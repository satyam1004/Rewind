"""Read-only source migration. Default is validation only; --apply copies to MySQL."""
import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import sys

from dotenv import load_dotenv
from storage import MySQLStore, StorageError, mysql_config


class MigrationError(Exception):
    pass


def source_records(data_dir):
    root = Path(data_dir).resolve()
    database = root / 'library.sqlite3'
    if not database.is_file():
        raise MigrationError('No library.sqlite3 found in the selected legacy data folder.')
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute('SELECT * FROM songs ORDER BY created_at, id').fetchall()
        for row in rows:
            record = dict(row)
            filename = record.pop('filename')
            path = (root / 'audio' / filename).resolve()
            if path.parent != (root / 'audio').resolve() or not path.is_file():
                raise MigrationError(f"Missing or unsafe audio path for song {record['id']}. Source unchanged.")
            if not re.fullmatch(r'[a-f0-9]{32}', record['id']):
                raise MigrationError('Invalid legacy song ID. Source unchanged.')
            if not 0 < path.stat().st_size <= 200 * 1024 * 1024:
                raise MigrationError(f"Audio size outside supported bounds for song {record['id']}.")
            audio = path.read_bytes()
            if len(audio) != record['size'] or hashlib.sha256(audio).hexdigest() != record['sha256']:
                raise MigrationError(f"Audio size/hash mismatch for song {record['id']}. Restore a matching backup first.")
            if (not record['title'] or any(len(str(record[k])) > 200 for k in ('title', 'artist', 'album'))
                    or not 1980 <= record['year'] <= 2009 or len(record['original']) > 255
                    or record['duration'] <= 0):
                raise MigrationError(f"Invalid legacy metadata for song {record['id']}. Source unchanged.")
            try:
                datetime.fromisoformat(record['created_at'].replace('Z', '+00:00'))
            except (ValueError, TypeError):
                raise MigrationError(f"Invalid creation timestamp for song {record['id']}.")
            record['favorite'] = bool(record['favorite'])
            record.setdefault('category', '')
            yield record, audio
    except sqlite3.Error:
        raise MigrationError('Unable to read the legacy SQLite schema. Source unchanged.') from None
    finally:
        connection.close()


def migrate(data_dir, store=None):
    """Prevalidate every source; then insert one atomic row at a time, never overwrite."""
    verified = sum(1 for _ in source_records(data_dir))
    if store is None:
        return dict(verified=verified, inserted=0, skipped=0)
    inserted = skipped = 0
    for record, audio in source_records(data_dir):
        existing = store.get(record['id'])
        if existing and existing['sha256'] != record['sha256']:
            raise MigrationError(f"Song ID conflict for {record['id']}; no existing MySQL row was overwritten. Earlier copied rows may remain; reruns are safe.")
        duplicate = existing or store.by_hash(record['sha256'])
        if duplicate:
            stored_audio = store.audio(duplicate['id'])
            if stored_audio is None or hashlib.sha256(stored_audio).hexdigest() != record['sha256']:
                raise MigrationError('An existing MySQL audio row failed its hash check. No overwrite was attempted.')
            skipped += 1
            continue
        store.insert(record, audio)
        stored_audio = store.audio(record['id'])
        if stored_audio is None or hashlib.sha256(stored_audio).hexdigest() != record['sha256']:
            raise MigrationError('MySQL readback verification failed. Source unchanged; inspect the target before retrying.')
        inserted += 1
    return dict(verified=verified, inserted=inserted, skipped=skipped)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(Path(__file__).parent / 'data'), help='Legacy data directory')
    parser.add_argument('--apply', action='store_true', help='Copy validated songs to the configured MySQL table')
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).parent / '.env', override=False)
    try:
        store = MySQLStore(mysql_config(os.environ)) if args.apply else None
        result = migrate(args.source, store)
        print(f"Verified: {result['verified']}; copied: {result['inserted']}; already present: {result['skipped']}.")
        print('Source SQLite database and audio files were not modified.')
        if not args.apply:
            print('Validation only; no MySQL connection made. Run with --apply after configuring and initializing MySQL.')
        return 0
    except (MigrationError, StorageError, OSError) as error:
        print(f'Migration stopped: {error}', file=sys.stderr)
        print('Source unchanged. Some target rows may already have been copied; reruns do not overwrite them.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
