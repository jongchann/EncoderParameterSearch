# 09. Implementation Progress

## Status Summary

Backend implementation has progressed through Step 12 of the MVP implementation plan for the backend-only mock path.
Step 11 has started with an Android client MVP skeleton, but Android real-device work is intentionally deferred.

Completed:

- Step 1: Project Skeleton
- Step 2: Metadata Schema
- Step 3: Session API
- Step 4: Capability Registration and Search Space Creation
- Step 5: OptimizerService
- Step 6: Trial Assignment API
- Step 7: Trial Result Upload
- Step 8: EvaluationService
- Step 9: Baseline Selection
- Step 10: Pareto Calculation and ReportService
- Step 12: Backend-only Mock Closed-loop Integration

Started:

- Step 11: Android Client MVP
- Step 13: RAG Agent foundation

## Current Verification

Current backend test command:

```sh
./scripts/test.sh
```

Latest verified result:

```text
Ran 71 tests
OK
```

The project is configured to run through `.venv/bin/python` only.

Current Android verification status:

- Android real-device work is deferred while the backend-only mock loop is stabilized.
- Android app mock mode was added so the manual UI flow can be checked without a backend server, Android encoder, or artifact upload.
- The mock flow displays each button result as formatted JSON on screen.
- A physical Android device connection was attempted by the user.
- The current shell cannot verify the device because `adb` is not available on `PATH`.
- Android CLI build/install is also blocked in this environment because `gradle` and `sdkmanager` are not available on `PATH`.
- Helper scripts were added so the next environment check is explicit:
  - `./scripts/check_android_tools.sh`
  - `./scripts/run_server_for_device.sh`

Design-to-implementation gap tracking:

- The current follow-up implementation gaps are tracked in [14_implementation_gap_review.md](14_implementation_gap_review.md).
- The highest-priority backend gaps before Step 12, upload-to-evaluation linkage and stronger session completion gates, have been implemented for the backend mock path.

## Implemented Backend Surface

HTTP endpoints currently implemented:

