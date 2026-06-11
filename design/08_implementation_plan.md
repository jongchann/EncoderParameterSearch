# 08. Implementation Plan

## Summary

Encoder Parameter Search MVP is currently defined by design and ADR documents. Implementation should proceed in this order:

1. Backend closed-loop skeleton
2. Android encoding integration
3. Evaluation and optimizer loop
4. RAG-assisted reporting

The MVP success criteria are fixed as follows.

- Run on one Android device and one H.264/AVC codec.
- Complete at least 15 evaluated trials for the same input video.
- Search over `bitrate_kbps`, `i_frame_interval_sec`, and capability-supported `profile`.
- Store requested and applied parameters separately.
- Store bitrate and VMAF observations.
- Generate a report with Pareto Set, baseline comparison, and audit trail.
- Use RAG only for constraint explanation and report assistance, not final parameter selection.

## Step 1: Project Skeleton

Create the Python backend package structure.

Suggested directories:

```text
backend/
  api/
  models/
  services/
  storage/
artifacts/
tests/
```

Use FastAPI or an equivalent Python API framework. Use SQLite for `MetadataStore` and the local filesystem for `ArtifactStore`.

Completion criteria:

- Backend server starts successfully.
- Empty SQLite database initializes successfully.
- `/health` or an equivalent endpoint passes.

## Step 2: Metadata Schema

Implement these metadata models first.

- `Session`
- `Device`
- `Capability`
- `SearchSpace`
- `ConstraintDecision`
- `Trial`
- `Observation`
- `OptimizerRecommendation`
- `ReportMetadata`

Use the documented state enums.

Session states:

- `created`
- `ready`
- `running`
- `completed`
- `failed`

Trial states:

- `pending`
- `assigned`
- `uploaded`
- `evaluated`
- `failed`

JSON fields should support `requested_params`, `applied_params`, `applied_params_unknown`, `raw_payload`, and service metadata.

Completion criteria:

- CRUD tests pass for all metadata models.
- JSON fields round-trip correctly.

## Step 3: Session API

Implement these APIs.

- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/constraints`

Behavior:

- A newly created session starts as `created`.
- Trial generation is not allowed before capability registration.
- Session status includes trial count, evaluated trial count, failed trial count, and current search space version.

Completion criteria:

- Session create/read tests pass.
- Calling next trial before capability registration returns a clear error.

## Step 4: Capability Registration and Search Space Creation

Implement this API.

- `POST /sessions/{session_id}/capabilities`

Implement these services.

- `ConstraintFilter`
- `SearchSpaceBuilder`

Default MVP search space:

- `bitrate_kbps`: integer range, default `1000-12000`
- `i_frame_interval_sec`: numeric range, default `1-5`
- `profile`: categorical values from capability `profiles` only

Rules:

- Exclude profiles that are not present in capability data.
- Exclude QP, B-frame, bitrate mode, and vendor extensions from the default MVP search space.
- Store excluded parameters and reasons as `ConstraintDecision` records.
- After search space creation, move the session to `ready`.

Completion criteria:

- Capability registration creates a search space version.
- Unsupported profile and vendor key rejection decisions are stored.
- Session transitions to `ready`.

## Step 5: OptimizerService

Start with a deterministic cold-start generator before adding Optuna NSGA-II or another multi-objective optimizer.

Cold-start behavior:

- Generate the first 5 trials to cover the search space broadly.
- Do not repeat evaluated or failed parameter combinations.
- Store each recommendation as `OptimizerRecommendation`.
- Include `phase`, `seed`, and `search_space_version` in recommendation metadata.

MOBO behavior:

- Maximize VMAF.
- Minimize measured bitrate.
- Exclude failed trials from objective data.
- Keep failed parameters in the duplicate-avoidance set.

Completion criteria:

- First 5 cold-start recommendations are unique.
- A new recommendation can be generated after an observation is added.
- No recommendation is outside the active search space.

## Step 6: Trial Assignment API

Implement this API.

- `GET /sessions/{session_id}/trials/next`

Behavior:

- Only `ready` or `running` sessions can receive trial assignments.
- Backend asks `OptimizerService` for the next recommendation.
- Backend validates the recommendation through `ConstraintFilter`.
- If accepted, create a Trial with status `assigned`.
- Move the session to `running`.
- Response includes `trial_id` and `requested_params`.

Completion criteria:

- Calling next trial creates a trial.
- Trial stores `optimizer_trial_id` and `search_space_version`.
- Rejected recommendations are never sent to the Android client.

## Step 7: Trial Result Upload

Implement these APIs.

- `POST /sessions/{session_id}/trials/{trial_id}/result`
- `POST /sessions/{session_id}/trials/{trial_id}/failure`

Use multipart upload for MVP.

Artifact layout:

```text
artifacts/
  {session_id}/
    trials/
      {trial_id}/
        output.h264
        encoder_log.json
        requested_params.json
        applied_params.json
