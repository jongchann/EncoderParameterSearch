# 14. Implementation Gap Review

## 목적

이 문서는 설계 문서가 강화된 뒤 현재 구현에서 후속 작업으로 남은 gap을 정리한다.

핵심 원칙:

- 문서와 구현의 차이를 숨기지 않는다.
- 현재 Step에서 반드시 맞춰야 하는 항목과 후속 Step의 목표 항목을 분리한다.
- 각 gap은 관련 FR/NFR, 영향, 권장 조치, 완료 기준으로 추적한다.

## 요약

현재 backend는 Step 12 backend-only mock closed-loop까지 구현되었다. Android Step 11은 skeleton과 mock UI가 시작된 상태지만, Android real-device 작업은 후속 작업으로 둔다. 설계 문서가 FR/NFR decision matrix, AI guardrails, AI-Ops까지 확장되면서 일부 항목은 아직 구현과 차이가 있다.

이 차이는 대부분 의도된 단계적 gap이다. Step 12 전에 필요했던 upload-to-evaluation linkage와 session completion gate 강화는 backend mock path 기준으로 처리되었다.

## 우선순위

| 우선순위 | Gap | 판단 |
| --- | --- | --- |
| Done | Trial result upload 후 evaluation 연결 부재 | backend mock path에서 구현됨 |
| Done | Session completion gate가 최소 trial/report 조건을 충분히 확인하지 않음 | backend mock path에서 구현됨 |
| Done | Report metadata와 Markdown에 trust level/version 정보 부족 | RAG placeholder 포함 구현됨 |
| Done | `RagOutput`, `AiOpsEvent` 저장 모델/guardrail foundation | storage/service/guardrail test 구현됨 |
| Done | RAG retrieval corpus version과 mock generator | mock corpus/snapshot/generator 구현됨 |
| P1 | Live/local document retrieval 미구현 | mock RAG 이후 후속 |
| P1 | 입력 영상 checksum/reference metadata 부족 | real evaluator 전 필요 |
| P2 | Real VMAF parsing 미구현 | real evaluation 단계에서 필요 |
| P2 | Android real-device artifact upload 미검증 | Step 11 완료 기준 |

## Gap 1: Upload 후 evaluation 연결

### 현 상태

`POST /sessions/{session_id}/trials/{trial_id}/result`는 artifact와 applied metadata를 저장한 뒤 backend mock path에서 `MockEvaluator`를 즉시 실행한다. HTTP 응답은 evaluation 결과를 포함하고, 성공 시 trial은 `evaluated` 상태가 되며 observation이 생성된다.

서비스 레벨의 `TrialService.upload_result`는 여전히 `uploaded` 중간 상태를 보존한다. 이는 향후 별도 evaluation endpoint나 background worker로 전환할 수 있는 경계로 남긴다.

### 관련 요구사항

- FR-006 평가
- FR-004 Trial parameter 추천
- NFR-005 관측 가능성
- NFR-006 실패 허용성

### 영향

Backend API만으로 `assigned -> uploaded -> evaluated -> next trial` loop가 닫힌다. 단, 현재 결정은 mock evaluator에 한정되며 real evaluator 전환 시 evaluator 선택 방식은 별도로 확정해야 한다.

### 후보

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Upload endpoint에서 mock evaluation 즉시 실행 | Step 12 mock loop가 단순해짐 | real evaluator 전환 시 분기 필요 | 선택 |
| 별도 `POST /evaluate` endpoint 추가 | evaluation trigger가 명확함 | client 또는 orchestrator가 한 단계 더 호출해야 함 | 후보 |
| background worker 도입 | 실제 운영 구조에 가까움 | MVP에 과함 | 후속 |

### 적용된 결정

Step 12에서는 MVP simplicity를 우선해 upload 후 mock evaluation 자동 실행을 선택했다.

### 완료 기준

- HTTP API flow로 trial이 `uploaded`에서 `evaluated`까지 전환된다. 구현됨.
- Observation이 생성된다. 구현됨.
- Evaluation failure는 failed trial과 evaluation log로 남는다. 기존 EvaluationService 경로로 보존됨.
- 다음 trial recommendation이 evaluated/failed parameter를 반복하지 않는다. Step 12 통합 테스트로 확인됨.

