import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root

    def save_trial_result(
        self,
        session_id: str,
        trial_id: str,
        artifact_bytes: bytes,
        requested_params: dict[str, Any],
        applied_params: dict[str, Any],
        encoder_log: dict[str, Any],
    ) -> Path:
        trial_directory = self.artifact_root / session_id / "trials" / trial_id
        trial_directory.mkdir(parents=True, exist_ok=True)

        output_path = trial_directory / "output.h264"
        output_path.write_bytes(artifact_bytes)
        self._write_json(trial_directory / "requested_params.json", requested_params)
        self._write_json(trial_directory / "applied_params.json", applied_params)
        self._write_json(trial_directory / "encoder_log.json", encoder_log)
        return output_path

    def save_evaluation_log(
        self,
        session_id: str,
        trial_id: str,
        payload: dict[str, Any],
    ) -> Path:
        trial_directory = self.artifact_root / session_id / "trials" / trial_id
        trial_directory.mkdir(parents=True, exist_ok=True)
        log_path = trial_directory / "evaluation_log.json"
        self._write_json(log_path, payload)
        return log_path

    def save_report(self, session_id: str, markdown: str) -> Path:
        session_directory = self.artifact_root / session_id
        session_directory.mkdir(parents=True, exist_ok=True)
        report_path = session_directory / "report.md"
        report_path.write_text(markdown, encoding="utf-8")
        return report_path

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
