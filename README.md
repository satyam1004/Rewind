# Rewind — MySQL personal music library

Rewind uses Python Flask, **MySQL**, HTML, CSS and vanilla JavaScript. Both uploaded audio bytes and metadata are saved in MySQL. The responsive library keeps uploads, downloads, search, decade filters, favorites, editing and the interactive player.

## Where songs are stored

Each song is one row in the MySQL `songs` table. Its `audio_data` column is a **LONGBLOB** containing the original audio bytes; the same row contains its title, artist, album, year, duration, SHA-256 hash and a retained legacy favorite flag. Personal favorites now live in browser storage. The row is committed atomically with InnoDB. Listing the library fetches metadata only.

**MySQL consumes storage on the machine hosting the database. It does not automatically provide cloud capacity.** A MySQL server on your Mac still uses your Mac's disk. A separately configured remote MySQL server uses that server's disk. You supply and manage the database server; nothing is provisioned or publicly hosted by this project.

New uploads are not saved to the former `data/audio/` folder, and runtime code no longer uses SQLite. Flask may temporarily spool incoming multipart uploads to the operating system's temporary directory, and audio is buffered in memory for validation and playback responses. Those are temporary processing copies, not the permanent music library.

## Configure your own MySQL server

Requires Python 3.9+ and a MySQL 8.x server you set up separately. No server discovery, installation, startup or credential entry is required from Codex. Live MySQL integration was not tested, by your choice; the database-free verification is described below.

1. Create a dedicated empty database (for example, `rewind`) using `utf8mb4`. Create your own database account and password. Give that account `SELECT`, `INSERT`, `UPDATE` and `DELETE` on the Rewind database. Automatic schema setup also requires `CREATE`, `ALTER` and `INDEX` privileges on that dedicated database.
2. Set the **MySQL server** `max_allowed_packet` to at least **512 MB** to allow 200 MB uploads plus SQL escaping overhead. For example, your server configuration can include:

   ```ini
   [mysqld]
   max_allowed_packet=512M
   ```

   Apply that setting using your server's normal restart/configuration procedure. Existing connection/session settings may need reconnection. Your server's disk, memory and timeouts must also accommodate the files you upload.
3. From this project folder, install the Python dependencies:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   cp .env.example .env
   ```

4. Edit `.env` with your own host, port, database, user and password. The supplied file deliberately leaves credentials blank. Shell environment values override `.env`. If a password contains spaces or `#`, quote it in the dotenv file. Never commit `.env`; it is ignored by Git and excluded from the source ZIP.
5. Configure the website admin password using the **Admin access** instructions below. Then run the app. Rewind automatically creates the `songs` table and adds missing required columns when it connects. You do not need to run SQL manually. The database itself must already exist. The optional command `.venv/bin/python -m flask --app app:create_app init-db` remains available to trigger setup explicitly.
6. Start Rewind:

   ```sh
   ./run.sh
   ```

   Open **http://127.0.0.1:5001**. Keep the terminal open; Ctrl+C stops Flask. `./run.sh --port 5002` uses an alternative port. On Windows, use `.venv\Scripts\python app.py` after installing requirements with that interpreter.

The launcher installs missing Python packages only; **it does not install or start MySQL**, create a database, choose credentials, or migrate old data. It does automatically create/check the Rewind table and add missing columns inside your configured database. If configuration is missing, the interface opens with a friendly visitor message (configuration details are visible after admin login) instead of silently falling back to SQLite. After editing `.env`, restart Flask and refresh the browser. If the database is unreachable or uninitialized, API calls return a safe JSON error and status 503.

For a remote MySQL server, set `REWIND_MYSQL_SSL_CA` to its CA certificate file to enable certificate and hostname verification. Keep database access restricted to the Flask host. No database credentials are sent to the browser. Without that setting this configuration does not request verified TLS; use it only for trusted local database connections.

## Migrate the previous SQLite/files library

