from typing import Any
from uuid import uuid4

from backend.storage.metadata_store import MetadataStore


class RagOutputError(Exception):
    pass


ALLOWED_OUTPUT_TYPES = {"constraint_candidate", "failure_analysis", "report_section"}


class RagOutputService:
    def __init__(self, store: MetadataStore) -> None:
        self.store = store

    def record_output(
        self,
        session_id: str,
        output_type: str,
        payload: dict[str, Any],
        sources: list[dict[str, Any]],
        prompt_version: str,
        retrieval_snapshot_path: str,
        retrieval_corpus_version: str | None = None,
        trial_id: str | None = None,
    ) -> dict[str, Any]:
        if self.store.get("sessions", "session_id", session_id) is None:
            raise RagOutputError("Session not found.")

        validation_error = self._validation_error(
            output_type,
            payload,
            sources,
            prompt_version,
            retrieval_snapshot_path,
        )
        status = "ignored" if validation_error else "recorded"
        rag_output_id = f"rag_{uuid4().hex[:12]}"
        stored_payload = (
            payload if validation_error is None else {"validation_error": validation_error}
        )

        self.store.create(
            "rag_outputs",
            {
                "rag_output_id": rag_output_id,
                "session_id": session_id,
                "trial_id": trial_id,
                "output_type": output_type,
                "payload": stored_payload,
                "sources": sources,
                "prompt_version": prompt_version,
                "retrieval_snapshot_path": retrieval_snapshot_path,
                "status": status,
            },
        )
        event = self._record_guardrail_event(
            session_id=session_id,
            rag_output_id=rag_output_id,
            output_type=output_type,
            prompt_version=prompt_version,
            retrieval_snapshot_path=retrieval_snapshot_path,
            retrieval_corpus_version=retrieval_corpus_version,
            source_count=len(sources),
            validation_error=validation_error,
        )

        return {
            "rag_output_id": rag_output_id,
            "session_id": session_id,
            "trial_id": trial_id,
            "output_type": output_type,
            "status": status,
            "aiops_event_id": event["event_id"],
            "validation_error": validation_error,
        }

    def _validation_error(
        self,
        output_type: str,
        payload: dict[str, Any],
        sources: list[dict[str, Any]],
        prompt_version: str,
        retrieval_snapshot_path: str,
    ) -> str | None:
        if output_type not in ALLOWED_OUTPUT_TYPES:
            return f"Unsupported RAG output type: {output_type}."
        if not prompt_version:
            return "Prompt version is required."
        if not retrieval_snapshot_path:
            return "Retrieval snapshot path is required."
        if not self._has_valid_sources(sources):
            return "At least one source reference is required."
        return self._payload_schema_error(output_type, payload)

    def _has_valid_sources(self, sources: list[dict[str, Any]]) -> bool:
        if not sources:
            return False
        return all(
            isinstance(source, dict)
            and bool(source.get("source_id"))
            and bool(source.get("source_type"))
            for source in sources
        )

    def _payload_schema_error(self, output_type: str, payload: dict[str, Any]) -> str | None:
        if output_type == "constraint_candidate":
            return self._require_keys(
                payload,
                ["parameter_name", "candidate_decision", "reason"],
            )
        if output_type == "failure_analysis":
            error = self._require_keys(
                payload,
                ["trial_id", "failure_type", "candidate_causes"],
            )
            if error is not None:
                return error
            if not isinstance(payload["candidate_causes"], list):
                return "candidate_causes must be a list."
            return None
        if output_type == "report_section":
            return self._require_keys(
                payload,
                ["facts", "derived_results", "interpretation"],
            )
        return None

    def _require_keys(self, payload: dict[str, Any], keys: list[str]) -> str | None:
        missing = [key for key in keys if key not in payload]
        if missing:
            return f"Missing required RAG payload keys: {', '.join(missing)}."
        return None

    def _record_guardrail_event(
        self,
        session_id: str,
        rag_output_id: str,
        output_type: str,
        prompt_version: str,
        retrieval_snapshot_path: str,
        retrieval_corpus_version: str | None,
        source_count: int,
        validation_error: str | None,
    ) -> dict[str, Any]:
        event_id = f"aiops_{uuid4().hex[:12]}"
        self.store.create(
            "aiops_events",
            {
                "event_id": event_id,
                "session_id": session_id,
                "component": "rag",
                "event_type": "guardrail_blocked"
                if validation_error
                else "guardrail_passed",
                "severity": "warning" if validation_error else "info",
                "payload": {
                    "rag_output_id": rag_output_id,
                    "output_type": output_type,
                    "prompt_version": prompt_version,
                    "retrieval_snapshot_path": retrieval_snapshot_path,
                    "retrieval_corpus_version": retrieval_corpus_version,
                    "source_count": source_count,
                    "validation_error": validation_error,
                },
            },
        )
        return {"event_id": event_id}
