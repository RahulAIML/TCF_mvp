"""The audio cache key must fit the old VARCHAR(64) column, and a database error must not drop the file."""
import hashlib
import sqlite3

import pytest

import audio_store
import database


def test_pitched_audio_is_deleted_once_and_user_tables_stay(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
    from sqlalchemy import text
    audio_store.ensure_schema()
    db = database.SessionLocal()
    db.execute(text("DELETE FROM content_registry WHERE module = 'system'"))
    db.commit()
    db.close()
    audio_store.save("old.mp3", b"ID3old-pitched", "audio/mpeg", "old-key")
    audio_store.forget_pitched_audio()
    assert audio_store.load("old.mp3") is None
    audio_store.save("fresh.mp3", b"ID3fresh", "audio/mpeg", "fresh-key")
    audio_store.forget_pitched_audio()
    assert audio_store.load("fresh.mp3") is not None


def test_postgres_migration_widens_script_key():
    sql = database.script_key_migration_sql("postgresql")
    assert sql == "ALTER TABLE stored_audio ALTER COLUMN script_key TYPE TEXT"
    assert database.script_key_migration_sql("sqlite") is None


def test_a_long_key_is_a_64_char_hash_that_fits_varchar(tmp_path, monkeypatch):
    long_key = "v3|François:fr-FR-male-1,Paul:fr-FR-male-2|" + ("ab" * 32)
    assert len(long_key) > 64
    stored = audio_store.stored_script_key(long_key)
    assert stored == hashlib.sha256(long_key.encode("utf-8")).hexdigest()
    assert len(stored) == 64

    # The length check is what Postgres enforces on VARCHAR(64). SQLite does not, so it is explicit here.
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE stored_audio (script_key VARCHAR(64) "
        "CHECK (script_key IS NULL OR length(script_key) <= 64))"
    )
    connection.execute("INSERT INTO stored_audio (script_key) VALUES (?)", (stored,))
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO stored_audio (script_key) VALUES (?)", (long_key,))

    url = audio_store.save("tcf_listening_longkey.mp3", b"ID3" + b"\x11" * 80, "audio/mpeg", long_key)
    assert url == "/audio/tcf_listening_longkey.mp3"
    assert audio_store.find_by_script(long_key) == url
    loaded = audio_store.load(url)
    assert loaded is not None and loaded[0].startswith(b"ID3")


def test_a_database_error_still_returns_the_audio_file(monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("value too long for type character varying(64)")

    monkeypatch.setattr(audio_store, "ensure_schema", lambda: None)
    real_session = audio_store.SessionLocal

    class _Broken:
        def execute(self, *args, **kwargs):
            explode()

        def commit(self):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(audio_store, "SessionLocal", lambda: _Broken())
    url = audio_store.save("tcf_listening_dbfail.mp3", b"ID3" + b"\x22" * 40, "audio/mpeg", "v3|" + "x" * 80)
    assert url == "/audio/tcf_listening_dbfail.mp3"
    assert audio_store.load(url)[0].startswith(b"ID3")
    monkeypatch.setattr(audio_store, "SessionLocal", real_session)
