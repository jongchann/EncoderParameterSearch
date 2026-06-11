# 14. Implementation Gap Review

## 목적

이 문서는 설계 문서가 강화된 뒤 현재 구현에서 후속 작업으로 남은 gap을 정리한다.

핵심 원칙:

- 문서와 구현의 차이를 숨기지 않는다.
- 현재 Step에서 반드시 맞춰야 하는 항목과 후속 Step의 목표 항목을 분리한다.
- 각 gap은 관련 FR/NFR, 영향, 권장 조치, 완료 기준으로 추적한다.

## 요약

현재 backend는 Step 10까지 구현되어 있고 Android Step 11은 skeleton과 mock UI가 시작된 상태다. 설계 문서가 FR/NFR decision matrix, AI guardrails, AI-Ops까지 확장되면서 일부 항목은 아직 구현과 차이가 있다.

이 차이는 대부분 의도된 단계적 gap이다. 다만 Step 12 closed-loop integration 전에 처리해야 할 항목도 있다.

## 우선순위

| 우선순위 | Gap | 판단 |
| --- | --- | --- |
| P0 | Trial result upload 후 evaluation 연결 부재 | Step 12 전에 필요 |
| P0 | Session completion gate가 최소 trial/report 조건을 충분히 확인하지 않음 | Step 12 전에 필요 |
| P1 | Report metadata와 Markdown에 trust level/version 정보 부족 | Step 13 전에 설계 반영 필요 |
| P1 | `RagOutput`, `AiOpsEvent` 저장 모델 미구현 | Step 13 착수 시 필요 |
| P1 | 입력 영상 checksum/reference metadata 부족 | real evaluator 전 필요 |
| P2 | Real VMAF parsing 미구현 | real evaluation 단계에서 필요 |
| P2 | Android real-device artifact upload 미검증 | Step 11 완료 기준 |

## Gap 1: Upload 후 evaluation 연결

### 현 상태

`POST /sessions/{session_id}/trials/{trial_id}/result`는 artifact와 applied metadata를 저장하고 trial을 `uploaded` 상태로 만든다. 그러나 HTTP closed-loop에서는 바로 evaluation이 실행되지 않는다.

### 관련 요구사항

- FR-006 평가
- FR-004 Trial parameter 추천
- NFR-005 관측 가능성
- NFR-006 실패 허용성

### 영향

Backend API만으로는 `assigned -> uploaded -> evaluated -> next trial` loop가 자동으로 닫히지 않는다. Step 12 closed-loop integration을 위해서는 upload 이후 evaluation trigger가 필요하다.

### 후보

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Upload endpoint에서 mock evaluation 즉시 실행 | Step 12 mock loop가 단순해짐 | real evaluator 전환 시 분기 필요 | 단기 후보 |
| 별도 `POST /evaluate` endpoint 추가 | evaluation trigger가 명확함 | client 또는 orchestrator가 한 단계 더 호출해야 함 | 후보 |
| background worker 도입 | 실제 운영 구조에 가까움 | MVP에 과함 | 후속 |

### 권장 조치

Step 12에서는 별도 evaluation trigger 또는 upload 후 mock evaluation 자동 실행 중 하나를 명시적으로 선택한다. MVP simplicity를 우선하면 upload 후 mock evaluation 자동 실행이 가장 빠르다.

### 완료 기준

- HTTP API flow로 trial이 `uploaded`에서 `evaluated`까지 전환된다.
- Observation이 생성된다.
- Evaluation failure는 failed trial과 evaluation log로 남는다.
- 다음 trial recommendation이 evaluated/failed parameter를 반복하지 않는다.

## Gap 2: Session completion gate 강화

### 현 상태

`BaselineService.complete_session`은 baseline observation 존재 여부만 확인한다. 최소 evaluated trial 수, report 생성 여부, `completed_at` 기록은 아직 gate에 포함되지 않는다.

### 관련 요구사항

- FR-001 Session 관리
- FR-008 결과 리포트
- FR-010 Baseline 실행
- NFR-001 재현성

### 영향

문서상 completed session은 최소 trial 수, baseline, Pareto/report 조건을 만족해야 한다. 현재 구현은 session이 너무 일찍 completed 될 수 있다.

### 권장 조치

Completion gate를 다음 조건으로 강화한다.

- evaluated trial count >= 15
- baseline observation exists
- final report metadata exists
- Pareto Set calculation completed
- `completed_at` 저장

### 완료 기준

- baseline만 있는 session은 completed가 되지 않는다.
- report 없이 completed가 되지 않는다.
- completed session은 `completed_at`을 가진다.
- 실패 시 명확한 error message를 반환한다.

## Gap 3: Report trust level과 version metadata

### 현 상태

Report는 metric, Pareto, baseline, optimizer audit trail을 포함한다. 그러나 raw metric, deterministic derived result, AI-assisted narrative의 trust level 구분과 prompt/source/evaluator/report version metadata는 아직 없다.

### 관련 요구사항

- FR-008 결과 리포트
- NFR-001 재현성
- NFR-005 관측 가능성
- NFR-007 AI guardrails와 AI-Ops

### 영향

AI narrative가 추가되기 전에는 치명적이지 않다. 하지만 Step 13에서 RAG report section이 붙으면 trust level 구분이 report 신뢰도의 핵심이 된다.

### 권장 조치

ReportService를 다음 방향으로 확장한다.

- Report metadata에 `report_template_version`, `evaluator_mode`, `search_space_version` 추가
- Markdown에 `Raw Metrics`, `Deterministic Results`, `AI-assisted Narrative`, `Audit Trail` 구분 유지
- RAG narrative가 없으면 `AI-assisted Narrative: not available`로 명시
- source-less narrative count를 metadata에 기록

