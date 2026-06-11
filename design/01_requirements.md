# 01. Requirements

## 목표

동일 입력 영상과 동일 Android 기기 조건에서 encoder parameter search를 수행하고, 제한된 search space 안에서 bitrate와 VMAF의 trade-off가 개선되는 Pareto-optimal parameter 후보를 찾는다.

MVP는 전역 최적해를 보장하지 않는다. 대신 baseline 대비 개선된 후보, Pareto Set, Pareto Front, 그리고 그 후보가 선택된 탐색 과정을 재현 가능한 형태로 제시한다.

## 사용자 시나리오

1. 사용자는 backend에 실험 session을 생성한다.
2. Android client는 codec capability를 backend에 등록한다.
3. Backend는 capability와 constraint를 바탕으로 첫 trial parameter를 생성한다.
4. Android client는 parameter를 받아 encoding을 수행한다.
5. Android client는 encoded artifact와 applied metadata를 backend에 업로드한다.
6. Backend는 bitrate와 VMAF를 측정하고 observation을 저장한다.
7. Optimizer는 다음 trial parameter를 추천한다.
8. 최소 15회 trial 후 backend는 개선 parameter 후보, Pareto Set, Pareto Front, baseline 비교, RAG 기반 설명 리포트를 생성한다.

## 기능 요구사항

### FR-001 Session 관리

Backend는 encoder parameter search를 session 단위로 생성, 조회, 진행, 종료할 수 있어야 한다.

- 입력: `input_video_id`, `target_mime`, `target_codec`
- 처리: session 상태를 `created`, `ready`, `running`, `completed`, `failed` 중 하나로 관리한다.
- 저장: session id, 입력 영상 id, 대상 codec, 대상 MIME, 현재 search space version, baseline trial id, 생성/종료 시각
- 수용 기준: capability 등록 전 session은 `created`이고, capability와 search space가 준비되면 `ready`가 된다.
- 수용 기준: 최소 trial 수와 report 생성 조건을 만족하면 `completed`가 된다.
- 수용 기준: 입력 영상, codec capability, artifact 저장소처럼 session 필수 전제가 깨지면 `failed`가 된다.

### FR-002 Capability discovery

Android client는 대상 Android device와 codec의 capability를 수집해 backend에 등록해야 한다.

- 입력: Android device, target MIME, codec selection 결과
- 처리: `MediaCodecList`, `CodecCapabilities`, `EncoderCapabilities` 등으로 수집 가능한 capability를 조사한다.
- 저장: device model, Android version, SoC vendor, codec name, MIME type, supported profiles, bitrate modes, resolution/framerate constraint, B-frame 지원 후보, vendor key 후보, raw payload
- 수용 기준: backend는 capability payload를 session에 연결해 저장한다.
- 수용 기준: capability가 등록되지 않은 session은 trial assignment를 생성하지 않는다.
- 수용 기준: 지원 여부가 불확실한 항목은 지원으로 간주하지 않고 후보 또는 unknown으로 기록한다.

### FR-003 Search space 구성

Backend는 ADR 002의 1차 탐색 변수를 기본으로 optimizer search space를 구성해야 한다.

- `bitrate`
- `i_frame_interval`
- `profile`, 단 capability discovery 결과에서 지원되는 경우

- 입력: ADR rule, capability payload, RAG constraint candidate, trial failure observation
- 처리: ConstraintFilter와 SearchSpaceBuilder가 허용 parameter domain을 생성한다.
- 저장: search space version, parameter domain, accepted/rejected constraint decision, decision source
- 수용 기준: unsupported parameter는 optimizer search space에서 제외된다.
- 수용 기준: `profile`은 capability에 포함된 값만 후보가 된다.
- 수용 기준: vendor extension key는 allowlist와 capability 검증을 통과하지 않으면 제외된다.
- 수용 기준: search space가 변경되면 기존 version을 수정하지 않고 새 version을 생성한다.

### FR-004 Trial parameter 추천

Backend optimizer는 search space와 이전 observation을 바탕으로 다음 trial parameter를 추천해야 한다.

