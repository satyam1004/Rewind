import re
import pytest
from app import create_app
from tests.fakes import MemoryStore
from tests.test_app import wav_bytes
from werkzeug.security import check_password_hash, generate_password_hash

@pytest.fixture
def account_site():
    store=MemoryStore()
    for i,key in enumerate('ab'):
        blob=wav_bytes(8000+i)
        store.insert(dict(id=key*32,original='tone.wav',title='Track '+key,artist='Test',album='',year=1987,category='',duration=1,size=len(blob),sha256=key*64,favorite=False,created_at=str(i)),blob)
    app=create_app({'TESTING':True,'SONG_STORE':store,'ADMIN_USER':'admin','ADMIN_PASSWORD_HASH':generate_password_hash('admin-password',method='pbkdf2:sha256:1000')})
    client=app.test_client()
    token=client.get('/api/account').json['csrf']
    return app,store,client,{'X-Rewind-Token':token}

def register(client,headers,**extra):
    return client.post('/api/account/register',headers=headers,json={'username':'musicfan','password':'long-test-password',**extra})

def test_guest_has_only_one_shared_preview_including_direct_urls(account_site):
    app,store,client,headers=account_site
    listing=client.get('/api/songs').json
    assert sum(not s['locked'] for s in listing)==1
    assert sum(s['preview'] for s in listing)==1
    for path in ('/audio/','/download/'):
        assert client.get(path+'a'*32).status_code==200
        for method in ('get','head'):
            response=getattr(client,method)(path+'b'*32,headers={'Range':'bytes=0-3'})
            assert response.status_code==401
            assert response.headers['Cache-Control']=='no-store'
        assert app.test_client().get(path+'b'*32).status_code==401
    assert client.get('/audio/'+'a'*32,headers={'Range':'bytes=0-3'}).status_code==206

def test_registration_login_logout_and_listener_never_admin(account_site):
    app,store,client,headers=account_site
    response=register(client,headers,admin=True,role='admin')
    assert response.status_code==201
    assert response.json['admin'] is False
    assert set(response.json['listener'])=={'id','username'}
    saved=store.listener_by_username('musicfan')
    assert saved['password_hash']!='long-test-password'
    assert check_password_hash(saved['password_hash'],'long-test-password')
    auth={'X-Rewind-Token':response.json['csrf']}
    assert auth!=headers
    assert client.get('/audio/'+'b'*32).status_code==200
    assert client.get('/download/'+'b'*32).status_code==200
    assert all(not s['locked'] for s in client.get('/api/songs').json)
    for method,path in [('post','/api/songs'),('patch','/api/songs/'+'b'*32),('delete','/api/songs/'+'b'*32)]:
        assert getattr(client,method)(path,headers=auth,json={}).status_code==401
    out=client.post('/api/account/logout',headers=auth,json={})
    assert client.get('/audio/'+'b'*32).status_code==401
    new={'X-Rewind-Token':out.json['csrf']}
    assert client.post('/api/account/login',headers=new,json={'username':'MusicFan','password':'wrong-password'}).status_code==401
    good=client.post('/api/account/login',headers=new,json={'username':'MusicFan','password':'long-test-password'})
    assert good.status_code==200
    assert client.get('/audio/'+'b'*32).status_code==200
    # Account data persists through a fresh app using the same repository.
    fresh=create_app({'TESTING':True,'SONG_STORE':store}).test_client()
    token=fresh.get('/api/account').json['csrf']
    assert fresh.post('/api/account/login',headers={'X-Rewind-Token':token},json={'username':'musicfan','password':'long-test-password'}).status_code==200

def test_registration_validation_duplicates_and_csrf(account_site):
    _,store,client,headers=account_site
    assert register(client,{}).status_code==403
    assert register(client,headers,password='short').status_code==400
    assert register(client,headers,username='bad name').status_code==400
    assert register(client,headers,username='admin').status_code==409
    good=register(client,headers)
    assert good.status_code==201
    current={'X-Rewind-Token':good.json['csrf']}
    assert register(client,current,username='MUSICFAN').status_code==409
    assert client.post('/api/account/logout',headers=headers,json={}).status_code==403
    assert len(store.listeners)==1

def test_invalid_or_deleted_listener_cannot_access_audio(account_site):
    _,_,client,_=account_site
    with client.session_transaction() as session:
        session['listener_id']='f'*32
    assert client.get('/audio/'+'b'*32).status_code==401

def test_account_rate_limit(account_site):
    _,_,client,headers=account_site
    for _ in range(10):
        assert register(client,headers,password='short').status_code==400
    assert register(client,headers).status_code==429

def test_admin_can_hear_all_songs_without_listener_registration(account_site):
    _,_,client,_=account_site
    with client.session_transaction() as session:
        session['admin']='admin'
    assert client.get('/audio/'+'b'*32).status_code==200


def test_personal_favorites_and_history_are_owned_by_authenticated_user(account_site):
    app,store,alice,headers=account_site
    alice_result=register(alice,headers,username='alice')
    alice_id=alice_result.json['listener']['id']
    ah={'X-Rewind-Token':alice_result.json['csrf']}
    bob=app.test_client()
    bh={'X-Rewind-Token':bob.get('/api/account').json['csrf']}
    bob_result=register(bob,bh,username='bob')
    bob_id=bob_result.json['listener']['id']
    bh={'X-Rewind-Token':bob_result.json['csrf']}
    track='b'*32
    saved=alice.post('/api/me/library/'+track+'/favorite',headers=ah,json={'favorite':True,'user_id':bob_id})
    assert saved.status_code==200 and saved.json['user_id']==alice_id
    assert alice.post('/api/me/library/'+track+'/played',headers=ah,json={'user_id':bob_id}).status_code==200
    assert alice.post('/api/me/library/'+track+'/played',headers=ah,json={}).status_code==200
    rows=alice.get('/api/me/library').json['songs']
    assert rows[0]['favorite'] is True and rows[0]['play_count']==1
    assert bob.get('/api/me/library').json['songs']==[]
    assert app.test_client().get('/api/me/library').status_code==401
    assert bob.post('/api/me/library/'+track+'/favorite',headers=bh,json={'favorite':False,'user_id':alice_id}).status_code==200
    assert alice.get('/api/me/library').json['songs'][0]['favorite'] is True
    # A separate browser signed into Alice sees Alice's saved library.
    another=app.test_client();new={'X-Rewind-Token':another.get('/api/account').json['csrf']}
    another.post('/api/account/login',headers=new,json={'username':'alice','password':'long-test-password'})
    assert another.get('/api/me/library').json['songs']==rows
    # Deleting a song removes it from personal views without exposing old metadata.
    store.delete(track)
    assert alice.get('/api/me/library').json['songs']==[]


def test_personal_activity_requires_login_valid_song_and_csrf(account_site):
    _,_,client,headers=account_site
    path='/api/me/library/'+'b'*32+'/favorite'
    assert client.post(path,headers=headers,json={'favorite':True}).status_code==401
    good=register(client,headers);auth={'X-Rewind-Token':good.json['csrf']}
    assert client.post(path,headers=headers,json={'favorite':True}).status_code==403
    assert client.post(path,headers=auth,json={'favorite':'true'}).status_code==400
    assert client.post('/api/me/library/'+'f'*32+'/played',headers=auth,json={}).status_code==404
