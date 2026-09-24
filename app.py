"""Rewind: a local, persistent personal audio library."""
import re
import hashlib
import io
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import uuid
import time
from threading import Lock
from datetime import timedelta

import click
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, session
from storage import MySQLStore, StorageError, StorageConfigurationError, DuplicateSong, mysql_config
from mutagen import File as AudioFile
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

DUMMY_LISTENER_HASH = 'pbkdf2:sha256:1000000$Ie8gsEmtnw6C3IND$8a28a3645ff52e71da7b2432af5edf25bb5355fd270ec2f5a9aab8521e4d62ba'

ALLOWED = {'.mp3', '.m4a', '.flac', '.ogg', '.wav'}


def create_app(test_config=None):
    load_dotenv(Path(__file__).parent / '.env', override=False)
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=201 * 1024 * 1024,
                      SECRET_KEY=os.environ.get('REWIND_SESSION_SECRET') or secrets.token_hex(32),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('REWIND_COOKIE_SECURE') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      ADMIN_USER=os.environ.get('REWIND_ADMIN_USER', 'admin'),
                      ADMIN_PASSWORD_HASH=os.environ.get('REWIND_ADMIN_PASSWORD_HASH', ''))
    if test_config:
        app.config.update(test_config)
    store = app.config.get('SONG_STORE')
    if store is None:
        try:
            store = MySQLStore(mysql_config(os.environ))
            try:
                store.ensure_schema()
            except StorageError:
                pass  # Requests retry setup and surface a safe actionable error.
        except StorageConfigurationError as error:
            # Keep the UI accessible with a useful JSON configuration error.
            message = str(error)
            class UnconfiguredStore:
                def __getattr__(self, name):
                    raise StorageConfigurationError(message)
            store = UnconfiguredStore()
    app.extensions['song_store'] = store
    attempts = {}
    attempts_lock = Lock()

    def csrf_token():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    def is_admin():
        return bool(app.config['ADMIN_PASSWORD_HASH'] and session.get('admin') == app.config['ADMIN_USER'])

    def listener_account():
        listener_id = session.get('listener_id')
        return store.listener_by_id(listener_id) if listener_id else None

    def account_response():
        account = listener_account()
        return dict(listener=account, admin=is_admin(), csrf=csrf_token())

    def throttle_listener():
        now = time.monotonic()
        key = 'listener:' + (request.remote_addr or 'local')
        with attempts_lock:
            for address in list(attempts):
                if now - attempts[address][1] > 300:
                    del attempts[address]
            count, started = attempts.get(key, (0, now))
            if count >= 10 or (key not in attempts and len(attempts) >= 10000):
                return True
            attempts[key] = (count + 1, started)
        return False

    @app.get('/api/account')
    def account_status():
        return jsonify(account_response())

    @app.post('/api/account/<action>')
    def account_action(action):
        if action == 'logout':
            session.clear()
            return jsonify(account_response())
        if action not in ('login', 'register'):
            return jsonify(error='Unknown account action.'), 404
        if request.content_length and request.content_length > 4096:
            return jsonify(error='Account request is too large.'), 400
        if throttle_listener():
            return jsonify(error='Too many account attempts. Try again in five minutes.'), 429
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Enter a username and password.'), 400
        username = data.get('username', '')
        password = data.get('password', '')
        if not isinstance(username, str) or not isinstance(password, str):
            return jsonify(error='Enter a username and password.'), 400
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z0-9_]{3,32}', username) or not 12 <= len(password) <= 128:
            return jsonify(error='Use a username of 3–32 letters, numbers or underscores and a password of 12–128 characters.'), 400
        if action == 'register':
            if username == app.config['ADMIN_USER'].lower():
                return jsonify(error='Choose another username.'), 409
            listener_id = uuid.uuid4().hex
            password_hash = generate_password_hash(password, method='pbkdf2:sha256:1000000')
            try:
                store.create_listener(listener_id, username, password_hash)
            except DuplicateSong:
                return jsonify(error='Choose another username.'), 409
        else:
            account = store.listener_by_username(username)
            # Use an equal-cost hash check even when the username does not exist.
            check_hash = account['password_hash'] if account else DUMMY_LISTENER_HASH
            if not check_password_hash(check_hash, password) or not account:
                return jsonify(error='Incorrect username or password.'), 401
            listener_id = account['id']
        session.clear()
        session.permanent = True
        session['listener_id'] = listener_id
        return jsonify(account_response()), 201 if action == 'register' else 200

    @app.get('/api/me/library')
    def personal_library():
        account=listener_account()
        if not account:
            return jsonify(error='Sign in to view your personal library.'), 401
        return jsonify(user_id=account['id'], songs=store.personal_library(account['id']))

    @app.post('/api/me/library/<song_id>/<action>')
    def personal_activity(song_id, action):
        account=listener_account()
        if not account:
            return jsonify(error='Sign in to save your personal library.'), 401
        song(song_id)
        if action == 'favorite':
            data=request.get_json(silent=True)
            if not isinstance(data,dict) or type(data.get('favorite')) is not bool:
                return jsonify(error='Choose whether to favorite this song.'), 400
            store.personal_favorite(account['id'],song_id,data['favorite'])
        elif action == 'played':
            store.personal_play(account['id'],song_id)
        else:
            return jsonify(error='Unknown listening action.'), 404
        return jsonify(user_id=account['id'],songs=store.personal_library(account['id']))

    @app.cli.command('init-db')
    def init_db():
        """Create the MySQL table in an existing configured database."""
        try:
            store.initialize()
        except StorageError as error:
            raise click.ClickException(str(error))
        click.echo('Rewind MySQL table is ready. Existing rows were preserved.')

    def public(row):
        item = dict(row)
        item.pop('sha256')
        item.pop('favorite', None)  # Legacy shared flags remain stored, never exposed as personal favorites.
        item['decade'] = 1980 if item['year'] <= 1990 else 1990 if item['year'] <= 2000 else 2000
        return item

    def song(song_id):
        row = store.get(song_id)
        if row is None:
            from flask import abort
            abort(404, description='That song is no longer in your library.')
        return row

    def metadata(data):
        title = str(data.get('title', '')).strip()
        artist = str(data.get('artist', '')).strip() or 'Unknown artist'
        album = str(data.get('album', '')).strip()
        if not title or any(len(x) > 200 for x in [title, artist, album]):
            raise ValueError('Enter a title and keep each text field to 200 characters or fewer.')
        try:
            year = int(data.get('year', 0))
        except (TypeError, ValueError):
            raise ValueError('Enter a release year from 1980 to 2030.')
        if not 1980 <= year <= 2030:
            raise ValueError('Enter a release year from 1980 to 2030.')
        category = data.get('category', '')
        if category not in ('', 'love', 'ghazal', 'travel', 'party'):
            raise ValueError('Choose Ghazal, Travel, Party or Uncategorized.')
        return title, artist, album, year, category

    @app.before_request
    def protect_writes():
        if request.method in ('POST', 'PATCH', 'DELETE'):
            if not session.get('csrf') or not secrets.compare_digest(request.headers.get('X-Rewind-Token', ''), session['csrf']):
                return jsonify(error='This page has expired. Refresh it and try again.'), 403
            if request.path.startswith('/api/songs'):
                if not is_admin():
                    return jsonify(error='Sign in as admin to upload or manage songs.'), 401

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.path == '/' or request.path.startswith(('/api/', '/audio/', '/download/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        message = 'Each file must be 200 MB or smaller.' if error.code == 413 else error.description
        return jsonify(error=message), error.code

    @app.get('/')
    def index():
        return render_template('index.html', csrf=csrf_token(), admin=is_admin())

    @app.post('/api/admin/login')
    def admin_login():
        if not app.config['ADMIN_PASSWORD_HASH']:
            return jsonify(error='Admin access is not configured. Set the admin password hash on the server.'), 503
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify(error='Enter your admin username and password.'), 400
        now = time.monotonic()
        key = request.remote_addr or 'local'
        with attempts_lock:
            for address in list(attempts):
                if now - attempts[address][1] > 300:
                    del attempts[address]
            count, _ = attempts.get(key, (0, now))
            if count >= 5:
                return jsonify(error='Too many login attempts. Try again in five minutes.'), 429
            if len(attempts) >= 10000 and key not in attempts:
                return jsonify(error='Login is busy. Try again in five minutes.'), 429
            attempts[key] = (count + 1, now)
        username = str(data.get('username', ''))
        password = str(data.get('password', ''))
        if len(password) > 1024 or len(username) > 200:
            return jsonify(error='Incorrect username or password.'), 401
        try:
            valid_password = check_password_hash(app.config['ADMIN_PASSWORD_HASH'], password)
        except (ValueError, TypeError, AttributeError):
            return jsonify(error='Admin password configuration is invalid. Update it on the server.'), 503
        if not valid_password or not secrets.compare_digest(username.encode(), app.config['ADMIN_USER'].encode()):
            return jsonify(error='Incorrect username or password.'), 401
        with attempts_lock:
            attempts.pop(key, None)
        session.clear()
        session.permanent = True
        session['admin'] = app.config['ADMIN_USER']
        return jsonify(admin=True, csrf=csrf_token())

    @app.post('/api/admin/logout')
    def admin_logout():
        session.clear()
        return jsonify(admin=False, csrf=csrf_token())

    @app.get('/api/songs')
    def list_songs():
        rows = store.list_songs()
        preview = store.preview_id()
        unlocked = is_admin() or bool(listener_account())
        return jsonify([{**public(row), 'preview': row['id'] == preview, 'locked': not unlocked and row['id'] != preview} for row in rows])

    @app.post('/api/songs')
    def upload_song():
        audio = request.files.get('file')
        if not audio or not audio.filename:
            return jsonify(error='Choose an audio file first.'), 400
        ext = Path(audio.filename).suffix.lower()
        if ext not in ALLOWED:
            return jsonify(error='Use an MP3, M4A, FLAC, OGG or WAV audio file.'), 400
        song_id = uuid.uuid4().hex
        try:
            payload = audio.read(200 * 1024 * 1024 + 1)
            size = len(payload)
            if not 0 < size <= 200 * 1024 * 1024:
                raise ValueError('Each file must contain audio and be 200 MB or smaller.')
            try:
                parsed = AudioFile(io.BytesIO(payload), easy=True)
                if parsed is None or not parsed.info or parsed.info.length <= 0:
                    raise ValueError()
                duration = float(parsed.info.length)
            except Exception:
                raise ValueError('This file could not be read as audio. Try another file or export it as MP3 or WAV.')
            tags = parsed.tags or {}
            def tag(key, fallback=''):
                values = tags.get(key, [fallback])
                return str(values[0]) if values else fallback
            values = dict(request.form)
            values.setdefault('title', tag('title', Path(audio.filename).stem))
            values.setdefault('artist', tag('artist', 'Unknown artist'))
            values.setdefault('album', tag('album'))
            values.setdefault('year', tag('date', '1990')[:4])
            info = metadata(values)
            title, artist, album, year, category = info
            original = secure_filename(audio.filename) or 'audio' + ext
            if len(original) > 255:
                original = original[:255 - len(ext)] + ext
            record = dict(id=song_id, original=original,
                          title=title, artist=artist, album=album, year=year, category=category, duration=duration, size=size,
                          sha256=hashlib.sha256(payload).hexdigest(), favorite=False,
                          created_at=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'))
            store.insert(record, payload)
            return jsonify(public(record)), 201
        except DuplicateSong as error:
            return jsonify(error=str(error)), 409
        except StorageError:
            raise
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except Exception:
            app.logger.error('Unable to process uploaded audio')
            return jsonify(error='The song could not be saved. Check available disk space and try again.'), 500

    @app.patch('/api/songs/<song_id>')
    def update_song(song_id):
        row = song(song_id)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Provide song details as an object.'), 400
        try:
            info = metadata({**dict(row), **data})
            if 'favorite' in data:
                raise ValueError('Favorites are personal to this browser and are not changed through the shared library API.')
            favorite = bool(row['favorite'])
            store.update(song_id, (*info, int(favorite)))
            return jsonify(public(song(song_id)))
        except ValueError as error:
            return jsonify(error=str(error)), 400

    @app.delete('/api/songs/<song_id>')
    def delete_song(song_id):
        row = song(song_id)
        store.delete(song_id)
        return '', 204

    def send_audio(song_id, download=False):
        row = song(song_id)
        if not is_admin() and not listener_account() and song_id != store.preview_id():
            return jsonify(error='Create a listener account or sign in to hear more songs.', login_required=True), 401
        # BytesIO supports Werkzeug's single-range / If-Range / HEAD handling.
        # No persistent audio file is created on the Flask host.
        payload = store.audio(song_id)
        if payload is None:
            return jsonify(error='That song is no longer in your library.'), 404
        return send_file(io.BytesIO(payload), as_attachment=download,
                         download_name=row['original'], conditional=True, etag=row['sha256'])

    @app.get('/audio/<song_id>')
    def stream_song(song_id):
        return send_audio(song_id)

    @app.get('/download/<song_id>')
    def download_song(song_id):
        return send_audio(song_id, download=True)

    @app.errorhandler(StorageError)
    def storage_error(error):
        message = str(error) if is_admin() else 'The music library is temporarily unavailable. Please try again later.'
        return jsonify(error=message), 503

    return app


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run your Rewind music library')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5001)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, debug=False)