- 입력: search space version, evaluated observation, failed trial parameter, baseline observation
- 처리: 초기 5회는 random, Sobol, Latin Hypercube 또는 동등한 cold start 방식을 사용한다.
- 처리: 이후 trial은 VMAF maximize, bitrate minimize를 objective로 하는 multi-objective optimizer를 사용한다.
- 출력: optimizer trial id, recommended parameter, recommendation metadata
- 수용 기준: 이미 evaluated 된 parameter 조합을 반복 추천하지 않는다.
- 수용 기준: failed trial parameter를 그대로 반복 추천하지 않는다.
- 수용 기준: 추천 결과는 Android client로 전달되기 전에 ConstraintFilter를 다시 통과한다.
- 수용 기준: recommendation metadata에는 search space version과 optimizer phase가 포함된다.

### FR-005 Encoding trial 실행

Android client는 backend가 제공한 requested parameter로 `MediaCodec` encoding trial을 수행해야 한다.

- 입력: trial id, requested parameter, input video reference
- 처리: EncoderParameterProxy가 requested parameter를 `MediaFormat` 설정으로 변환한다.
- 처리: `MediaCodec.configure()`와 encoding을 수행한다.
- 출력: encoded artifact, applied parameter, applied 여부가 불확실한 parameter, encoder log, failure 정보
- 수용 기준: requested parameter와 applied parameter는 분리 기록된다.
- 수용 기준: 적용 여부를 확인할 수 없는 parameter는 `applied_params_unknown`에 기록된다.
- 수용 기준: `configure()` 또는 encoding 실패는 failed trial로 backend에 보고된다.
- 수용 기준: Android client는 VMAF 측정을 수행하지 않는다.

### FR-006 평가

Backend는 encoded artifact를 수신한 뒤 bitrate와 VMAF를 측정하고 observation을 생성해야 한다.

- 입력: encoded artifact, input video reference, trial metadata
- 처리: artifact 존재 여부를 확인하고 bitrate를 계산한다.
- 처리: `ffmpeg`와 `libvmaf`를 사용해 VMAF를 측정한다.
- 저장: bitrate, VMAF, evaluation log path, observation 생성 시각
- 수용 기준: 평가가 성공하면 trial 상태는 `evaluated`가 된다.
- 수용 기준: VMAF 측정 실패 시 artifact와 ffmpeg log를 보존하고 failed evaluation으로 기록한다.
- 수용 기준: observation은 optimizer update에 사용할 수 있는 정량 objective를 포함한다.

### FR-007 RAG Agent 보조

RAG Agent는 다음 작업을 보조해야 한다.

- 문서 기반 constraint 후보 생성
- unsupported parameter 제외 사유 생성
- trial 실패 원인 후보 생성
- 최종 Pareto 결과 리포트 생성

- 입력: 제한된 문서 corpus, capability, constraint decision, trial log, observation
- 출력: constraint candidate, unsupported parameter 제외 사유, failure analysis, report section draft
- 수용 기준: 모든 RAG 출력은 source reference를 포함한다.
- 수용 기준: source reference가 없는 constraint candidate는 search space에 반영되지 않는다.
- 수용 기준: RAG Agent는 최종 parameter를 직접 결정하지 않는다.
- 수용 기준: RAG Agent 실패는 optimizer loop를 중단시키지 않는다.
- 수용 기준: RAG output은 output type, prompt version, source reference, retrieval snapshot metadata와 함께 저장된다.
- 수용 기준: RAG narrative는 raw metric 또는 Pareto result와 구분되어 report에 표시된다.

### FR-008 결과 리포트

Backend는 session 종료 시 다음 결과를 생성해야 한다.

- trial 목록
- requested/applied parameter 비교
- bitrate/VMAF observation
- 개선 parameter 후보
- Pareto Set
- Pareto Front
- baseline 대비 BD-Rate 또는 VMAF-bitrate 비교
- 제외된 parameter와 제외 사유
- 실패 trial 해석

- 입력: session metadata, capability, trial list, observation, constraint decision, optimizer recommendation history, RAG output
- 출력: final report artifact와 report metadata
- 수용 기준: report는 개선 parameter 후보가 어떤 trial과 observation에서 선택됐는지 표시한다.
- 수용 기준: BD-Rate 계산이 불충분하면 VMAF-bitrate table/plot 비교를 대체 지표로 명시한다.
- 수용 기준: failed trial이 있으면 실패 유형과 원인 후보를 포함한다.
- 수용 기준: 최종 후보가 LLM 단독 출력이 아니라 optimizer와 ConstraintFilter를 거쳤다는 audit trail을 포함한다.
- 수용 기준: report는 raw metric, deterministic derived result, AI-assisted narrative를 구분한다.
- 수용 기준: source reference가 없는 RAG 문장은 최종 결론의 근거로 표시하지 않는다.

### FR-009 Audit trail

