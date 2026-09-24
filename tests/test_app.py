import io
import re
import wave
import pytest
from app import create_app
from tests.fakes import MemoryStore
from storage import StorageError
from werkzeug.security import generate_password_hash


def wav_bytes(frames=8000):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b'\x00\x00' * frames)
    return stream.getvalue()


@pytest.fixture
def library(tmp_path):
    store = MemoryStore()
    app = create_app({'TESTING': True, 'SONG_STORE': store, 'ADMIN_USER':'admin', 'ADMIN_PASSWORD_HASH':generate_password_hash('testing-password', method='pbkdf2:sha256:1000')})
    client = app.test_client()
    with client.session_transaction() as session:
        session['admin'] = 'admin'
    token = re.search(r'name="rewind-token" content="([^"]+)"', client.get('/').get_data(as_text=True)).group(1)
    return app, client, {'X-Rewind-Token': token}, tmp_path


def upload(client, headers, payload=None, name='old favorite.wav', **metadata):
    return client.post('/api/songs', headers=headers, data={'file': (io.BytesIO(payload or wav_bytes()), name), 'year': '1987', **metadata})


def test_complete_lifecycle_and_persistence(library):
    app, client, headers, root = library
    assert client.get('/api/songs').json == []
    result = upload(client, headers, title='A memory', artist='My artist')
    assert result.status_code == 201
    song = result.json
    assert song['duration'] == 1 and song['decade'] == 1980
    assert 'filename' not in song and 'sha256' not in song
    song_id = song['id']
    response = client.get('/audio/' + song_id, headers={'Range': 'bytes=0-43'})
    assert response.status_code == 206 and response.data == wav_bytes()[:44]
    download = client.get('/download/' + song_id)
    assert download.data == wav_bytes()
    assert 'attachment;' in download.headers['Content-Disposition']
    result = client.patch('/api/songs/' + song_id, headers=headers, json={'year': 2001, 'title': 'Changed title'})
    assert 'favorite' not in result.json and result.json['decade'] == 2000
    fresh = create_app({'TESTING': True, 'SONG_STORE': app.extensions['song_store']}).test_client()
    assert fresh.get('/api/songs').json[0]['title'] == 'Changed title'
    assert client.delete('/api/songs/' + song_id, headers=headers).status_code == 204
    assert client.get('/api/songs').json == []
    assert client.get('/audio/' + song_id).status_code == 404
    assert not list(root.iterdir())


@pytest.mark.parametrize('year,expected_decade', [(1980, 1980), (1990, 1980), (1991, 1990), (2000, 1990), (2001, 2000), (2030, 2000)])
def test_decade_boundaries(library, year, expected_decade):
    _, client, headers, _ = library
    result = upload(client, headers, year=str(year), title=f'Song {year}')
    assert result.status_code == 201
    assert result.json['decade'] == expected_decade


def test_duplicate_does_not_leave_orphan(library):
    _, client, headers, root = library
    assert upload(client, headers).status_code == 201
    assert upload(client, headers, name='renamed.wav').status_code == 409
    assert len(client.get('/api/songs').json) == 1
    assert not list(root.iterdir())


@pytest.mark.parametrize('payload,name,year', [(b'not audio','test.mp3','1985'), (b'plain text','test.txt','1985'), (wav_bytes(),'test.wav','2010'), (wav_bytes(),'test.wav','1979'), (wav_bytes(),'test.wav','oops')])
def test_invalid_upload_is_rejected_and_cleaned(library, payload, name, year):
    _, client, headers, root = library
    assert upload(client, headers, payload, name, year=year).status_code == 400
    assert client.get('/api/songs').json == []
    assert not list(root.iterdir())


def test_mutation_token_required(library):
    _, client, headers, _ = library
    assert upload(client, {}).status_code == 403
    assert upload(client, {'X-Rewind-Token': 'wrong'}).status_code == 403
    assert upload(client, headers).status_code == 201


def test_safe_filename_and_validation(library):
    _, client, headers, root = library
    result = upload(client, headers, name='../../outside.wav', title='<script>alert(1)</script>')
    assert result.status_code == 201 and result.json['original'] == 'outside.wav'
    song_id = result.json['id']
    assert len(client.get('/api/songs').json) == 1
    assert not list(root.iterdir())
    for data in [{'title': ''}, {'title': 'x' * 201}, {'year': 'foo'}, {'favorite': 'yes'}, []]:
        assert client.patch('/api/songs/' + song_id, headers=headers, json=data).status_code == 400
    assert client.get('/download/../../outside.wav').status_code == 404


def test_request_size_limit(library):
    app, client, headers, root = library
    app.config['MAX_CONTENT_LENGTH'] = 100
    assert upload(client, headers).status_code == 413
    assert not list(root.iterdir())


def test_missing_upload_and_records(library):
    _, client, headers, _ = library
    assert client.post('/api/songs', headers=headers).status_code == 400
    assert client.patch('/api/songs/missing', headers=headers, json={}).status_code == 404
    assert client.delete('/api/songs/missing', headers=headers).status_code == 404


def test_missing_audio_has_useful_error(library):
    app, client, headers, root = library
    song_id = upload(client, headers).json['id']
    app.extensions['song_store'].blobs.pop(song_id)
    for prefix in ['/audio/', '/download/']:
        response = client.get(prefix + song_id)
        assert response.status_code == 404