### 완료 기준

- final report에서 metric과 AI narrative를 구분할 수 있다.
- report metadata로 version 정보를 재검토할 수 있다.
- RAG 미사용 상태가 report에 명시된다.

## Gap 4: `RagOutput`와 `AiOpsEvent` 저장 모델

### 현 상태

설계 문서는 `RagOutput`과 `AiOpsEvent`를 정의했지만 SQLite schema와 MetadataStore에는 아직 table이 없다.

### 관련 요구사항

- FR-007 RAG Agent 보조
- NFR-002 안전성
- NFR-007 AI guardrails와 AI-Ops

### 영향

현재 RAG Agent가 미구현이므로 즉시 runtime gap은 아니다. Step 13 착수 시 첫 번째 schema 작업으로 처리해야 한다.

### 권장 조치

Step 13 시작 시 다음을 추가한다.

- `rag_outputs` table
- `aiops_events` table 또는 artifact JSON 저장 방식 결정
- JSON column round-trip test
- source-less RAG output rejected/ignored test

### 완료 기준

- RAG output이 prompt version, retrieval snapshot, sources와 함께 저장된다.
- guardrail pass/block event를 session 단위로 조회할 수 있다.
- source 없는 constraint candidate가 search space에 반영되지 않는다.

## Gap 5: 입력 영상 checksum/reference metadata

### 현 상태

Session은 `input_video_id`만 저장한다. 입력 영상 path, checksum, resolution/framerate/duration 같은 reference metadata는 아직 별도 모델로 관리하지 않는다.

### 관련 요구사항

- NFR-001 재현성
- FR-006 평가
- FR-008 결과 리포트

### 영향

Mock evaluator 단계에서는 큰 문제가 아니지만 real VMAF evaluation에서는 reference video identity가 중요하다.

### 권장 조치

real evaluator 연결 전 다음 중 하나를 선택한다.

- `input_videos` metadata table 추가
- session metadata에 `input_video_path`, `input_video_checksum` 추가
- artifact layout의 `input/` 아래 reference metadata JSON 저장

### 완료 기준

- final report에서 reference input identity를 확인할 수 있다.
- VMAF evaluation log가 reference checksum 또는 equivalent id를 포함한다.

## Gap 6: Real VMAF parsing

### 현 상태

Real evaluator는 `ffmpeg`/`libvmaf` command, stdout, stderr, return code를 보존하지만 VMAF score parsing은 아직 구현하지 않았다.

### 관련 요구사항

- FR-006 평가
- NFR-005 관측 가능성

### 영향

실제 Android artifact에 대한 objective metric 자동 산출이 아직 불가능하다.

### 권장 조치

Step 12 mock closed-loop가 안정화된 뒤 real evaluator contract를 ADR 004에서 확정하고 parsing을 구현한다.

### 완료 기준

- libvmaf output에서 VMAF score를 추출한다.
- parsing 실패 시 evaluation log와 error message가 남는다.
- mock evaluator와 real evaluator test가 분리되어 통과한다.

## Gap 7: Android real-device verification

### 현 상태

Android client skeleton과 mock mode는 구현되어 있지만, 이 환경에서는 Android build/install과 real-device artifact upload가 검증되지 않았다.

### 관련 요구사항

- FR-002 Capability discovery
- FR-005 Encoding trial 실행
- NFR-004 확장성

### 영향

프로젝트 목표인 Android hardware encoder 포함 closed-loop 증명에는 real-device upload가 필요하다.

### 권장 조치

Android toolchain이 있는 환경에서 다음을 수행한다.

- Android app compile
- mock mode UI smoke test
- backend device-access server 실행
- mock mode disabled 상태에서 one-trial artifact upload

### 완료 기준

- 실제 Android device가 capability를 등록한다.
- trial assignment를 수신한다.
- `MediaCodec` encoding artifact를 backend에 업로드한다.
- backend artifact directory에 `output.h264`, `requested_params.json`, `applied_params.json`, `encoder_log.json`이 생성된다.

## 권장 작업 순서

1. Step 12 backend-only mock closed-loop를 구현한다.
2. Upload 후 evaluation trigger를 결정하고 구현한다.
3. Session completion gate를 강화한다.
4. Report metadata에 현재 구현 가능한 version 정보를 추가한다.
5. Android real-device one-artifact upload를 검증한다.
6. Step 13에서 `RagOutput`, `AiOpsEvent`, guardrail tests를 구현한다.
7. Real evaluator parsing과 input checksum metadata를 구현한다.

## 추적성

| Gap | 관련 문서 |
| --- | --- |
| Upload 후 evaluation 연결 | [06](06_verification_plan.md), [08](08_implementation_plan.md), [13](13_nfr_decision_matrix.md) |
| Completion gate | [01](01_requirements.md), [06](06_verification_plan.md), [12](12_fr_decision_matrix.md) |
| Report trust level/version | [11](11_ai_guardrails_and_aiops.md), [13](13_nfr_decision_matrix.md) |
| `RagOutput`/`AiOpsEvent` | [04](04_data_api_design.md), [11](11_ai_guardrails_and_aiops.md) |
| Input checksum | [01](01_requirements.md), [04](04_data_api_design.md), [13](13_nfr_decision_matrix.md) |
| Real VMAF parsing | [05](05_algorithm_and_rag_design.md), [07](07_risk_and_roadmap.md) |
| Android verification | [03](03_component_design.md), [09](09_implementation_progress.md) |