## Gap 2: Session completion gate 강화

### 현 상태

`BaselineService.complete_session`은 baseline observation, 최소 evaluated trial 수, final report metadata, `completed_at` 기록을 확인한다.

### 관련 요구사항

- FR-001 Session 관리
- FR-008 결과 리포트
- FR-010 Baseline 실행
- NFR-001 재현성

### 영향

문서상 completed session의 핵심 gate는 backend mock path 기준으로 구현되었다. Pareto Set 계산은 별도 table이 아니라 `ReportService.generate_report`가 final report metadata를 생성하는 방식으로 확인한다.

### 적용된 결정

Completion gate를 다음 조건으로 강화했다.

- evaluated trial count >= 15
- baseline observation exists
- final report metadata exists
- Pareto Set calculation completed through `ReportService.generate_report`
- `completed_at` 저장

### 완료 기준

- baseline만 있는 session은 completed가 되지 않는다. 구현됨.
- report 없이 completed가 되지 않는다. 구현됨.
- completed session은 `completed_at`을 가진다. 구현됨.
- 실패 시 명확한 error message를 반환한다. 구현됨.

## Gap 3: Report trust level과 version metadata

### 현 상태

Report는 raw metric, deterministic derived result, AI-assisted narrative placeholder, optimizer audit trail을 구분한다. Report metadata는 report/search-space/evaluator version 정보와 trust-level count를 저장한다.

`prompt_version`과 `retrieval_snapshot_path`는 recorded `RagOutput`이 있으면 final report metadata에 연결된다. `retrieval_corpus_version`은 corpus snapshot/versioning이 아직 없어 placeholder로 남는다.

### 관련 요구사항

- FR-008 결과 리포트
- NFR-001 재현성
- NFR-005 관측 가능성
- NFR-007 AI guardrails와 AI-Ops

### 영향

Recorded RAG report section이 있으면 final report의 AI-assisted narrative와 metadata에 연결된다. RAG가 없으면 `AI-assisted Narrative: not available`, ignored output만 있으면 guardrail에 의해 ignored 상태로 표시된다.

### 적용된 결정

ReportService를 다음 방향으로 확장했다.

- Report metadata에 `report_template_version`, `evaluator_mode`, `search_space_version` 추가
- Markdown에 `Raw Metrics`, `Deterministic Results`, `AI-assisted Narrative`, `Audit Trail` 구분 유지
- RAG narrative가 없으면 `AI-assisted Narrative: not available`로 명시
- source-less narrative count를 metadata에 기록
- trust-level count를 metadata에 기록

### 완료 기준

- final report에서 metric과 AI narrative를 구분할 수 있다. 구현됨.
- report metadata로 version 정보를 재검토할 수 있다. 구현됨.
- RAG 미사용 상태가 report에 명시된다. 구현됨.

## Gap 4: `RagOutput`와 `AiOpsEvent` 저장 모델

### 현 상태

`rag_outputs`와 `aiops_events` table이 추가되었고, `MetadataStore` JSON round-trip이 구현되었다. `RagOutputService`는 schema/source guardrail을 통과한 output을 `recorded`, 실패한 output을 `ignored`로 저장한다.

Guardrail 결과는 `aiops_events`에 `guardrail_passed` 또는 `guardrail_blocked`로 남는다. Recorded `report_section`은 final report metadata와 AI-assisted narrative section에 연결된다.

### 관련 요구사항

- FR-007 RAG Agent 보조
- NFR-002 안전성
- NFR-007 AI guardrails와 AI-Ops

### 영향

Storage와 guardrail foundation은 구현되었다. 아직 live retrieval, corpus versioning, LLM/mock generator는 없다.

### 적용된 결정

Step 13 foundation으로 다음을 추가했다.

- `rag_outputs` table
- `aiops_events` table
- JSON column round-trip test
- source-less RAG output rejected/ignored test
- schema-invalid RAG output ignored test
- report metadata linkage test

### 완료 기준

- RAG output이 prompt version, retrieval snapshot, sources와 함께 저장된다. 구현됨.
- guardrail pass/block event를 session 단위로 조회할 수 있다. 구현됨.
- source 없는 constraint candidate가 search space에 반영되지 않는다. 구현됨.