The existing `data/library.sqlite3` and `data/audio/` are preserved. **Nothing migrates automatically.** Do not delete the old folder until you have independently verified your MySQL copy and a backup.

1. Stop the old Flask app and stop changes to the source collection. Make a backup copy of its entire `data` folder.
2. Validate the old library without a MySQL connection or any writes:

   ```sh
   .venv/bin/python migrate_sqlite.py --source /absolute/path/to/old/data
   ```

3. After configuring MySQL, explicitly copy the validated library:

   ```sh
   .venv/bin/python migrate_sqlite.py --source /absolute/path/to/old/data --apply
   ```

4. Start Rewind, verify song counts, playback and downloads, and back up MySQL.

The migration opens SQLite read-only and checks file sizes and SHA-256 hashes before copying. It preserves song IDs, original filenames, metadata, creation times, favorite flags and byte-exact audio. Each row is committed atomically and its audio is read back for hash verification. Source files are never deleted or edited. Records already present by ID or audio hash are verified and skipped; existing MySQL metadata is never overwritten. An ID with different audio is reported as a conflict. A failure can leave earlier successfully copied target rows; rerunning safely skips those. Keep the source unchanged throughout migration and run one migration at a time.

## Use the library

- **Add music:** choose/drop MP3, M4A, FLAC, OGG or WAV files, up to 200 MB each. Pick a release year for the batch, then Add to library. Files upload separately with progress and individual errors. Duplicate hashes are rejected by a MySQL unique constraint.
- **Edit:** the **···** button edits title, artist, album and release year (1980–2009). Supported embedded tags supply title/artist/album initially; the selected batch year applies to every uploaded song. Untagged files use the filename and “Unknown artist.” Metadata edits do not rewrite embedded audio tags.
- **Browse:** decade, search (song/artist/album/year), sorting and Favorites work as before. The browser filters the metadata list; it does not download every audio BLOB.
- **Listen:** play/pause, seeking, previous/next, shuffle, repeat-current-song and desktop volume/mute. The queue stays in place while browsing. Normal queue completion stops playback; manual next/previous wraps. On phones/tablets use the device volume buttons. Space toggles playback when the page body has focus.
- **Download:** the down arrow returns the exact stored bytes with the original sanitized filename. Downloads and playback support HTTP byte ranges, conditional requests and HEAD.
- **Delete:** song details → Delete song → confirm permanently removes that MySQL row, including the audio BLOB. The original file you uploaded and any legacy SQLite/files copy remain untouched.

Browser codec support varies, especially for OGG, FLAC and M4A codecs. MP3 and PCM WAV are straightforward choices. Unsupported playback shows an error; downloads remain available. DRM-protected tracks are not supported.

## Performance and limits

The 200 MB per-file limit is intentional. This personal-use implementation buffers a complete BLOB in Python before Werkzeug serves a full or partial response, so even a seek request currently fetches the complete song from MySQL. Concurrent uploads/listeners multiply memory and bandwidth needs; escaping binary parameters may require substantially more memory than the file size. It is suitable for a small personal collection, not a large concurrent streaming service. MySQL storage is limited by your server capacity, backup strategy and configuration, not by the theoretical LONGBLOB limit.

## Phones and tablets

The responsive layout works on phones, tablets and laptops. Another device cannot access your computer's `127.0.0.1` address.

For trusted home Wi-Fi access, run `./run.sh --host 0.0.0.0` and open `http://YOUR_COMPUTER_LAN_IP:5001` on a phone/tablet on the same Wi-Fi. Keep Flask running and the computer awake. MySQL must also remain reachable from the Flask host. The phone connects to Flask, never directly to MySQL.

Guests can browse and play/download one shared preview song. Registered listeners can play/download the full collection and save personal favorites in their browser. **Only the signed-in admin can upload, edit song metadata or delete songs.** The website admin account is separate from the MySQL database account. Default loopback is computer-only; LAN mode is for a trusted network. Do not port-forward the Flask development server to the internet. Internet hosting still requires HTTPS, production serving and stronger shared rate limiting; nothing has been publicly deployed here.

