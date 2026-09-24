# Verification — MySQL update, 11 September 2026

## Current MySQL implementation

The production code uses PyMySQL and an InnoDB `songs` table. Metadata and the original audio LONGBLOB are inserted in one transaction. No production SQLite/files fallback remains. Schema setup now runs automatically when the configured MySQL store connects. Legacy SQLite data is never automatically edited or migrated.

## Database-free checks

`python -m pytest -q`: **49 passed** at this checkpoint.

- Flask API contract using a **test-only in-memory repository**: upload/list/edit/favorite/delete, reused repository across app instances, exact download bytes, duplicate handling, invalid audio/extensions/metadata, size limits, missing rows/audio, safe filenames, mutation token checks, and database-failure JSON. Missing configuration is tested to return 503 without attempting a MySQL connection.
- Audio response checks using that repository: bounded, suffix and open-ended byte ranges, HTTP 206, invalid and multiple ranges (416), HEAD, ETag/304 and matching/nonmatching If-Range.
- **Mocked PyMySQL** checks: parameterized binary insertion, commit/rollback/connection closure, no BLOB retrieval for library listings, sanitized driver errors, required environment values, verified-TLS options, and the LONGBLOB/InnoDB schema declaration.
- Migration with synthetic temporary SQLite/audio sources: validation-only mode, copy/readback, rerun skipping, metadata/favorite/timestamp preservation, byte-for-byte source preservation, missing/corrupt files, path traversal, conflicting IDs and duplicate hashes. Default migration CLI is tested not to connect to MySQL, and missing sources are not created.

These tests verify application and adapter behavior; they do not prove that the schema or driver commands execute successfully on a live MySQL server.

## Browser/UI continuity

The player JavaScript and responsive CSS are unchanged by the database switch. Admin login/logout and conditional upload/edit controls have now been added. The responsive player and browsing layout are otherwise preserved. The previous SQLite version had browser verification of upload, WAV playback/seek, edits, favorites, filtering, and widths 320–1280px; that is historical UI evidence, **not MySQL integration evidence**. The current JavaScript syntax check passes.

## Deliberately not performed

Per the user's clarification, no live MySQL integration, server installation/provisioning/startup, credential request or database migration was performed. The user owns server setup and connection configuration. MySQL connections, actual SQL execution, BLOB capacity at 100 MB, runtime database durability, server packet limits and MySQL-backed browser flows still need verification against that configured server. No cloud service was purchased or deployed.

The retained legacy SQLite database and audio folder are the source for an optional non-destructive migration; running the updated application does not modify them.

## Automatic schema and admin update

43 database-free tests pass. Added coverage: visitor upload/edit/delete rejection; authenticated upload and public playback/download; logout; CSRF token rotation and per-browser isolation; wrong passwords and throttling; missing admin configuration; favorites cannot bypass the edit guard; additive missing-column setup; no ALTER on an already complete schema; and safe failure for incomplete existing rows. SQL tests remain mocked, with no live MySQL connection. No database server was installed, started or configured.

Browser verification for admin update used an isolated, test-only in-memory library, not MySQL: guest controls, admin sign-in, authenticated upload-panel access, sign-out, and hidden guest upload controls passed. A 400px logical mobile viewport had no page overflow, and no console errors were observed. Test server was stopped afterward. Automatic startup setup and cached schema initialization are also covered by tests.

## Category update
49 database-free tests pass. Added coverage for Ghazal/Travel/Party upload and readback, uncategorized defaults, category editing, favorite edits preserving category, and invalid category rejection. Schema gains an additive category column with an empty default; legacy migration supplies the same default. No live MySQL server was used.

Category browser checks used disposable in-memory storage: selected Party in the upload form, uploaded one generated WAV, filtered Party (one result), edited its category to Ghazal (removed from Party), and filtered Ghazal (one result). Counts followed the change; the 400px mobile layout had no horizontal page overflow and no browser console errors. The disposable test preview was then stopped. The actual MySQL-backed app remains open with the expected configuration error until user setup.

## Personal listening update — current verification

51 database-free Python tests and 7 Node browser-state tests pass. JavaScript syntax checks pass. New coverage verifies browser-store isolation, favorites and playback persistence, malformed or blocked storage, queue reorder boundaries, missing-song cleanup, retained legacy favorite flags, rejection of API favorite writes, and generic visitor versus detailed admin storage errors. Earlier shared-favorite behavior described above is superseded.

Browser QA used a temporary in-memory server with three synthetic WAV test tones, not MySQL or commercial songs. Verified a favorite after reload; paused playback restored at 2.02 seconds with a Resume listening prompt; reordered queue persisted through reload and Next selected the expected track; no browser errors were logged. At 320px viewport width the queue fit without horizontal page overflow and was visually inspected. Test tones are not bundled in the deliverable.

Live MySQL remains unconfigured and untested, as requested. The normal preview therefore shows the friendly unavailable message until the user configures their database.

## Listener registration and access update

Current automated result: 59 Python tests plus 7 Node preference tests pass. Additional database-free checks cover the shared preview rule; direct audio/download/Range/HEAD enforcement; registration and hashed password storage; login/logout and CSRF rotation; duplicate and invalid usernames; account attempt limits; deleted-account rejection; listener denial from all admin mutations; admin full access; parameterized account SQL; automatic users-table creation and stable preview selection. SQL checks are mocked and persistence across app instances uses MemoryStore.

Browser QA with temporary synthetic tones verified the locked-track registration prompt, account creation and immediate playback, listener login retained after reload, paused playback restoration, logout restoring the gate, and signing back in. Upload controls remained hidden. Listener dialog visually inspected at 320px with no horizontal page overflow; no browser error logs. No real accounts or songs were added to MySQL.

Earlier unrestricted-visitor behavior in this report is superseded by the one-preview policy. Live MySQL setup and integration remain the user's next step.

## Account-owned personal library — current result

62 Python tests and 8 Node preference tests pass; final JavaScript syntax check passes. Added tests use two separate authenticated clients to verify per-user favorite/history isolation, rejected owner-ID spoofing, saved data visible from another browser signed into the same account, anonymous/CSRF rejection, removed-song filtering, and account-scoped local playback. SQL checks assert user-scoped parameterized queries and play-count deduplication.

Browser QA with disposable accounts and synthetic tones: Alice saved a favorite and accumulated listening history; after logout and Bob registration in the same browser, Bob had zero favorites, empty Most played, and no Alice resume prompt. Signing back into Alice restored her favorite, history and resume prompt. No browser errors were logged. The production MySQL database was not configured or accessed for these tests.

The shared song catalog is unchanged; personal views now use the authenticated user, superseding older shared-browser descriptions in this document.

Vinyl animation: browser verified paused before playback, running while a synthetic song plays, and paused at the same angle afterward. JavaScript syntax passes. Existing reduced-motion preference disables animation.

Vinyl lift: browser computed styles confirmed a 22px right / 42px upward offset and running rotation during playback, returning to zero offset and paused rotation after pause. The movement uses a smooth, interruptible CSS transition.
