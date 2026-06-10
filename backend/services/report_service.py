from typing import Any
from uuid import uuid4

from backend.storage.artifact_store import ArtifactStore
from backend.storage.metadata_store import MetadataStore


class ReportError(Exception):
    pass


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
        )
        report_path = self.artifact_store.save_report(session_id, markdown)
        self.store.create(
            "report_metadata",
            {
                "report_id": f"report_{uuid4().hex[:12]}",
                "session_id": session_id,
                "report_path": str(report_path),
                "metadata": {
                    "type": "final_report",
                    "pareto_count": len(pareto_set),
                    "baseline_trial_id": session["baseline_trial_id"],
                },
            },
        )

        return {
            "session_id": session_id,
            "pareto_set": pareto_set,
            "baseline_comparison": baseline_comparison,
            "plot_data": plot_data,
            "report_path": str(report_path),
            "markdown": markdown,
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
                "## Device and Capability Summary",
                self._format_bullets(devices + capabilities),
                "",
                "## Search Space and Excluded Parameters",
                self._format_bullets(search_spaces + constraints),
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
                "## Pareto Set",
                self._format_table(pareto_set, ["trial_id", "bitrate_kbps", "vmaf"]),
                "",
                "## VMAF-Bitrate Plot Data",
                self._format_table(plot_data, ["trial_id", "bitrate_kbps", "vmaf"]),
                "",
                "## Baseline Comparison",
                self._format_bullets([baseline_comparison]),
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
