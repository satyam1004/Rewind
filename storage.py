"""MySQL repository. Audio and metadata commit atomically in one InnoDB row."""
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

import pymysql

COLUMNS = 'id, original, title, artist, album, year, duration, size, sha256, favorite, created_at, category'
FIELDS = tuple(COLUMNS.split(', '))


class StorageError(Exception):
    pass


class StorageConfigurationError(StorageError):
    pass


class DuplicateSong(StorageError):
    pass


def mysql_config(environment):
    required = ['REWIND_MYSQL_DATABASE', 'REWIND_MYSQL_USER', 'REWIND_MYSQL_PASSWORD']
    missing = [name for name in required if not environment.get(name)]
    if missing:
        raise StorageConfigurationError('Set ' + ', '.join(missing) + ' in your environment or .env. See README.md.')
    try:
        port = int(environment.get('REWIND_MYSQL_PORT', '3306'))
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError:
        raise StorageConfigurationError('REWIND_MYSQL_PORT must be between 1 and 65535.')
    options = dict(host=environment.get('REWIND_MYSQL_HOST', '127.0.0.1'), port=port,
                   user=environment['REWIND_MYSQL_USER'], password=environment['REWIND_MYSQL_PASSWORD'],
                   database=environment['REWIND_MYSQL_DATABASE'], charset='utf8mb4',
                   cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                   connect_timeout=10, read_timeout=600, write_timeout=600)
    if environment.get('REWIND_MYSQL_SSL_CA'):
        options.update(ssl_ca=environment['REWIND_MYSQL_SSL_CA'], ssl_verify_cert=True, ssl_verify_identity=True)
    return options