```

Successful result behavior:

- Store the encoded artifact.
- Store `applied_params` and `applied_params_unknown`.
- Move trial status to `uploaded`.

Failure behavior:

- Store `error_code` and `error_message`.
- Move trial status to `failed`.
- Move linked optimizer recommendation status to `failed`.

Completion criteria:

- Uploaded artifact exists on disk.
- Failed trials do not fail the whole session.
- Requested, applied, and unknown parameters are stored separately.

## Step 8: EvaluationService

Evaluation behavior:

- Confirm uploaded artifact exists.
- Calculate bitrate.
- Measure VMAF using `ffmpeg` and `libvmaf`.
- Store evaluation log.
- Create an `Observation`.
- Move trial status to `evaluated`.

Provide two evaluator modes.

- `mock evaluator`: for lifecycle testing without Android.
- `real evaluator`: for actual `ffmpeg`/`libvmaf` execution.

Completion criteria:

- Missing artifact is recorded as evaluation failure.
- Mock evaluator supports a 15-trial lifecycle test.
- Real evaluator preserves logs on failure.

## Step 9: Baseline Selection

Baseline priority:

1. Android default encoder settings trial
2. Predefined baseline preset trial
3. Representative cold-start trial

MVP default:

- If possible, mark the first default-setting trial as baseline.
- Otherwise, choose the evaluated cold-start trial closest to the center bitrate.

Completion criteria:

- Completed sessions have `baseline_trial_id`.
- A session cannot become `completed` without a baseline observation.
- Baseline selection reason is stored.

## Step 10: Pareto Calculation and ReportService

Implement:

- Pareto Set calculation from evaluated observations.
- VMAF-bitrate plot data generation.
- Baseline comparison table.
- BD-Rate only when enough rate-quality points exist.
- VMAF-bitrate table or plot comparison when BD-Rate is insufficient.

Report should include:

- Session metadata
- Device and capability summary
- Search space and excluded parameters
- Trial result table
- Requested/applied parameter comparison
- Observation table
- Pareto Set
- Baseline comparison
- Optimizer recommendation audit trail
- Failed trial summary

Completion criteria:

- `GET /sessions/{session_id}/report` works.
- Markdown report is saved to `artifacts/{session_id}/report.md`.
- Pareto Set and baseline comparison are included.

## Step 11: Android Client MVP

Implement Android-side components.

- `CapabilityReporter`
- `EncoderParameterProxy`
- `NoOpExtensionStrategy`
- `TrialRunner`
- Artifact uploader

MVP parameter mapping:

- `bitrate_kbps` to `MediaFormat.KEY_BIT_RATE`
- `i_frame_interval_sec` to `MediaFormat.KEY_I_FRAME_INTERVAL`
- `profile` to profile-related key only when supported

Android flow:

1. Register capability with backend.
2. Fetch trial assignment from `/trials/next`.
3. Configure and run `MediaCodec`.
4. Upload encoded artifact and applied metadata.
5. Call failure endpoint on configure or encoding failure.

Completion criteria:

- One real Android device uploads one encoded artifact successfully.
- Requested, applied, and unknown metadata are sent.
- Android client does not measure VMAF.

## Step 12: Closed-loop Integration

Target lifecycle:

1. Create session.
2. Register Android capability.
3. Create search space.
4. Run baseline and cold-start trials.
5. Upload artifact.
6. Evaluate artifact on backend.
7. Update optimizer state.
8. Repeat next trial generation.
9. Reach 15 evaluated trials.
10. Generate Pareto result and report.
11. Mark session `completed`.

Completion criteria:

- At least 15 evaluated trials are recorded.
- Duplicate parameter recommendations are avoided.
- Failed trials do not block subsequent trials.
- Session becomes `completed` after report generation.

## Step 13: RAG Agent

Start with lightweight local retrieval.

Knowledge sources:

- Android CDD
- Android `MediaCodec` documentation
- Android `MediaFormat` documentation
- Vendor codec documentation, if available
- Current session trial log

RAG output schemas:

- Constraint candidate
- Failure analysis
- Final report section draft

Rules:

- Reject constraint candidates without source references.
- Store RAG output in `RagOutput` or an equivalent metadata model.
- Store prompt version and retrieval snapshot metadata for each RAG output.
- RAG must not directly choose final parameters.
- RAG failure must not stop the optimizer loop.
- Report must separate raw metrics, deterministic derived results, and RAG-assisted narrative.
- Guardrail block events should be stored as metadata or artifact JSON.
- Prompt, source, optimizer, evaluator, and report versions should be visible in report metadata.

Completion criteria:

- Source-less RAG constraints are not reflected in search space.
- Report includes RAG explanation and source references.
- Constraint decisions still record the filter's final accepted or rejected result.
- RAG output can be traced back to prompt version and retrieved sources.
- AI guardrail release gate passes on a fixed mock session fixture.

## Public Interfaces

Implement and keep stable:

- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/capabilities`
- `GET /sessions/{session_id}/trials/next`
- `POST /sessions/{session_id}/trials/{trial_id}/result`
- `POST /sessions/{session_id}/trials/{trial_id}/failure`
- `GET /sessions/{session_id}/constraints`
- `GET /sessions/{session_id}/report`