## Gap 4-1: RAG retrieval corpus version과 mock generator

### 현 상태

`MockRagAgentService`가 allowlisted mock corpus를 사용해 retrieval snapshot artifact를 저장하고, `mock_rag_corpus_v1`을 snapshot과 AI-Ops event에 기록한다. Mock generator는 `constraint_candidate`, `failure_analysis`, `report_section` payload를 생성하고 `RagOutputService` guardrail을 통과한다.

ReportService는 recorded `report_section`의 snapshot을 읽어 `retrieval_corpus_version`, `prompt_version`, `retrieval_snapshot_path`를 final report metadata에 연결한다.

### 관련 요구사항

- FR-007 RAG Agent 보조
- NFR-001 재현성
- NFR-007 AI guardrails와 AI-Ops

### 영향

Backend는 live LLM 없이도 재현 가능한 mock RAG flow를 시연할 수 있다. 실제 외부/로컬 문서 index 연결은 아직 없다.

### 적용된 결정

- allowlisted mock corpus fixture를 정의했다.
- retrieval snapshot artifact를 저장한다.
- mock RAG generator가 `constraint_candidate`, `failure_analysis`, `report_section` payload를 생성한다.
- `retrieval_corpus_version`을 retrieval snapshot과 report metadata에 연결한다.

### 완료 기준

- 같은 mock query에서 prompt version, corpus version, retrieval snapshot path가 재현 가능하게 남는다. 구현됨.
- mock generator 출력이 `RagOutputService` guardrail을 통과하거나 block된다. 구현됨.
- final report metadata에서 prompt/source/corpus version을 함께 확인할 수 있다. 구현됨.

## Gap 4-2: Live/local document retrieval

### 현 상태

RAG generator는 mock corpus를 사용한다. Android/MediaCodec 문서나 session artifact를 실제 retrieval corpus로 indexing하는 기능은 없다.

### 관련 요구사항

- FR-007 RAG Agent 보조
- NFR-001 재현성
- NFR-007 AI guardrails와 AI-Ops

### 영향

설계 시연에서는 guardrail, versioning, report trust-level을 보여줄 수 있지만, 실제 문서 근거 기반 설명 품질은 아직 mock 수준이다.

### 권장 조치

- local corpus directory contract를 정의한다.
- source allowlist와 corpus version 계산 방식을 정한다.
- session trial/evaluation logs를 retrievable source로 snapshot한다.
- mock generator boundary 뒤에 local retrieval adapter를 연결한다.

### 완료 기준

- corpus file 변경 시 `retrieval_corpus_version`이 바뀐다.
- retrieval snapshot에 source id, title, section, uri, score가 남는다.
- RAG output guardrail은 live/local retrieval 결과에도 동일하게 적용된다.

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

1. Live/local document retrieval adapter를 구현한다.
2. Android mock UI를 Android Studio/device에서 확인한다.
3. Android real-device one-artifact upload를 검증한다.
4. Real evaluator parsing과 input checksum metadata를 구현한다.

## 추적성

| Gap | 관련 문서 |
| --- | --- |
| Upload 후 evaluation 연결 | [06](06_verification_plan.md), [08](08_implementation_plan.md), [13](13_nfr_decision_matrix.md) |
| Completion gate | [01](01_requirements.md), [06](06_verification_plan.md), [12](12_fr_decision_matrix.md) |
| Report trust level/version | [11](11_ai_guardrails_and_aiops.md), [13](13_nfr_decision_matrix.md) |
| `RagOutput`/`AiOpsEvent` | [04](04_data_api_design.md), [11](11_ai_guardrails_and_aiops.md) |
| RAG retrieval/generator | [05](05_algorithm_and_rag_design.md), [11](11_ai_guardrails_and_aiops.md) |
| Live/local document retrieval | [05](05_algorithm_and_rag_design.md), [11](11_ai_guardrails_and_aiops.md) |
| Input checksum | [01](01_requirements.md), [04](04_data_api_design.md), [13](13_nfr_decision_matrix.md) |
| Real VMAF parsing | [05](05_algorithm_and_rag_design.md), [07](07_risk_and_roadmap.md) |
| Android verification | [03](03_component_design.md), [09](09_implementation_progress.md) |