def test_range_variants_and_conditional_requests(library):
    _, client, headers, _ = library
    result = upload(client, headers)
    url = '/audio/' + result.json['id']
    content = wav_bytes()
    for header, expected in [('bytes=40-99', content[40:100]), ('bytes=-40', content[-40:]), ('bytes=44-', content[44:])]:
        response = client.get(url, headers={'Range': header})
        assert response.status_code == 206 and response.data == expected
        assert response.headers['Accept-Ranges'] == 'bytes'
    assert client.get(url, headers={'Range': 'bytes=999999-'}).status_code == 416
    assert client.get(url, headers={'Range': 'bytes=0-1,4-5'}).status_code == 416
    assert client.head(url).data == b''
    etag = client.get(url).headers['ETag']
    assert client.get(url, headers={'If-None-Match': etag}).status_code == 304
    assert client.get(url, headers={'If-Range': '"old"', 'Range': 'bytes=0-3'}).status_code == 200
    assert client.get(url, headers={'If-Range': etag, 'Range': 'bytes=0-3'}).data == content[:4]


def test_database_failure_returns_actionable_json(library, monkeypatch):
    app, client, headers, _ = library
    def fail(*args):
        raise StorageError('MySQL is unavailable. Check configuration.')
    monkeypatch.setattr(app.extensions['song_store'], 'list_songs', fail)
    response = client.get('/api/songs')
    assert response.status_code == 503 and 'MySQL' in response.json['error']
    monkeypatch.setattr(app.extensions['song_store'], 'insert', fail)
    assert upload(client, headers).status_code == 503


def test_unconfigured_app_never_connects_to_mysql(monkeypatch):
    import app as app_module
    import pymysql
    from storage import StorageConfigurationError
    def not_configured(environment):
        raise StorageConfigurationError('Set REWIND_MYSQL_DATABASE in .env.')
    def forbidden_connection(**kwargs):
        raise AssertionError('A database connection must not be attempted by this test')
    monkeypatch.setattr(app_module, 'mysql_config', not_configured)
    monkeypatch.setattr(app_module, 'load_dotenv', lambda *args, **kwargs: None)
    monkeypatch.setattr(pymysql, 'connect', forbidden_connection)
    app = create_app({'TESTING': True})
    client = app.test_client()
    assert client.get('/').status_code == 200
    response = client.get('/api/songs')
    assert response.status_code == 503
    assert 'temporarily unavailable' in response.json['error']
    assert 'REWIND_MYSQL_DATABASE' not in response.json['error']
    result = app.test_cli_runner().invoke(args=['init-db'])
    assert result.exit_code == 1
    assert 'REWIND_MYSQL_DATABASE' in result.output


def test_long_original_filename_preserves_audio_extension(library):
    _, client, headers, _ = library
    result = upload(client, headers, name='a' * 300 + '.wav', title='Short title')
    assert result.status_code == 201
    assert len(result.json['original']) <= 255
    assert result.json['original'].endswith('.wav')
    assert client.get('/audio/' + result.json['id']).mimetype in ('audio/wav', 'audio/x-wav')


@pytest.mark.parametrize('category', ['love', 'ghazal', 'travel', 'party'])
def test_category_upload_and_readback(library, category):
    _, client, headers, _ = library
    result=upload(client,headers,category=category)
    assert result.status_code==201
    assert result.json['category']==category
    assert client.get('/api/songs').json[0]['category']==category


def test_category_edit_and_uncategorized_default(library):
    _,client,headers,_=library
    result=upload(client,headers)
    assert result.json['category']==''
    song_id=result.json['id']
    result=client.patch('/api/songs/'+song_id,headers=headers,json={'category':'travel'})
    assert result.json['category']=='travel'
    result=client.patch('/api/songs/'+song_id,headers=headers,json={'title':'Renamed'})
    assert result.json['category']=='travel'
    result=client.patch('/api/songs/'+song_id,headers=headers,json={'category':''})
    assert result.json['category']==''


@pytest.mark.parametrize('category',['invalid',None])
def test_invalid_category_rejected(library,category):
    _,client,headers,_=library
    result=upload(client,headers)
    response=client.patch('/api/songs/'+result.json['id'],headers=headers,json={'category':category})
    assert response.status_code==400
    assert client.get('/api/songs').json[0]['category']==''


def test_legacy_favorites_are_private_and_preserved(library):
    app,client,headers,_=library
    song_id=upload(client,headers).json['id']
    store=app.extensions['song_store']
    store.rows[song_id]['favorite']=True
    assert 'favorite' not in client.get('/api/songs').json[0]
    assert client.patch('/api/songs/'+song_id,headers=headers,json={'favorite':False}).status_code==400
    assert client.patch('/api/songs/'+song_id,headers=headers,json={'title':'Updated'}).status_code==200
    assert store.rows[song_id]['favorite'] == 1


def test_storage_details_hidden_from_visitors(library,monkeypatch):
    app,client,_,_=library
    def fail():
        raise StorageError('MySQL internal configuration detail')
    monkeypatch.setattr(app.extensions['song_store'],'list_songs',fail)
    assert 'MySQL' in client.get('/api/songs').json['error']
    guest=app.test_client()
    response=guest.get('/api/songs')
    assert response.status_code==503
    assert response.json['error']=='The music library is temporarily unavailable. Please try again later.'
