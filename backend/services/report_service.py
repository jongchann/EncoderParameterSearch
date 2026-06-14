import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class ReportError(Exception):
    pass


REPORT_TEMPLATE_VERSION = "report_template_v1"


class ReportService:
    def __init__(self, store: MetadataStore, artifact_store: ArtifactStore) -> None:
        self.store = store
        self.artifact_store = artifact_store

    def generate_report(self, session_id: str) -> dict[str, Any]:
        session = self.store.get("sessions", "session_id", session_id)
        if session is None:
            raise ReportError("Session not found.")

        trials = self.store.list_trials_with_optional_observations(session_id)
        observations = self.store.list_observations_for_session(session_id)
        pareto_set = self.calculate_pareto_set(observations)
        baseline_comparison = self._baseline_comparison(session, observations, pareto_set)
        rag_summary = self._rag_summary(session_id)
        trust_level_summary = self._trust_level_summary(rag_summary)
        report_metadata = self._report_metadata(
            session,
            observations,
            pareto_set,
            trust_level_summary,
            rag_summary,
        )
        plot_data = [
            {
                "trial_id": observation["trial_id"],
                "bitrate_kbps": observation["bitrate_kbps"],
                "vmaf": observation["vmaf"],
            }
            for observation in observations
        ]

        markdown = self._render_markdown(
            session_id=session_id,
            session=session,
            trials=trials,
            observations=observations,
            pareto_set=pareto_set,
            baseline_comparison=baseline_comparison,
            plot_data=plot_data,
            report_metadata=report_metadata,
            trust_level_summary=trust_level_summary,
            rag_summary=rag_summary,
        )
        report_path = self.artifact_store.save_report(session_id, markdown)
        self.store.create(
            "report_metadata",
            {
                "report_id": f"report_{uuid4().hex[:12]}",
                "session_id": session_id,
                "report_path": str(report_path),
                "metadata": report_metadata,
            },
        )

        return {
            "session_id": session_id,
            "pareto_set": pareto_set,
            "baseline_comparison": baseline_comparison,
            "plot_data": plot_data,
            "report_path": str(report_path),
            "markdown": markdown,
            "metadata": report_metadata,
        }

    def calculate_pareto_set(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pareto = []
        for candidate in observations:
            dominated = False
            for challenger in observations:
                if challenger["observation_id"] == candidate["observation_id"]:
                    continue
                bitrate_no_worse = challenger["bitrate_kbps"] <= candidate["bitrate_kbps"]
                vmaf_no_worse = challenger["vmaf"] >= candidate["vmaf"]
                strictly_better = (
                    challenger["bitrate_kbps"] < candidate["bitrate_kbps"]
                    or challenger["vmaf"] > candidate["vmaf"]
                )
                if bitrate_no_worse and vmaf_no_worse and strictly_better:
                    dominated = True
                    break
            if not dominated:
                pareto.append(self._observation_summary(candidate))

        return sorted(pareto, key=lambda item: (item["bitrate_kbps"], -item["vmaf"]))

    def _baseline_comparison(
        self,
        session: dict[str, Any],
        observations: list[dict[str, Any]],
        pareto_set: list[dict[str, Any]],
    ) -> dict[str, Any]:
        baseline = next(
            (
                observation
                for observation in observations
                if observation["trial_id"] == session["baseline_trial_id"]
                or observation["is_baseline"] == 1
            ),
            None,
        )
        if baseline is None:
            return {
                "status": "missing_baseline",
                "bd_rate": "insufficient_points",
                "rows": [],
            }

        rows = []
        for observation in pareto_set:
            rows.append(
                {
                    "trial_id": observation["trial_id"],
                    "delta_bitrate_kbps": round(
                        observation["bitrate_kbps"] - baseline["bitrate_kbps"],
                        3,
                    ),
                    "delta_vmaf": round(observation["vmaf"] - baseline["vmaf"], 3),
                }
            )

        return {
            "baseline_trial_id": baseline["trial_id"],
            "baseline_bitrate_kbps": baseline["bitrate_kbps"],
            "baseline_vmaf": baseline["vmaf"],
            "bd_rate": "insufficient_points",
            "rows": rows,
        }

    def _render_markdown(
        self,
        session_id: str,
        session: dict[str, Any],
        trials: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        pareto_set: list[dict[str, Any]],
        baseline_comparison: dict[str, Any],
        plot_data: list[dict[str, Any]],
        report_metadata: dict[str, Any],
        trust_level_summary: list[dict[str, Any]],
        rag_summary: dict[str, Any],
    ) -> str:
        constraints = self.store.list("constraint_decisions", "session_id", session_id)
        search_spaces = self.store.list("search_spaces", "session_id", session_id)
        recommendations = self.store.list("optimizer_recommendations", "session_id", session_id)
        devices = self.store.list("devices")
        capabilities = self.store.list("capabilities")
        failed_trials = [trial for trial in trials if trial["status"] == "failed"]

        return "\n".join(
            [
                "# Encoder Parameter Search Report",
                "",
                "## Session Metadata",
                f"- session_id: {session_id}",
                f"- status: {session['status']}",
                f"- baseline_trial_id: {session['baseline_trial_id']}",
                "",
                "## Report Version Metadata",
                self._format_bullets(
                    [
                        {
                            "report_template_version": report_metadata[
                                "report_template_version"
                            ],
                            "search_space_version": report_metadata["search_space_version"],
                            "evaluator_mode": report_metadata["evaluator_mode"],
                            "retrieval_corpus_version": report_metadata[
                                "retrieval_corpus_version"
                            ],
                            "rag_status": report_metadata["rag_status"],
                        }
                    ]
                ),
                "",
                "## Trust Level Summary",
                self._format_table(
                    trust_level_summary,
                    ["section", "trust_level", "source", "status"],
                ),
                "",
                "## Device and Capability Summary",
                self._format_bullets(devices + capabilities),
                "",
                "## Search Space and Excluded Parameters",
                self._format_bullets(search_spaces + constraints),
                "",
                "## Raw Metrics",
                "",
                "## Trial Result Table",
                self._format_table(trials, ["trial_id", "status", "artifact_path"]),
                "",
                "## Requested/Applied Parameter Comparison",
                self._format_table(trials, ["trial_id", "requested_params", "applied_params"]),
                "",
                "## Observation Table",
                self._format_table(observations, ["trial_id", "bitrate_kbps", "vmaf", "is_baseline"]),
                "",
                "## VMAF-Bitrate Plot Data",
                self._format_table(plot_data, ["trial_id", "bitrate_kbps", "vmaf"]),
                "",
                "## Deterministic Results",
                "",
                "## Pareto Set",
                self._format_table(pareto_set, ["trial_id", "bitrate_kbps", "vmaf"]),
                "",
                "## Baseline Comparison",
                self._format_bullets([baseline_comparison]),
                "",
                "## AI-assisted Narrative",
                self._format_ai_narrative(rag_summary),
                "",
                "## Audit Trail",
                "",
                "## Optimizer Recommendation Audit Trail",
                self._format_table(
                    recommendations,
                    ["optimizer_trial_id", "trial_id", "status", "recommended_params"],
                ),
                "",
                "## Failed Trial Summary",
                self._format_table(failed_trials, ["trial_id", "error_code", "error_message"]),
                "",
            ]
        )

    def _report_metadata(
        self,
        session: dict[str, Any],
        observations: list[dict[str, Any]],
        pareto_set: list[dict[str, Any]],
        trust_level_summary: list[dict[str, Any]],
        rag_summary: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": "final_report",
            "report_template_version": REPORT_TEMPLATE_VERSION,
            "search_space_version": session["search_space_version"],
            "evaluator_mode": self._evaluator_mode(observations),
            "prompt_version": rag_summary["prompt_version"],
            "retrieval_corpus_version": rag_summary["retrieval_corpus_version"],
            "retrieval_snapshot_path": rag_summary["retrieval_snapshot_path"],
            "rag_status": rag_summary["rag_status"],
            "rag_output_count": rag_summary["rag_output_count"],
            "rag_ignored_count": rag_summary["rag_ignored_count"],
            "trust_level_counts": self._trust_level_counts(trust_level_summary),
            "source_less_narrative_count": rag_summary["source_less_narrative_count"],
            "pareto_count": len(pareto_set),
            "baseline_trial_id": session["baseline_trial_id"],
        }

    def _trust_level_summary(self, rag_summary: dict[str, Any]) -> list[dict[str, Any]]:
        ai_status = "available" if rag_summary["report_sections"] else "not_available"
        return [
            {
                "section": "Trial Result Table",
                "trust_level": "raw_metric",
                "source": "MetadataStore",
                "status": "available",
            },
            {
                "section": "Observation Table",
                "trust_level": "raw_metric",
                "source": "EvaluationService",
                "status": "available",
            },
            {
                "section": "VMAF-Bitrate Plot Data",
                "trust_level": "raw_metric",
                "source": "EvaluationService",
                "status": "available",
            },
            {
                "section": "Pareto Set",
                "trust_level": "deterministic_derived_result",
                "source": "ReportService",
                "status": "available",
            },
            {
                "section": "Baseline Comparison",
                "trust_level": "deterministic_derived_result",
                "source": "ReportService",
                "status": "available",
            },
            {
                "section": "AI-assisted Narrative",
                "trust_level": "ai_assisted_narrative",
                "source": "RagAgentService",
                "status": ai_status,
            },
        ]

    def _trust_level_counts(self, trust_level_summary: list[dict[str, Any]]) -> dict[str, int]:
        counts = {
            "raw_metric": 0,
            "deterministic_derived_result": 0,
            "ai_assisted_narrative": 0,
        }
        for row in trust_level_summary:
            if row["status"] == "available":
                counts[row["trust_level"]] += 1
        return counts

    def _rag_summary(self, session_id: str) -> dict[str, Any]:
        rag_outputs = self.store.list("rag_outputs", "session_id", session_id)
        recorded = [output for output in rag_outputs if output["status"] != "ignored"]
        report_sections = [
            output
            for output in recorded
            if output["output_type"] == "report_section" and output["sources"]
        ]
        latest = self._latest_rag_output(report_sections or rag_outputs)
        snapshot_metadata = self._retrieval_snapshot_metadata(latest)

        if not rag_outputs:
            rag_status = "not_available"
        elif report_sections:
            rag_status = "available"
        elif recorded:
            rag_status = "recorded"
        else:
            rag_status = "ignored"

        return {
            "rag_status": rag_status,
            "rag_output_count": len(rag_outputs),
            "rag_ignored_count": len(
                [output for output in rag_outputs if output["status"] == "ignored"]
            ),
            "prompt_version": latest["prompt_version"] if latest else None,
            "retrieval_corpus_version": snapshot_metadata.get("retrieval_corpus_version"),
            "retrieval_snapshot_path": latest["retrieval_snapshot_path"] if latest else None,
            "source_less_narrative_count": len(
                [
                    output
                    for output in rag_outputs
                    if output["output_type"] == "report_section" and not output["sources"]
                ]
            ),
            "report_sections": report_sections,
        }

    def _latest_rag_output(self, rag_outputs: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rag_outputs:
            return None
        return sorted(rag_outputs, key=lambda output: output["created_at"])[-1]

    def _retrieval_snapshot_metadata(
        self,
        rag_output: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if rag_output is None:
            return {}
        snapshot_path = Path(rag_output["retrieval_snapshot_path"])
        if not snapshot_path.exists():
            return {}
        try:
            payload = json.loads(snapshot_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _format_ai_narrative(self, rag_summary: dict[str, Any]) -> str:
        if not rag_summary["report_sections"]:
            if rag_summary["rag_status"] == "ignored":
                return "AI-assisted Narrative: ignored by guardrails"
            return "AI-assisted Narrative: not available"

        rows = []
        for section in rag_summary["report_sections"]:
            rows.append(
                {
                    "rag_output_id": section["rag_output_id"],
                    "prompt_version": section["prompt_version"],
                    "interpretation": section["payload"]["interpretation"],
                    "source_count": len(section["sources"]),
                }
            )
        return self._format_bullets(rows)

    def _evaluator_mode(self, observations: list[dict[str, Any]]) -> str:
        modes = set()
        for observation in observations:
            log_path = observation.get("evaluation_log_path")
            if not log_path:
                continue
            path = Path(log_path)
            if not path.exists():
                continue
            try:
                log = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            mode = log.get("mode")
            if mode:
                modes.add(str(mode))

        if not modes:
            return "unknown"
        if len(modes) == 1:
            return next(iter(modes))
        return "mixed"

    def _observation_summary(self, observation: dict[str, Any]) -> dict[str, Any]:
        return {
            "trial_id": observation["trial_id"],
            "observation_id": observation["observation_id"],
            "bitrate_kbps": observation["bitrate_kbps"],
            "vmaf": observation["vmaf"],
        }

    def _format_bullets(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "- none"
        return "\n".join(f"- {row}" for row in rows)

    def _format_table(self, rows: list[dict[str, Any]], columns: list[str]) -> str:
        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        if not rows:
            return "\n".join([header, separator])
        body = [
            "| "
            + " | ".join(str(row.get(column, "")) for column in columns)
            + " |"
            for row in rows
        ]
        return "\n".join([header, separator, *body])