MVP parameter schema:

```json
{
  "bitrate_kbps": 4000,
  "i_frame_interval_sec": 2,
  "profile": "baseline"
}
```

Do not include these extension parameters in the MVP core path.

- `b_frame_count`
- `bitrate_mode`
- `qp_min`
- `qp_max`
- `vendor_extensions`

## Test Plan

Unit tests:

- `ConstraintFilter` excludes unsupported profiles and vendor keys.
- `ConstraintFilter` rejects RAG constraints without sources.
- `OptimizerService` avoids duplicate recommendations.
- `OptimizerService` avoids failed parameters.
- `EvaluationService` handles missing artifacts and ffmpeg failure.
- `ReportService` includes Pareto Set, baseline, and audit trail.
- AI guardrail tests block schema-invalid and source-less RAG output.
- AI-Ops metadata records prompt/source/search-space/evaluator/report versions.

Integration tests:

- Session creation, capability registration, and search space creation.
- Next trial, upload result, evaluation, and observation storage.
- Failed trial recording followed by next trial generation.
- 15-trial lifecycle with mock evaluator.
- Report generation followed by session completion.

Manual E2E tests:

- Register H.264/AVC capability from one Android device.
- Upload one real encoded artifact.
- Run real ffmpeg/libvmaf evaluation.
- Complete 15 closed-loop trials.
- Review final report.

## Assumptions

- Backend is implemented in Python.
- MetadataStore uses SQLite.
- ArtifactStore uses the local filesystem.
- First codec is H.264/AVC with MIME `video/avc`.
- First Android device count is one.
- `profile` is included only when confirmed by capability.
- VMAF is measured only on backend.
- BD-Rate is optional when there are not enough rate-quality points.
- RAG starts with the simplest local retrieval that satisfies source reference requirements.