class MySQLStore:
    def __init__(self, config):
        self.config = config
        self._ready = False
        self._schema_lock = Lock()

    @contextmanager
    def connection(self):
        connection = None
        try:
            connection = pymysql.connect(**self.config)
            yield connection
            connection.commit()
        except pymysql.IntegrityError as error:
            if connection is not None:
                connection.rollback()
            if error.args and error.args[0] == 1062:
                raise DuplicateSong('That exact audio file or song ID is already in your library.') from None
            raise StorageError('MySQL rejected the song data. Check the Rewind schema.') from None
        except (pymysql.MySQLError, OSError):
            if connection is not None:
                try:
                    connection.rollback()
                except pymysql.MySQLError:
                    pass
            # Never include driver errors: they can contain SQL with audio or connection details.
            raise StorageError('MySQL is unavailable or not ready. Check its connection settings, schema, storage space and max_allowed_packet (512 MB recommended).') from None
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def ensure_schema(self):
        if not self._ready:
            with self._schema_lock:
                if not self._ready:
                    self.initialize()

    def initialize(self):
        sql = (Path(__file__).parent / 'schema.sql').read_text()
        # Only hard-coded identifiers enter DDL; credentials and user data never do.
        definitions = {
            'id': 'CHAR(32) CHARACTER SET ascii COLLATE ascii_bin',
            'original': 'VARCHAR(255)', 'title': 'VARCHAR(200)',
            'artist': 'VARCHAR(200)', 'album': "VARCHAR(200) NOT NULL DEFAULT ''",
            'year': 'SMALLINT UNSIGNED', 'duration': 'DOUBLE', 'size': 'BIGINT UNSIGNED',
            'sha256': 'CHAR(64) CHARACTER SET ascii COLLATE ascii_bin',
            'favorite': 'BOOLEAN NOT NULL DEFAULT FALSE',
            'category': "VARCHAR(20) NOT NULL DEFAULT ''",
            'created_at': 'VARCHAR(32) CHARACTER SET ascii', 'audio_data': 'LONGBLOB',
        }
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT GET_LOCK(CONCAT('rewind:', LEFT(SHA2(DATABASE(),256),50)), 10) AS acquired")
                lock = cursor.fetchone()
                if not lock or lock['acquired'] != 1:
                    raise StorageError('MySQL schema setup is busy. Try again shortly.')
                try:
                    cursor.execute(sql)
                    cursor.execute((Path(__file__).parent / 'accounts.sql').read_text())
                    cursor.execute((Path(__file__).parent / 'user_library.sql').read_text())
                    cursor.execute('SHOW COLUMNS FROM songs')
                    present = {row['Field']: row for row in cursor.fetchall()}
                    for name, definition in definitions.items():
                        if name not in present:
                            cursor.execute(f'ALTER TABLE songs ADD COLUMN `{name}` {definition}')
                    # Never fabricate audio or identity for existing incomplete rows.
                    required = [name for name in definitions if name not in ('album', 'favorite', 'category')]
                    condition = ' OR '.join(f'`{name}` IS NULL' for name in required)
                    cursor.execute(f'SELECT COUNT(*) AS incomplete FROM songs WHERE {condition}')
                    if cursor.fetchone()['incomplete']:
                        raise StorageError('Required columns were added, but existing rows lack required values. Restore or migrate their missing audio/metadata before using this table. No rows were deleted.')
                    if 'audio_data' in present and present['audio_data']['Type'].lower() != 'longblob':
                        raise StorageError('Existing audio_data column must be LONGBLOB. Back up and widen its type before uploading; no existing column was replaced.')
                    cursor.execute('SHOW INDEX FROM songs')
                    indexes = cursor.fetchall()
                    unique = {}
                    for row in indexes:
                        if row['Non_unique'] == 0:
                            unique.setdefault(row['Key_name'], []).append(row['Column_name'])
                    for column, name in [('id', 'rewind_id_unique'), ('sha256', 'songs_sha256_unique')]:
                        if [column] not in unique.values():
                            cursor.execute(f'ALTER TABLE songs ADD UNIQUE KEY `{name}` (`{column}`)')
                finally:
                    cursor.execute("SELECT RELEASE_LOCK(CONCAT('rewind:', LEFT(SHA2(DATABASE(),256),50)))")

        self._ready = True

    def list_songs(self):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT {COLUMNS} FROM songs ORDER BY created_at DESC, id')
                return cursor.fetchall()

    def get(self, song_id):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT {COLUMNS} FROM songs WHERE id = %s', (song_id,))
                return cursor.fetchone()

    def by_hash(self, digest):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'SELECT {COLUMNS} FROM songs WHERE sha256 = %s', (digest,))
                return cursor.fetchone()

    def audio(self, song_id):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT audio_data FROM songs WHERE id = %s', (song_id,))
                row = cursor.fetchone()
                return bytes(row['audio_data']) if row else None

    def insert(self, song, audio):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'INSERT INTO songs ({COLUMNS}, audio_data) VALUES ({", ".join(["%s"] * (len(FIELDS) + 1))})',
                               tuple(song[field] for field in FIELDS) + (audio,))

    def update(self, song_id, details):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE songs SET title=%s, artist=%s, album=%s, year=%s, category=%s, favorite=%s WHERE id=%s',
                               (*details, song_id))

    def delete(self, song_id):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM songs WHERE id=%s', (song_id,))

    def preview_id(self):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id FROM songs ORDER BY created_at ASC, id ASC LIMIT 1')
                row = cursor.fetchone()
                return row['id'] if row else None

    def listener_by_username(self, username):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, username, password_hash FROM users WHERE username=%s', (username,))
                return cursor.fetchone()

    def listener_by_id(self, listener_id):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, username FROM users WHERE id=%s', (listener_id,))
                return cursor.fetchone()

    def create_listener(self, listener_id, username, password_hash):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)', (listener_id, username, password_hash))

    def personal_library(self, user_id):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT p.song_id, p.favorite, p.play_count, p.last_played FROM user_library p JOIN songs s ON s.id=p.song_id WHERE p.user_id=%s', (user_id,))
                rows=cursor.fetchall()
                for row in rows:
                    row['favorite']=bool(row['favorite'])
                    row['last_played']=row['last_played'].isoformat()+'Z' if row['last_played'] else None
                return rows

    def personal_favorite(self, user_id, song_id, favorite):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO user_library (user_id, song_id, favorite) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE favorite=%s', (user_id, song_id, favorite, favorite))

    def personal_play(self, user_id, song_id):
        self.ensure_schema()
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO user_library (user_id, song_id, play_count, last_played) VALUES (%s,%s,1,UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE play_count=play_count+IF(last_played IS NULL OR last_played < UTC_TIMESTAMP(6)-INTERVAL 30 SECOND,1,0), last_played=UTC_TIMESTAMP(6)', (user_id, song_id))
