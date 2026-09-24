import re
import pytest
from app import create_app
from tests.fakes import MemoryStore
from werkzeug.security import generate_password_hash
from tests.test_app import upload

@pytest.fixture
def website():
    app=create_app({'TESTING':True, 'SONG_STORE':MemoryStore(), 'ADMIN_USER':'owner', 'ADMIN_PASSWORD_HASH':generate_password_hash('correct-password',method='pbkdf2:sha256:1000')})
    client=app.test_client()
    token=re.search(r'name="rewind-token" content="([^"]+)"',client.get('/').get_data(as_text=True)).group(1)
    return app,client,{'X-Rewind-Token':token}

def login(client, headers, password='correct-password'):
    return client.post('/api/admin/login',headers=headers,json={'username':'owner','password':password})

def test_visitors_read_but_cannot_upload_edit_delete(website):
    _,client,headers=website
    assert client.get('/api/songs').status_code==200
    assert upload(client,headers).status_code==401
    assert client.patch('/api/songs/anything',headers=headers,json={'title':'Changed'}).status_code==401
    assert client.delete('/api/songs/anything',headers=headers).status_code==401
    assert 'Admin login' in client.get('/').get_data(as_text=True)

def test_login_upload_logout_and_csrf_rotation(website):
    app,client,headers=website
    response=login(client,headers)
    assert response.status_code==200
    new_headers={'X-Rewind-Token':response.json['csrf']}
    assert new_headers!=headers
    assert upload(client,headers).status_code==403
    result=upload(client,new_headers)
    assert result.status_code==201
    visitor=app.test_client()
    for prefix in ('/audio/','/download/'):
        assert visitor.get(prefix+result.json['id']).status_code==200
    assert 'Sign out' in client.get('/').get_data(as_text=True)
    out=client.post('/api/admin/logout',headers=new_headers,json={})
    assert out.status_code==200
    assert upload(client,{'X-Rewind-Token':out.json['csrf']}).status_code==401

def test_wrong_password_and_rate_limit(website):
    _,client,headers=website
    for _ in range(5):
        assert login(client,headers,'wrong').status_code==401
    assert login(client,headers).status_code==429
    assert upload(client,headers).status_code==401

def test_admin_disabled_without_password(website):
    app,client,headers=website
    app.config['ADMIN_PASSWORD_HASH']=''
    assert login(client,headers).status_code==503
    assert upload(client,headers).status_code==401

def test_csrf_bound_to_browser_session(website):
    app,_,headers=website
    another=app.test_client();another.get('/')
    assert login(another,headers).status_code==403

def test_favorite_only_cannot_bypass_metadata_guard(website):
    _,client,headers=website
    auth=login(client,headers)
    admin_headers={'X-Rewind-Token':auth.json['csrf']}
    song_id=upload(client,admin_headers).json['id']
    out=client.post('/api/admin/logout',headers=admin_headers,json={})
    guest_headers={'X-Rewind-Token':out.json['csrf']}
    assert client.patch('/api/songs/'+song_id,headers=guest_headers,json={'favorite':True}).status_code==401
    assert client.patch('/api/songs/'+song_id,headers=guest_headers,json={'favorite':False,'title':'bad'}).status_code==401

def test_app_attempts_automatic_schema_setup(monkeypatch):
    import app as module
    from unittest.mock import MagicMock
    store=MagicMock()
    monkeypatch.setattr(module,'mysql_config',lambda environment:{})
    monkeypatch.setattr(module,'MySQLStore',lambda config:store)
    monkeypatch.setattr(module,'load_dotenv',lambda *args,**kwargs:None)
    create_app({'TESTING':True})
    store.ensure_schema.assert_called_once()
