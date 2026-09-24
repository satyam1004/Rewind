"""Test-only in-memory repository. This is NOT a MySQL integration test."""
from storage import DuplicateSong


class MemoryStore:
    def __init__(self):
        self.personal = {}
        self.listeners = {}
        self.rows = {}
        self.blobs = {}

    def list_songs(self):
        return sorted((dict(row) for row in self.rows.values()), key=lambda row: (row['created_at'], row['id']), reverse=True)

    def get(self, song_id):
        return dict(self.rows[song_id]) if song_id in self.rows else None

    def by_hash(self, digest):
        return next((dict(s) for s in self.rows.values() if s['sha256'] == digest), None)

    def audio(self, song_id):
        return self.blobs.get(song_id)

    def insert(self, row, audio):
        if row['id'] in self.rows or self.by_hash(row['sha256']):
            raise DuplicateSong('That exact audio file is already in your library.')
        self.rows[row['id']] = dict(row)
        self.blobs[row['id']] = audio

    def update(self, song_id, details):
        self.rows[song_id].update(dict(zip(['title', 'artist', 'album', 'year', 'category', 'favorite'], details)))

    def delete(self, song_id):
        self.rows.pop(song_id, None)
        self.blobs.pop(song_id, None)

    def preview_id(self):
        rows=sorted(self.rows.values(), key=lambda row:(row['created_at'],row['id']))
        return rows[0]['id'] if rows else None

    def listener_by_username(self, username):
        return next((dict(row) for row in self.listeners.values() if row['username']==username),None)

    def listener_by_id(self, listener_id):
        row=self.listeners.get(listener_id)
        return dict(id=row['id'],username=row['username']) if row else None

    def create_listener(self, listener_id, username, password_hash):
        if self.listener_by_username(username):
            raise DuplicateSong('Duplicate account')
        self.listeners[listener_id]=dict(id=listener_id,username=username,password_hash=password_hash)

    def personal_library(self, user_id):
        return [dict(row) for (owner,song_id),row in self.personal.items() if owner==user_id and song_id in self.rows]

    def personal_favorite(self, user_id, song_id, favorite):
        row=self.personal.setdefault((user_id,song_id),dict(song_id=song_id,favorite=False,play_count=0,last_played=None))
        row['favorite']=favorite

    def personal_play(self, user_id, song_id):
        from datetime import datetime,timezone
        row=self.personal.setdefault((user_id,song_id),dict(song_id=song_id,favorite=False,play_count=0,last_played=None))
        now=datetime.now(timezone.utc)
        if not row['last_played'] or (now-datetime.fromisoformat(row['last_played'].replace('Z','+00:00'))).total_seconds()>30:
            row['play_count']+=1
        row['last_played']=now.isoformat().replace('+00:00','Z')
