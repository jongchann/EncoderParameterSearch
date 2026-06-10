import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from backend.storage.sqlite import initialize_database


JSON_COLUMNS = {
    "capabilities": {"profiles", "bitrate_modes", "vendor_keys", "raw_payload"},
    "search_spaces": {"parameters", "created_from"},
    "trials": {"requested_params", "applied_params", "applied_params_unknown"},
    "optimizer_recommendations": {"recommended_params", "metadata"},
    "report_metadata": {"metadata"},
}

ALLOWED_TABLES = {
    "sessions",
    "devices",
    "capabilities",
    "search_spaces",
    "constraint_decisions",
    "trials",
    "observations",
    "optimizer_recommendations",
    "report_metadata",
}


class MetadataStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        initialize_database(database_path)

    def create(self, table: str, values: dict[str, Any]) -> None:
        self._validate_table(table)
        encoded_values = self._encode_values(table, values)
        columns = tuple(encoded_values.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_names = ", ".join(columns)

        with self._connection() as connection:
            with connection:
                connection.execute(
                    f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})",
                    tuple(encoded_values[column] for column in columns),
                )

    def get(self, table: str, key_column: str, key_value: Any) -> dict[str, Any] | None:
        self._validate_table(table)
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {table} WHERE {key_column} = ?",
                (key_value,),
            ).fetchone()

        if row is None:
            return None

        return self._decode_row(table, dict(row))

    def list(
        self,
        table: str,
        key_column: str | None = None,
        key_value: Any | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_table(table)
        query = f"SELECT * FROM {table}"
        params: tuple[Any, ...] = ()
        if key_column is not None:
            query = f"{query} WHERE {key_column} = ?"
            params = (key_value,)

        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()

        return [self._decode_row(table, dict(row)) for row in rows]

    def count(
        self,
        table: str,
        key_column: str | None = None,
        key_value: Any | None = None,
    ) -> int:
        self._validate_table(table)
        query = f"SELECT COUNT(*) FROM {table}"
        params: tuple[Any, ...] = ()
        if key_column is not None:
            query = f"{query} WHERE {key_column} = ?"
            params = (key_value,)

        with self._connection() as connection:
            return int(connection.execute(query, params).fetchone()[0])

    def count_trials_by_status(self, session_id: str, status: str) -> int:
        with self._connection() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM trials
                    WHERE session_id = ? AND status = ?
                    """,
                    (session_id, status),
                ).fetchone()[0]
            )

    def list_trials_with_observations(self, session_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT trials.*, observations.observation_id
                FROM trials
                INNER JOIN observations ON observations.trial_id = trials.trial_id
                WHERE trials.session_id = ?
                """,
                (session_id,),
            ).fetchall()

        return [self._decode_row("trials", dict(row)) for row in rows]

    def list_observations_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    observations.*,
                    trials.session_id,
                    trials.requested_params,
                    trials.optimizer_trial_id,
                    optimizer_recommendations.metadata AS optimizer_metadata
                FROM observations
                INNER JOIN trials ON trials.trial_id = observations.trial_id
                LEFT JOIN optimizer_recommendations
                    ON optimizer_recommendations.optimizer_trial_id = trials.optimizer_trial_id
                WHERE trials.session_id = ?
                """,
                (session_id,),
            ).fetchall()

        observations = []
        for row in rows:
            decoded = dict(row)
            decoded["requested_params"] = json.loads(decoded["requested_params"])
            if decoded.get("optimizer_metadata") is not None:
                decoded["optimizer_metadata"] = json.loads(decoded["optimizer_metadata"])
            observations.append(decoded)
        return observations

    def list_trials_with_optional_observations(self, session_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    trials.*,
                    observations.observation_id,
                    observations.bitrate_kbps,
                    observations.vmaf,
                    observations.evaluation_log_path,
                    observations.is_baseline
                FROM trials
                LEFT JOIN observations ON observations.trial_id = trials.trial_id
                WHERE trials.session_id = ?
                ORDER BY trials.trial_index
                """,
                (session_id,),
            ).fetchall()

        trials = []
        for row in rows:
            decoded = self._decode_row("trials", dict(row))
            trials.append(decoded)
        return trials

    def update(
        self,
        table: str,
        key_column: str,
        key_value: Any,
        values: dict[str, Any],
    ) -> None:
        self._validate_table(table)
        encoded_values = self._encode_values(table, values)
        assignments = ", ".join(f"{column} = ?" for column in encoded_values)

        with self._connection() as connection:
            with connection:
                connection.execute(
                    f"UPDATE {table} SET {assignments} WHERE {key_column} = ?",
                    (*encoded_values.values(), key_value),
                )

    def delete(self, table: str, key_column: str, key_value: Any) -> None:
        self._validate_table(table)
        with self._connection() as connection:
            with connection:
                connection.execute(
                    f"DELETE FROM {table} WHERE {key_column} = ?",
                    (key_value,),
                )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        finally:
            connection.close()

    def _validate_table(self, table: str) -> None:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Unsupported metadata table: {table}")

    def _encode_values(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        json_columns = JSON_COLUMNS.get(table, set())
        return {
            key: json.dumps(value, sort_keys=True) if key in json_columns else value
            for key, value in values.items()
        }

    def _decode_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        for column in JSON_COLUMNS.get(table, set()):
            if row.get(column) is not None:
                row[column] = json.loads(row[column])
        return row
