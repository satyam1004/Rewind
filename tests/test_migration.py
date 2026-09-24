import hashlib
from pathlib import Path
import sqlite3
import pytest
from migrate_sqlite import migrate, MigrationError
from tests.fakes import MemoryStore
from tests.test_app import wav_bytes


@pytest.fixture
def legacy(tmp_path):
    (tmp_path / 'audio').mkdir()
    blob = wav_bytes()
    song_id = 'a' * 32
    (tmp_path / 'audio' / (song_id + '.wav')).write_bytes(blob)
    with sqlite3.connect(tmp_path / 'library.sqlite3') as connection:
        connection.execute('CREATE TABLE songs (id TEXT, filename TEXT, original TEXT, title TEXT, artist TEXT, album TEXT, year INTEGER, duration REAL, size INTEGER, sha256 TEXT, favorite INTEGER, created_at TEXT)')
        connection.execute('INSERT INTO songs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (song_id, song_id + '.wav', 'favorite.wav', 'Old memory', 'Artist', 'Album', 1986, 1., len(blob), hashlib.sha256(blob).hexdigest(), 1, '2026-09-11T00:00:00.000Z'))
    return tmp_path, blob, song_id


def source_hashes(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_dry_run_and_repeatable_copy_preserve_source(legacy):
    root, blob, song_id = legacy
    before = source_hashes(root)
    assert migrate(root) == {'verified':1, 'inserted':0, 'skipped':0}
    store = MemoryStore()
    assert migrate(root, store) == {'verified':1, 'inserted':1, 'skipped':0}
    assert store.audio(song_id) == blob
    assert store.get(song_id)['favorite'] is True
    assert store.get(song_id)['created_at'] == '2026-09-11T00:00:00.000Z'
    store.rows[song_id]['title'] = 'Edited in MySQL'
    assert migrate(root, store)['skipped'] == 1
    assert store.get(song_id)['title'] == 'Edited in MySQL'
    assert source_hashes(root) == before


def test_missing_file_aborts_before_any_insert(legacy):
    root, blob, song_id = legacy
    (root / 'audio' / (song_id + '.wav')).unlink()
    store = MemoryStore()
    with pytest.raises(MigrationError, match='Missing'):
        migrate(root, store)
    assert store.rows == {}


def test_corrupt_file_aborts_without_source_changes(legacy):
    root, blob, song_id = legacy
    (root / 'audio' / (song_id + '.wav')).write_bytes(b'corrupt')
    before = source_hashes(root)
    with pytest.raises(MigrationError, match='mismatch'):
        migrate(root, MemoryStore())
    assert source_hashes(root) == before


def test_target_id_conflict_never_overwrites(legacy):
    root, blob, song_id = legacy
    store = MemoryStore()
    store.rows[song_id] = {'id':song_id, 'sha256':'different'}
    with pytest.raises(MigrationError, match='conflict'):
        migrate(root, store)
    assert store.rows[song_id]['sha256'] == 'different'


def test_duplicate_hash_keeps_existing_target_metadata(legacy):
    root, blob, song_id = legacy
    store = MemoryStore()
    store.rows['b' * 32] = {'id':'b' * 32, 'sha256':hashlib.sha256(blob).hexdigest(), 'title':'Keep this'}
    store.blobs['b' * 32] = blob
    assert migrate(root, store)['skipped'] == 1
    assert len(store.rows) == 1
    assert store.rows['b' * 32]['title'] == 'Keep this'


def test_traversal_rejected(legacy):
    root, _, song_id = legacy
    with sqlite3.connect(root / 'library.sqlite3') as connection:
        connection.execute('UPDATE songs SET filename=?', ('../../outside.wav',))
    with pytest.raises(MigrationError, match='unsafe'):
        migrate(root, MemoryStore())


def test_default_cli_is_read_only_and_never_connects(legacy, monkeypatch, capsys):
    import pymysql
    from migrate_sqlite import main
    root, _, _ = legacy
    def forbidden_connection(**kwargs):
        raise AssertionError('Dry run must not connect to MySQL')
    monkeypatch.setattr(pymysql, 'connect', forbidden_connection)
    before = source_hashes(root)
    assert main(['--source', str(root)]) == 0
    assert 'no MySQL connection' in capsys.readouterr().out
    assert source_hashes(root) == before


def test_missing_source_is_not_created(tmp_path):
    with pytest.raises(MigrationError, match='No library.sqlite3'):
        migrate(tmp_path)
    assert not list(tmp_path.iterdir())