## Backup

Back up the **MySQL database**, including BLOBs, with your MySQL backup tool. For example, use a consistent InnoDB dump with `mysqldump --single-transaction --hex-blob` and a sufficient client packet setting. Store credentials securely, use a password prompt rather than placing passwords in command arguments, and verify restoration into a separate database. Copying the old `data` folder no longer backs up new uploads. Preserve that old folder separately until migration has been verified.

## Database-free tests

```sh
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
node --check static/app.js
```

The tests use a test-only in-memory repository and mocked MySQL connections; **they do not connect to any MySQL server** and are not proof of live MySQL integration. Migration tests use synthetic temporary SQLite files and audio. Node is only needed for the optional JS syntax check.

After you configure MySQL, verify one real upload, seek/playback, byte-exact download, metadata persistence after restarting Flask and personal favorites after refreshing the browser, duplicate rejection and deletion of that test song. If migrating, validate song counts and sampled downloads against the retained source.

## Files

- `app.py`: Flask API, validation, audio responses and schema CLI.
- `storage.py`: environment configuration and parameterized MySQL repository.
- `schema.sql`: InnoDB table with metadata and LONGBLOB audio.
- `.env.example`: blank credential placeholders.
- `migrate_sqlite.py`: read-only validation and explicit resumable copy of the legacy library.
- `templates/`, `static/`: responsive interface and player.
- `tests/`: database-free backend, adapter and migration checks.
- `VERIFICATION.md`: what was and was not verified.

## Admin access

There is no default admin password. Generate your own hash locally:

```sh
.venv/bin/python admin_password.py
```

The command prompts twice without echoing your password. Copy the resulting hash into `REWIND_ADMIN_PASSWORD_HASH` in `.env`, and choose `REWIND_ADMIN_USER` (default username: `admin`). Never enter your MySQL password in the website login. Restart Flask after changing these settings.

The page shows **Admin login**. After a successful login, **Add music** and song editing controls appear. **Sign out** removes access. Upload, metadata-edit and delete endpoints enforce admin access independently of the UI. If no admin hash is configured, these operations stay disabled; there is no admin registration or default password. Listener self-registration is separate and never grants admin access. Signed-in listener favorites are private to their account and stored in MySQL. Guest and admin-local preferences are isolated from listener accounts.

Sessions use signed, HttpOnly, SameSite cookies and expire after eight hours. Request tokens are bound to each browser session and rotate on login/logout. Five failed login attempts from one client address trigger a five-minute cooldown within the running Flask process; restarting clears this local rate limiter. An optional long random `REWIND_SESSION_SECRET` keeps sessions valid across restarts; leaving it blank generates a new signing secret each start and logs everyone out. For HTTPS deployments set `REWIND_COOKIE_SECURE=1`. Local HTTP does not encrypt admin passwords in transit, so use it only on your computer or a trusted network.

## Automatic schema behavior

Setup runs on startup when MySQL credentials are configured. If the server is temporarily unavailable, later library operations retry. A MySQL advisory lock serializes schema setup across processes. Completed schema checks are cached until restart. Existing columns and rows are retained; missing columns and required unique keys are added. DDL additions are idempotent, but MySQL DDL commits independently: if a later check fails, earlier added columns remain safely available for the next attempt.

An incomplete existing table can be repaired structurally, but the app cannot invent missing audio bytes, song IDs or metadata. Such rows are preserved and an actionable error is shown. Existing incompatible column types and duplicate values may need manual repair from backup; the app never drops columns, overwrites audio or deletes rows to force setup to pass. Use a dedicated Rewind database. Automatic setup does not create the database, users or server, and it does not migrate the legacy SQLite collection unless you explicitly run the migration command.

## Ghazal, Travel and Party

The homepage has three category sections with song counts. Click one to filter the library; click it again or Clear filters to remove the filter. Categories combine with decade/search filters, and Play collection plays the visible songs. Admins choose one category per song (or Uncategorized) in the upload batch selector or Song details. Existing songs and legacy migrations default to Uncategorized, preserving previous data. The next configured MySQL connection automatically adds the category column with an empty default.