- `GET /health`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/constraints`
- `POST /sessions/{session_id}/capabilities`
- `GET /sessions/{session_id}/trials/next`
- `POST /sessions/{session_id}/trials/{trial_id}/result`
- `POST /sessions/{session_id}/trials/{trial_id}/failure`
- `GET /sessions/{session_id}/report`

Implemented services:

- `SessionService`
- `ConstraintFilter`
- `SearchSpaceBuilder`
- `OptimizerService`
- `TrialService`
- `EvaluationService`
- `BaselineService`
- `ReportService`
- `RagOutputService`
- `MockRagAgentService`

Implemented storage:

- SQLite-backed `MetadataStore`
- Filesystem-backed `ArtifactStore`
- `rag_outputs` metadata table
- `aiops_events` metadata table
- RAG retrieval snapshot artifacts under `artifacts/{session_id}/rag/retrieval_snapshots/`

Implemented Android client skeleton:

- Gradle Android application project under `android-client/`
- `CapabilityReporter`
- `EncoderParameterProxy`
- `NoOpExtensionStrategy`
- `TrialRunner`
- `SyntheticSurfaceSourceEncoder`
- `AppClient`, `NetworkAppClient`, and `MockAppClient` to switch between real backend execution and local mock UI verification
- Minimal `MainActivity` manual runner with session creation, capability registration, and one-trial execution
- `MainActivity` result display that shows the latest response or failure message on screen
- Multipart artifact upload client
- Device-access backend helper script: `scripts/run_server_for_device.sh`
- Android tool/device check helper script: `scripts/check_android_tools.sh`

## Step Notes

### Step 1: Project Skeleton

Implemented backend package layout, `.venv`-based scripts, standard-library HTTP server, `/health`, and SQLite initialization.

Note: FastAPI remains declared in `pyproject.toml`, but the current Step 1-10 implementation uses the Python standard library HTTP server because the local system lacks complete `python3.14-venv`/pip bootstrap support.

### Step 2: Metadata Schema

Implemented SQLite tables for sessions, devices, capabilities, search spaces, constraint decisions, trials, observations, optimizer recommendations, and report metadata.

JSON round-trip behavior is covered by tests for requested params, applied params, raw payloads, recommendation metadata, and report metadata.

### Step 3: Session API

Implemented session create/read, constraints read, and clear trial-generation error before capability registration.

Session status includes trial counts and current search space version.

### Step 4: Capability Registration and Search Space Creation

Implemented capability registration, default MVP search space creation, constraint decision storage, and transition to `ready`.

Default search space:

- `bitrate_kbps`: `1000-12000`
- `i_frame_interval_sec`: `1-5`
- `profile`: values reported by capability only

MVP-excluded parameters are stored as rejected constraint decisions.

### Step 5: OptimizerService

Implemented deterministic cold-start recommendation generation.

Current behavior:

- Avoids duplicate recommendations.
- Avoids failed parameter combinations.
- Avoids evaluated parameter combinations.
- Stores recommendations with `phase`, `seed`, and `search_space_version`.

### Step 6: Trial Assignment API

Implemented trial assignment through `GET /sessions/{session_id}/trials/next`.

The backend now creates assigned trials, links optimizer recommendations, stores search space version, and transitions sessions to `running`.

### Step 7: Trial Result Upload

Implemented multipart trial result upload and JSON failure reporting.

Artifacts are stored under:

```text
artifacts/{session_id}/trials/{trial_id}/
```

Stored files:

- `output.h264`
- `requested_params.json`
- `applied_params.json`
- `encoder_log.json`

The HTTP upload endpoint now triggers mock evaluation immediately after a successful upload. The lower-level `TrialService.upload_result` still models the intermediate `uploaded` state for service-level testing and future asynchronous evaluation options.

Failure handling marks the trial and linked optimizer recommendation as failed without failing the session.

### Step 8: EvaluationService

Implemented mock and real evaluator boundaries.

Current behavior:

- Missing artifact is recorded as evaluation failure.
- Mock evaluator creates bitrate/VMAF observations and supports a 15-trial lifecycle test.
- Real evaluator preserves command/stdout/stderr/returncode logs on failure.

### Step 9: Baseline Selection

Implemented baseline selection.

Priority:

1. First Android default encoder settings trial.
2. Evaluated cold-start trial closest to center bitrate.

The selected baseline updates `session.baseline_trial_id`, marks the baseline observation, and records the selection reason in report metadata.

Session completion is guarded so a session cannot become `completed` without a baseline observation, at least 15 evaluated trials, final report metadata, and a `completed_at` timestamp.

### Step 10: Pareto Calculation and ReportService

Implemented Pareto Set calculation, VMAF-bitrate plot data generation, baseline comparison, Markdown report generation, report trust-level sections, report version metadata, and `GET /sessions/{session_id}/report`.

The report endpoint returns Pareto data, baseline comparison, report path, and report metadata so version/trust information can be reviewed through the API.

Reports are saved to:

```text
artifacts/{session_id}/report.md
```

The report includes:

- Session metadata
- Report version metadata
- Trust level summary
- Raw metric sections
- Device and capability summary
- Search space and excluded parameters
- Trial result table
- Requested/applied parameter comparison
- Observation table
- VMAF-bitrate plot data
- Deterministic result sections
- Pareto Set
- Baseline comparison
- AI-assisted narrative placeholder marked as not available
- Audit trail section
- Optimizer recommendation audit trail
- Failed trial summary

Final report metadata now stores:

- `report_template_version`
- `search_space_version`
- `evaluator_mode`
- `rag_status`
- `trust_level_counts`
- `source_less_narrative_count`

RAG-specific `prompt_version` and `retrieval_snapshot_path` are filled from recorded `RagOutput` rows when available. `retrieval_corpus_version` remains a placeholder until corpus versioning is implemented.
When a recorded RAG report section exists, ReportService now fills prompt/snapshot metadata from `RagOutput` and marks AI-assisted narrative as available.

### Step 11: Android Client MVP

Implemented a manual Android smoke-test app under `android-client/`.

Current behavior:

- The app can create a session, register AVC encoder capability, and run one trial through button actions.
- `Mock mode` is enabled by default so the UI can be checked without backend or encoder dependencies.
- In mock mode:
  - `Create session` returns `mock_sess_001`.
  - `Register capability` returns a ready mock capability response.
  - `Run one trial` returns an uploaded mock trial with requested params, applied params, and a mock artifact path.
- The latest action result is displayed as formatted JSON in the app so test output can be inspected directly.
- Disabling `Mock mode` uses `NetworkAppClient`, which preserves the existing backend and synthetic encoder path.

Current verification:

- Backend regression tests were rerun after the Android mock UI, backend mock closed-loop, report trust metadata, and RAG guardrail foundation changes.
- Result: `Ran 71 tests`, `OK`.
- Android compilation and installation are still pending because Android command-line tools are unavailable in the current shell.

### Step 12: Backend-only Mock Closed-loop Integration

Implemented a backend-only mock closed-loop path while Android real-device work is deferred.

Current behavior:

- `POST /sessions/{session_id}/trials/{trial_id}/result` stores artifact metadata and immediately evaluates the trial with `MockEvaluator`.
- Successful HTTP uploads now create an observation and move the trial to `evaluated`.
- The optimizer avoids parameters already evaluated or failed, so repeated `next trial -> upload result` calls advance through unused candidates.
- `BaselineService.complete_session` now requires 15 evaluated trials, a selected baseline observation, final report metadata, and records `completed_at`.
- `tests/test_step_12_backend_mock_closed_loop.py` verifies a 15-trial HTTP mock loop through report generation and completion.

### Step 13: RAG Agent Foundation

Started the RAG/AI guardrail implementation with storage, policy gates, retrieval snapshots, and a mock generator, without adding a live LLM dependency.

Current behavior:

- `rag_outputs` stores RAG output type, payload, sources, prompt version, retrieval snapshot path, status, and optional trial link.
- `aiops_events` stores guardrail pass/block events with component, event type, severity, and JSON payload.
- `RagOutputService.record_output` validates output type, required schema keys, prompt version, retrieval snapshot path, and source references.
- Valid RAG output is stored as `recorded` and emits `guardrail_passed`.
- Schema-invalid or source-less RAG output is stored as `ignored` and emits `guardrail_blocked`.
- Source-less constraint candidates do not create `ConstraintDecision` rows and do not change search space versions.
- Recorded `report_section` output is surfaced in final report metadata and in the AI-assisted narrative section.
- `MockRagAgentService` uses an allowlisted mock corpus with `mock_rag_corpus_v1`.
- Mock retrieval snapshots are saved under `rag/retrieval_snapshots/` with deterministic snapshot ids.
- The mock generator can create `constraint_candidate`, `failure_analysis`, and `report_section` outputs.
- Report metadata now includes `retrieval_corpus_version` when a RAG snapshot is available.
- `tests/test_step_13_rag_guardrails.py` verifies valid, source-less, schema-invalid, and report metadata linkage behavior.
- `tests/test_step_13_mock_rag_agent.py` verifies mock corpus versioning, snapshot artifacts, supported output types, AI-Ops event versioning, and report metadata linkage.

## Known Gaps

- Baseline selection and final session completion are currently service-level operations, not exposed as HTTP endpoints.
- Android client has not been compiled in this environment.
- `adb`, `gradle`, and `sdkmanager` were not available on the current shell `PATH`.
- Android mock mode has not yet been opened in Android Studio or on a device/emulator from this shell.
- End-to-end real Android encoding has not been verified.
- One real Android device artifact upload has not been verified.
- Android client currently uses a synthetic smoke-test source, not the final target input video source.
- Real VMAF parsing is not implemented; real evaluator currently preserves failure logs.
- Live RAG retrieval and LLM generation are not implemented yet.
- RAG retrieval currently uses a mock allowlisted corpus rather than a real document index.
- FastAPI dependency is declared but not currently used by the running server.

## Recommended Next Step

Choose one of these paths:

1. Add live/local document retrieval behind the existing mock RAG service boundary.
2. Add input video checksum/reference metadata before real VMAF evaluation.
3. Open `android-client/` in Android Studio and run the app with `Mock mode` enabled to visually confirm the button flow and JSON result display.
4. Finish Step 11 by making Android SDK tools available on `PATH`, compiling the Android project, and running one real-device upload with `Mock mode` disabled.
5. Revisit the backend server framework and switch from the current standard-library server to FastAPI once `.venv`/pip bootstrap is fixed.