Backend는 각 trial decision에 대해 다음 정보를 추적해야 한다.

- Search space version
- Constraint decision
- Optimizer recommendation reason 또는 optimizer trial id
- RAG Agent 출력이 사용된 경우 source reference
- 최종 requested parameter 생성 시각

- 입력: search space decision, optimizer recommendation, constraint validation, trial assignment, evaluation result
- 저장: search space version, optimizer trial id, constraint decision id, source reference, requested parameter 생성 시각
- 수용 기준: 임의의 trial id로 requested parameter가 생성된 경로를 역추적할 수 있다.
- 수용 기준: search space 변경 전후 trial을 version으로 구분할 수 있다.
- 수용 기준: RAG output이 search space에 영향을 준 경우 source reference와 filter decision이 함께 남는다.

### FR-010 Baseline 실행

Backend와 Android client는 baseline 비교를 위해 최소 1개의 기준 trial을 실행하거나 선택해야 한다.

Baseline은 Android 기본 encoder 설정, 사전 preset, cold start trial 중 대표값 순서로 선택한다.

- 입력: Android 기본 encoder 설정, 사전 preset, cold start observation
- 처리: baseline 우선순위에 따라 baseline trial을 실행하거나 기존 trial 중 하나를 선택한다.
- 저장: `baseline_trial_id`, baseline observation, baseline selection reason
- 수용 기준: completed session은 baseline observation을 가진다.
- 수용 기준: baseline 없이 final report를 생성할 수는 있지만 session을 `completed`로 전환하지 않는다.
- 수용 기준: baseline 선택 근거는 report에 포함된다.

## 비기능 요구사항

### NFR-001 재현성

동일 session 결과를 나중에 재검토할 수 있도록 trial 결정과 평가 근거를 보존해야 한다.

- 기준: 모든 trial은 requested parameter, applied parameter, artifact path, observation 또는 failure reason을 가진다.
- 기준: 모든 optimizer recommendation은 search space version과 optimizer trial id를 가진다.
- 기준: 입력 영상은 path와 checksum 또는 동등한 식별자를 가진다.
- 기준: report 생성 후에도 raw metric과 constraint decision을 조회할 수 있다.

### NFR-002 안전성

LLM/RAG 출력과 unsupported parameter가 직접 encoder 설정으로 이어지지 않도록 방어해야 한다.

- 기준: RAG constraint candidate는 source reference가 없으면 rejected 된다.
- 기준: optimizer recommendation은 trial assignment 전에 ConstraintFilter를 통과한다.
- 기준: allowlist에 없는 vendor extension key는 Android client로 전달되지 않는다.
- 기준: LLM 출력만으로 search space를 확장하지 않는다.
- 기준: RAG prompt version과 retrieval snapshot을 남겨 AI 설명을 재검토할 수 있어야 한다.

### NFR-003 구현 가능성

1인 3개월 MVP 안에서 구현 가능한 기술과 범위를 우선해야 한다.

- 기준: backend는 Python 기반 구현을 우선한다.
- 기준: metadata store는 SQLite 또는 동등한 경량 로컬 저장소를 우선한다.
- 기준: artifact store는 초기에는 로컬 파일 시스템을 우선한다.
- 기준: 첫 codec은 H.264/AVC, 첫 device는 1대로 제한한다.
- 기준: fine-tuning과 다중 기기 병렬 실험은 MVP 범위에서 제외한다.

### NFR-004 확장성

Android encoder 제어는 Proxy Pattern으로 backend parameter 주입과 `MediaCodec` 설정을 분리한다.

Vendor별 extension key 처리는 Strategy Pattern으로 분리한다.

- 기준: backend parameter schema 변경이 `MediaCodec` 호출부 전체 수정으로 이어지지 않아야 한다.
- 기준: vendor extension key 처리는 기본 `NoOpExtensionStrategy`로 시작할 수 있어야 한다.
- 기준: H.265/HEVC나 추가 parameter는 기존 session/trial 데이터 모델을 유지한 채 확장 가능해야 한다.

### NFR-005 관측 가능성

실험 진행 중 상태와 실패 원인을 session 단위로 확인할 수 있어야 한다.

- 기준: session status는 trial 수, evaluated trial 수, failed trial 수, current search space version을 제공한다.
- 기준: trial status는 `pending`, `assigned`, `uploaded`, `evaluated`, `failed` 중 하나로 조회된다.
- 기준: constraint decision과 optimizer recommendation history는 session 단위로 조회된다.
- 기준: evaluation 실패 시 ffmpeg log path 또는 error message가 남는다.