## Personal listening preferences

Tap a heart to save a favorite on this browser. Favorites, current track and position, queue order, volume, shuffle and repeat are stored locally. They survive refreshes but do not sync across devices, browser profiles or different website addresses. People sharing one browser profile share these preferences. Clearing website data removes them. If browser storage is blocked, controls still work for the current page and a message explains the limitation. Existing shared MySQL favorite flags are retained for data preservation but no longer exposed or changed by the library API.

Reopening the page restores the last track paused; choose Resume listening or Play to continue. Progress saves periodically and when pausing or leaving the page. Missing songs are removed from the restored queue.

Use the plus beside a song to add it to Up next. Open Up next to play a queued song, reorder upcoming tracks with the arrows, remove tracks, or clear upcoming songs. Reordering turns shuffle off so Next follows your order. Playing a collection or choosing a track from the library starts the visible collection as a new queue.

Visitors receive a friendly retry message when the library is unavailable. Signed-in admins can see the setup detail. Every shared library mutation requires admin access; favorites never call a mutation endpoint.

Run browser preference checks with `node --test tests/test_listener.cjs`, alongside `.venv/bin/python -m pytest -q`.

## Listener accounts and the free preview

Guests can browse all metadata and play/download one shared preview song: the earliest-added remaining song, with song ID breaking timestamp ties. It is marked Free preview. This is a fixed catalog preview, not a per-person listening counter. Refreshing, clearing cookies, or using a different browser does not unlock another song. If the preview is deleted, the next earliest remaining song becomes the preview.

Choose Listener sign in, then Create an account. Usernames use 3–32 letters, digits or underscores (case-insensitive); passwords use 12–128 characters. Registration signs the listener in. Accounts are stored in the new MySQL users table, created automatically with the schema setup. Passwords are hashed with PBKDF2-SHA256. No email address is collected and there is currently no self-service password recovery. The account only grants listening and downloading; uploading, editing and deleting remain admin-only.

The server checks access on both audio and download routes, including range and HEAD requests, and marks those responses no-store. Signing out clears active playback and restores preview-only access. Previously downloaded files cannot be revoked. Listener authentication uses the same HttpOnly, SameSite cookie protection and CSRF tokens as admin authentication, with separate roles. Account attempts are limited per IP in each server process; production multi-process hosting needs shared rate limiting.

Set a stable REWIND_SESSION_SECRET in the server environment to retain sessions across app restarts. Without it, restarting signs everyone out; account records remain in MySQL. Signed-in favorites and listening history are stored per account in MySQL. Playback position and queue remain browser-local but are separated by account.

After configuring MySQL, verify account creation, sign-out/sign-in after restarting Flask, one guest preview, full listener playback/downloads, and listener rejection from all song-management endpoints. Live MySQL account persistence has not yet been tested here.

## Personal favorites and Most played

For signed-in listeners, favorites and listening history are stored in the MySQL user_library table, keyed by user ID and song ID. The table is created automatically on connection. Every personal read/write derives its owner from the authenticated server session; a client cannot select another user ID. The uploaded song catalog remains shared. Favorites and Most played show only the current listener's activity and are available when signing into that account from another browser.

A play is recorded after roughly ten seconds of actual playback, or half the duration for shorter tracks. Seeking does not count as listening. Repeated reports for the same account and song within thirty seconds do not increment the count. Most played sorts that account's listened-to songs by play count. This is a listening convenience, not audited analytics.

Switching accounts or signing out clears the current personal view and active playback. Queue, volume and resume position stay locally under separate keys for each listener, guest and admin. Guest favorites are not automatically imported into an account, and legacy shared browser favorites are not assigned to listeners. No passwords or authentication tokens are stored in browser local storage.

This section supersedes earlier browser-only favorite descriptions. Verify real account-to-account isolation and persistence against your configured MySQL server before public use.
