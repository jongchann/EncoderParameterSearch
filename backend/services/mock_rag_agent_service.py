from hashlib import sha256
from pathlib import Path
from typing import Any

from backend.services.rag_output_service import RagOutputService
from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


MOCK_RETRIEVAL_CORPUS_VERSION = "mock_rag_corpus_v1"
CONSTRAINT_PROMPT_VERSION = "constraint_candidate_v1"
FAILURE_PROMPT_VERSION = "failure_analysis_v1"
REPORT_PROMPT_VERSION = "report_section_v1"


MOCK_CORPUS = [
    {
        "source_id": "mock-corpus:capability-b-frame",
        "source_type": "design_policy",
        "title": "MVP capability policy",
        "section": "B-frame support",
        "uri": "local-corpus/mock/capability_policy.md",
        "retrieval_score": 0.91,
        "retrieved_at": "2026-06-13T00:00:00Z",
        "text": "B-frame parameters must remain excluded unless capability discovery confirms support.",
    },
    {
        "source_id": "mock-corpus:report-trust-level",
        "source_type": "design_policy",
        "title": "Report trust level policy",
        "section": "AI-assisted narrative",
        "uri": "local-corpus/mock/report_policy.md",
        "retrieval_score": 0.88,
        "retrieved_at": "2026-06-13T00:00:00Z",
        "text": "RAG narrative may explain results but must not overwrite raw metrics or deterministic results.",
    },
    {
        "source_id": "mock-corpus:failure-analysis",
        "source_type": "design_policy",
        "title": "Failure analysis policy",
        "section": "Configure failure",
        "uri": "local-corpus/mock/failure_policy.md",
        "retrieval_score": 0.83,
        "retrieved_at": "2026-06-13T00:00:00Z",
        "text": "Configure failures should be treated as candidate causes unless corroborated by capability or logs.",
    },
]


class MockRagAgentService:
    def __init__(
        self,
        store: MetadataStore,
        artifact_store: ArtifactStore,
        rag_output_service: RagOutputService | None = None,
        corpus_version: str = MOCK_RETRIEVAL_CORPUS_VERSION,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.rag_output_service = rag_output_service or RagOutputService(store)
        self.corpus_version = corpus_version

    def generate_constraint_candidate(
        self,
        session_id: str,
        parameter_name: str,
    ) -> dict[str, Any]:
        query = f"constraint_candidate:{parameter_name}"
        sources, snapshot_path = self._retrieve_and_save_snapshot(session_id, query)
        return self.rag_output_service.record_output(
            session_id=session_id,
            output_type="constraint_candidate",
            payload={
                "parameter_name": parameter_name,
                "candidate_decision": "rejected",
                "reason": f"{parameter_name} is not enabled by the MVP capability policy.",
            },
            sources=sources,
            prompt_version=CONSTRAINT_PROMPT_VERSION,
            retrieval_snapshot_path=str(snapshot_path),
            retrieval_corpus_version=self.corpus_version,
        )

    def generate_failure_analysis(
        self,
        session_id: str,
        trial_id: str,
        failure_type: str,
    ) -> dict[str, Any]:
        query = f"failure_analysis:{trial_id}:{failure_type}"
        sources, snapshot_path = self._retrieve_and_save_snapshot(session_id, query)
        return self.rag_output_service.record_output(
            session_id=session_id,
            trial_id=trial_id,
            output_type="failure_analysis",
            payload={
                "trial_id": trial_id,
                "failure_type": failure_type,
                "candidate_causes": [
                    "Requested parameters may not be supported by the selected codec.",
                    "Capability discovery should be checked before promoting a new constraint.",
                ],
            },
            sources=sources,
            prompt_version=FAILURE_PROMPT_VERSION,
            retrieval_snapshot_path=str(snapshot_path),
            retrieval_corpus_version=self.corpus_version,
        )

    def generate_report_section(self, session_id: str) -> dict[str, Any]:
        query = "report_section:final_summary"
        sources, snapshot_path = self._retrieve_and_save_snapshot(session_id, query)
        return self.rag_output_service.record_output(
            session_id=session_id,
            output_type="report_section",
            payload={
                "facts": [],
                "derived_results": [],
                "interpretation": (
                    "The mock RAG summary is source-backed and does not modify raw metrics "
                    "or deterministic Pareto results."
                ),
            },
            sources=sources,
            prompt_version=REPORT_PROMPT_VERSION,
            retrieval_snapshot_path=str(snapshot_path),
            retrieval_corpus_version=self.corpus_version,
        )

    def _retrieve_and_save_snapshot(
        self,
        session_id: str,
        query: str,
    ) -> tuple[list[dict[str, Any]], Path]:
        sources = self._retrieve(query)
        snapshot_id = self._snapshot_id(session_id, query)
        snapshot_path = self.artifact_store.save_rag_retrieval_snapshot(
            session_id,
            snapshot_id,
            {
                "session_id": session_id,
                "query": query,
                "retrieval_corpus_version": self.corpus_version,
                "sources": sources,
            },
        )
        return sources, snapshot_path

    def _retrieve(self, query: str) -> list[dict[str, Any]]:
        if query.startswith("constraint_candidate"):
            documents = [MOCK_CORPUS[0]]
        elif query.startswith("failure_analysis"):
            documents = [MOCK_CORPUS[2], MOCK_CORPUS[0]]
        else:
            documents = [MOCK_CORPUS[1], MOCK_CORPUS[0]]
        return [
            {key: value for key, value in document.items() if key != "text"}
            for document in documents
        ]

    def _snapshot_id(self, session_id: str, query: str) -> str:
        digest = sha256(f"{session_id}|{self.corpus_version}|{query}".encode("utf-8"))
        return f"rag_snapshot_{digest.hexdigest()[:12]}"
