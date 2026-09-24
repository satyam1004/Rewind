CREATE TABLE IF NOT EXISTS user_library (
    user_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    song_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    favorite BOOLEAN NOT NULL DEFAULT FALSE,
    play_count BIGINT UNSIGNED NOT NULL DEFAULT 0,
    last_played DATETIME(6) NULL,
    PRIMARY KEY (user_id, song_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