### NFR-006 실패 허용성

일부 trial 실패가 전체 search session 실패로 즉시 이어지지 않아야 한다.

- 기준: `configure()` 실패, encoding 실패, evaluation 실패는 failed trial로 기록하고 다음 trial을 진행할 수 있다.
- 기준: artifact upload 실패는 retry 가능한 상태로 처리한다.
- 기준: RAG Agent 실패는 optimizer loop를 중단하지 않는다.
- 기준: search space가 비거나 objective 계산이 반복 실패하는 경우에만 session 조기 종료를 허용한다.
- 기준: 조기 종료 시에도 실패 report를 생성한다.

### NFR-007 AI guardrails와 AI-Ops

RAG Agent와 optimizer 변경이 실제 encoder action과 report 신뢰도에 미치는 영향을 통제하고 추적할 수 있어야 한다.

- 기준: RAG output은 schema validation, source validation, action validation, report trust-level validation을 거친다.
- 기준: guardrail을 통과하지 못한 output은 Android client로 전달되지 않는다.
- 기준: prompt version, retrieval snapshot, search space version, optimizer phase, evaluator mode, report template version을 session 단위로 추적한다.
- 기준: RAG 또는 optimizer 변경 후 release gate를 통과하지 못하면 이전 version으로 rollback할 수 있어야 한다.
- 기준: AI-assisted narrative는 raw metric 또는 deterministic derived result와 구분되어 표시된다.

## MVP 성공 기준

- 하나의 Android 기기에서 하나의 H.264/AVC codec 대상으로 실험한다.
- 동일 입력 영상 기준 최소 15회 trial을 완료한다.
- 모든 trial에 requested parameter, applied parameter, bitrate, VMAF, artifact path, metadata가 기록된다.
- Unsupported parameter가 optimizer search space에서 제외된다.
- Optimizer가 동일 parameter 조합을 반복 추천하지 않는다.
- Baseline 대비 개선된 parameter 후보를 산출한다.
- Pareto Set과 Pareto Front가 산출된다.
- Baseline 대비 bitrate 감소 또는 VMAF 개선 사례를 제시한다.
- RAG Agent가 constraint 후보, 제외 사유, trial 요약, 최종 결과 설명을 생성한다.
- 최종 parameter가 LLM 단독 출력이 아니라 constraint filter와 optimizer를 거쳐 선택되었음이 로그로 확인된다.
- AI guardrail 위반이 search space 변경이나 Android trial assignment로 이어지지 않는다.
- Prompt/source/optimizer/evaluator version이 final report 또는 metadata에서 확인된다.

## 요구사항 추적성

| 요구사항 | 설계 문서 | 검증 방법 |
| --- | --- | --- |
| FR-001 Session 관리 | [02](02_system_architecture.md), [03](03_component_design.md), [04](04_data_api_design.md) | Trial lifecycle 통합 테스트 |
| FR-002 Capability discovery | [03](03_component_design.md), [04](04_data_api_design.md) | Capability 등록 API 테스트 |
| FR-003 Search space 구성 | [05](05_algorithm_and_rag_design.md) | ConstraintFilter 단위 테스트 |
| FR-004 Trial parameter 추천 | [05](05_algorithm_and_rag_design.md) | OptimizerService 단위 테스트 |
| FR-005 Encoding trial 실행 | [02](02_system_architecture.md), [03](03_component_design.md) | Android 수동/E2E 테스트 |
| FR-006 평가 | [03](03_component_design.md), [04](04_data_api_design.md) | EvaluationService 단위 테스트 |
| FR-007 RAG Agent 보조 | [04](04_data_api_design.md), [05](05_algorithm_and_rag_design.md), [10](10_design_review_and_evolution.md) | RAG output schema 테스트 |
| FR-008 결과 리포트 | [06](06_verification_plan.md), [10](10_design_review_and_evolution.md) | Report checklist |
| FR-009 Audit trail | [04](04_data_api_design.md), [06](06_verification_plan.md) | Audit log 조회 테스트 |
| FR-010 Baseline 실행 | [05](05_algorithm_and_rag_design.md), [06](06_verification_plan.md) | Baseline 비교 검증 |
| NFR-007 AI guardrails와 AI-Ops | [06](06_verification_plan.md), [11](11_ai_guardrails_and_aiops.md) | Guardrail/release gate 테스트 |
