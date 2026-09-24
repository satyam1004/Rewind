-- Run against the dedicated database you created for Rewind.
-- This adds a table only. It never replaces existing tables or rows.
CREATE TABLE IF NOT EXISTS songs (
    id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    original VARCHAR(255) NOT NULL,
    title VARCHAR(200) NOT NULL,
    artist VARCHAR(200) NOT NULL,
    album VARCHAR(200) NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    duration DOUBLE NOT NULL,
    size BIGINT UNSIGNED NOT NULL,
    sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    favorite BOOLEAN NOT NULL DEFAULT FALSE,
    created_at VARCHAR(32) CHARACTER SET ascii NOT NULL,
    category VARCHAR(20) NOT NULL DEFAULT '',
    audio_data LONGBLOB NOT NULL,
    UNIQUE KEY songs_sha256_unique (sha256),
    KEY songs_recent (created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
