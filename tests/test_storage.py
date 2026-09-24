from unittest.mock import MagicMock
import pytest
import pymysql
from storage import MySQLStore, StorageError, StorageConfigurationError, DuplicateSong, mysql_config, FIELDS


def test_config_requires_explicit_credentials():
    with pytest.raises(StorageConfigurationError, match='REWIND_MYSQL_DATABASE'):
        mysql_config({})
    with pytest.raises(StorageConfigurationError, match='PORT'):
        mysql_config({'REWIND_MYSQL_DATABASE':'test', 'REWIND_MYSQL_USER':'test', 'REWIND_MYSQL_PASSWORD':'test', 'REWIND_MYSQL_PORT':'bad'})
    config = mysql_config({'REWIND_MYSQL_DATABASE':'test', 'REWIND_MYSQL_USER':'test', 'REWIND_MYSQL_PASSWORD':'test', 'REWIND_MYSQL_SSL_CA':'ca.pem'})
    assert config['ssl_verify_identity'] and config['ssl_verify_cert']
    assert config['charset'] == 'utf8mb4'


def connection_stub(monkeypatch):
    monkeypatch.setattr(MySQLStore, 'ensure_schema', lambda self: None)
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(pymysql, 'connect', lambda **kwargs: connection)
    cursor.fetchone.return_value = {'acquired':1, 'incomplete':0}
    cursor.fetchall.return_value = []
    return connection, cursor


def test_blob_insert_parameterized_and_atomic(monkeypatch):
    connection, cursor = connection_stub(monkeypatch)
    song = dict.fromkeys(FIELDS, "quote' and \\ test")
    data = b'\x00\xffbinary'
    MySQLStore({}).insert(song, data)
    sql, values = cursor.execute.call_args.args
    assert 'audio_data' in sql and 'quote' not in sql
    assert values[-1] == data and len(values) == 13
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


def test_listing_never_fetches_blob(monkeypatch):
    _, cursor = connection_stub(monkeypatch)
    MySQLStore({}).list_songs()
    sql = cursor.execute.call_args.args[0]
    assert 'audio_data' not in sql and 'SELECT *' not in sql


@pytest.mark.parametrize('code,expected', [(1062, DuplicateSong), (1406, StorageError), (1153, StorageError)])
def test_driver_errors_rollback_without_exposing_sql(monkeypatch, code, expected):
    connection, cursor = connection_stub(monkeypatch)
    cursor.execute.side_effect = pymysql.IntegrityError(code, 'secret database password and SQL payload')
    with pytest.raises(expected) as error:
        MySQLStore({}).insert(dict.fromkeys(FIELDS, ''), b'audio')
    assert 'secret' not in str(error.value)
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
    connection.commit.assert_not_called()


def test_connect_failure_is_sanitized(monkeypatch):
    def fail(**kwargs):
        raise pymysql.OperationalError(1045, 'secret connection details')
    monkeypatch.setattr(pymysql, 'connect', fail)
    with pytest.raises(StorageError) as error:
        MySQLStore({}).list_songs()
    assert 'secret' not in str(error.value)


def test_schema_has_longblob_and_innodb(monkeypatch):
    _, cursor = connection_stub(monkeypatch)
    MySQLStore({}).initialize()
    sql = next(call.args[0] for call in cursor.execute.call_args_list if 'CREATE TABLE' in call.args[0])
    assert 'audio_data LONGBLOB NOT NULL' in sql
    assert 'ENGINE=InnoDB' in sql and 'CREATE TABLE IF NOT EXISTS' in sql
    assert 'DROP TABLE' not in sql

def test_setup_adds_missing_columns_without_dropping_data(monkeypatch):
    _,cursor=connection_stub(monkeypatch)
    MySQLStore({}).initialize()
    statements=[call.args[0] for call in cursor.execute.call_args_list]
    assert any('ADD COLUMN `audio_data` LONGBLOB' in sql for sql in statements)
    assert any('ADD COLUMN `favorite`' in sql for sql in statements)
    assert not any('DROP ' in sql or 'DELETE ' in sql for sql in statements)
    assert 'RELEASE_LOCK' in statements[-1]

def test_setup_does_not_alter_complete_existing_columns(monkeypatch):
    _,cursor=connection_stub(monkeypatch)
    columns=[{'Field':name,'Type':'longblob' if name=='audio_data' else 'varchar(200)'} for name in (*FIELDS,'audio_data')]
    indexes=[{'Non_unique':0,'Key_name':'PRIMARY','Column_name':'id'}, {'Non_unique':0,'Key_name':'songs_sha256_unique','Column_name':'sha256'}]
    cursor.fetchall.side_effect=[columns,indexes]
    MySQLStore({}).initialize()
    assert not any('ALTER TABLE' in call.args[0] for call in cursor.execute.call_args_list)

def test_incomplete_old_rows_preserved_and_reported(monkeypatch):
    _,cursor=connection_stub(monkeypatch)
    cursor.fetchone.side_effect=[{'acquired':1},{'incomplete':2}]
    with pytest.raises(StorageError,match='No rows were deleted'):
        MySQLStore({}).initialize()
    assert not any('DELETE ' in call.args[0] for call in cursor.execute.call_args_list)
    assert 'RELEASE_LOCK' in cursor.execute.call_args.args[0]

def test_schema_ensure_is_cached_after_success(monkeypatch):
    store=MySQLStore({})
    calls=[]
    def setup():
        calls.append(True)
        store._ready=True
    monkeypatch.setattr(store,'initialize',setup)
    store.ensure_schema();store.ensure_schema()
    assert len(calls)==1


def test_listener_schema_and_parameterized_account_queries(monkeypatch):
    _,cursor=connection_stub(monkeypatch)
    store=MySQLStore({})
    store.initialize()
    statements=[call.args[0] for call in cursor.execute.call_args_list]
    assert any('CREATE TABLE IF NOT EXISTS users' in sql and 'UNIQUE' in sql and 'password_hash' in sql for sql in statements)
    store.create_listener('a'*32,'musicfan','hashed-value')
    sql,values=cursor.execute.call_args.args
    assert 'INSERT INTO users' in sql and 'hashed-value' not in sql
    assert values==('a'*32,'musicfan','hashed-value')
    store.listener_by_username("name' OR 1=1")
    sql,values=cursor.execute.call_args.args
    assert "name'" not in sql and values==("name' OR 1=1",)
    store.listener_by_id('a'*32)
    assert 'password_hash' not in cursor.execute.call_args.args[0]


def test_preview_selection_is_stable_and_does_not_fetch_audio(monkeypatch):
    _,cursor=connection_stub(monkeypatch)
    cursor.fetchone.return_value={'id':'a'*32}
    assert MySQLStore({}).preview_id()=='a'*32
    sql=cursor.execute.call_args.args[0]
    assert 'ORDER BY created_at ASC, id ASC LIMIT 1' in sql
    assert 'audio_data' not in sql


def test_personal_queries_scope_every_operation_to_user(monkeypatch):
    _,cursor=connection_stub(monkeypatch)
    store=MySQLStore({})
    store.personal_library('owner')
    sql,values=cursor.execute.call_args.args
    assert 'WHERE p.user_id=%s' in sql and 'JOIN songs' in sql and values==('owner',)
    store.personal_favorite('owner','track',True)
    sql,values=cursor.execute.call_args.args
    assert '(user_id, song_id, favorite)' in sql and values==('owner','track',True,True)
    store.personal_play('owner','track')
    sql,values=cursor.execute.call_args.args
    assert 'INTERVAL 30 SECOND' in sql and values==('owner','track')
