import sqlite3
from contextlib import closing
from pathlib import Path


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    INSERT OR IGNORE INTO schema_migrations (version)
    VALUES (1)
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        input_video_id TEXT NOT NULL,
        target_codec TEXT NOT NULL,
        target_mime TEXT NOT NULL,
        status TEXT NOT NULL,
        search_space_version INTEGER,
        baseline_trial_id TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        android_version TEXT NOT NULL,
        soc_vendor TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capabilities (
        capability_id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        codec_name TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        profiles TEXT NOT NULL,
        bitrate_modes TEXT NOT NULL,
        supports_b_frame INTEGER NOT NULL,
        vendor_keys TEXT NOT NULL,
        raw_payload TEXT NOT NULL,
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_spaces (
        search_space_version INTEGER NOT NULL,
        session_id TEXT NOT NULL,
        parameters TEXT NOT NULL,
        created_from TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (session_id, search_space_version),
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS constraint_decisions (
        decision_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        parameter_name TEXT NOT NULL,
        decision TEXT NOT NULL,
        reason TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_ref TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trials (
        trial_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        trial_index INTEGER NOT NULL,
        status TEXT NOT NULL,
        requested_params TEXT NOT NULL,
        applied_params TEXT NOT NULL,
        applied_params_unknown TEXT NOT NULL,
        artifact_path TEXT,
        optimizer_trial_id TEXT,
        search_space_version INTEGER,
        error_code TEXT,
        error_message TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS observations (
        observation_id TEXT PRIMARY KEY,
        trial_id TEXT NOT NULL,
        bitrate_kbps REAL NOT NULL,
        vmaf REAL NOT NULL,
        evaluation_log_path TEXT,
        is_baseline INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS optimizer_recommendations (
        optimizer_trial_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        trial_id TEXT,
        search_space_version INTEGER NOT NULL,
        recommended_params TEXT NOT NULL,
        status TEXT NOT NULL,
        metadata TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id),
        FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS report_metadata (
        report_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        report_path TEXT NOT NULL,
        metadata TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rag_outputs (
        rag_output_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        trial_id TEXT,
        output_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        sources TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        retrieval_snapshot_path TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id),
        FOREIGN KEY (trial_id) REFERENCES trials(trial_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS aiops_events (
        event_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        component TEXT NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """,
)


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute("PRAGMA foreign_keys = ON")
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
