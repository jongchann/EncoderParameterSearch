# Encoder Parameter Search

Encoder Parameter Search는 Android hardware encoder의 parameter를 backend closed-loop로 탐색하고, bitrate 대비 VMAF trade-off가 개선된 Pareto-optimal 후보를 찾는 MVP 프로젝트다.

이 저장소의 설계 초점은 AI를 무조건적인 parameter 결정자로 쓰지 않는 것이다. Optimizer가 수치 결정을 맡고, ConstraintFilter가 안전 경계를 강제하며, RAG Agent는 문서 근거 기반 constraint 후보와 결과 설명을 보조한다.

## Design Documents

설계 문서는 [design/README.md](design/README.md)에서 순서대로 볼 수 있다.

평가자 관점에서 빠르게 읽을 핵심 문서는 다음과 같다.

- [00_design_overview.md](design/00_design_overview.md): 설계 범위와 핵심 결정
- [02_system_architecture.md](design/02_system_architecture.md): 전체 구조와 책임 분리
- [05_algorithm_and_rag_design.md](design/05_algorithm_and_rag_design.md): optimizer/RAG/constraint filter 계약
- [06_verification_plan.md](design/06_verification_plan.md): 검증 계획
- [09_implementation_progress.md](design/09_implementation_progress.md): 현재 구현 상태
- [10_design_review_and_evolution.md](design/10_design_review_and_evolution.md): 전체 설계 리뷰와 발전 방향
- [11_ai_guardrails_and_aiops.md](design/11_ai_guardrails_and_aiops.md): AI guardrails와 AI-Ops 적용 범위

## Current Status

Backend implementation has progressed through Step 10 of the MVP plan.

- Implemented: session/trial lifecycle, capability registration, search space creation, deterministic optimizer, multipart artifact upload, mock/real evaluator boundary, baseline selection, Pareto/report generation.
- Started: Android client MVP with manual smoke-test UI and mock mode.
- Pending: real Android closed-loop verification, real VMAF parsing, RAG Agent implementation.

See [09_implementation_progress.md](design/09_implementation_progress.md) for the latest detailed status.

## Python Environment

Use the project virtual environment only. Do not install or run backend dependencies with the system Python.

Set up the environment:

```sh
./scripts/bootstrap_venv.sh
```

Run tests:

```sh
./scripts/test.sh
```

Start the backend server:

```sh
./scripts/run_server.sh
```

The current backend server uses the Python standard library HTTP server so it can run in the constrained local environment. FastAPI remains declared in `pyproject.toml` as a future API framework option.

## Backend API Surface

```text
GET  /health
POST /sessions
GET  /sessions/{session_id}
GET  /sessions/{session_id}/constraints
POST /sessions/{session_id}/capabilities
GET  /sessions/{session_id}/trials/next
POST /sessions/{session_id}/trials/{trial_id}/result
POST /sessions/{session_id}/trials/{trial_id}/failure
GET  /sessions/{session_id}/report
```

## Android Notes

Android client code lives under `android-client/`.

Useful helper scripts:

```sh
./scripts/check_android_tools.sh
./scripts/run_server_for_device.sh
```

The Android mock mode is intended for UI flow verification without backend, encoder, or artifact upload dependencies. Real-device upload remains a Step 11 completion gate.
