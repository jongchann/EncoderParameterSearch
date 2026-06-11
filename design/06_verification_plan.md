# 06. Verification Plan

## 검증 목표

MVP 검증의 목표는 제한된 parameter space에서도 closed-loop search가 재현 가능하게 동작하고, 결과 리포트가 실험 근거를 보존하는지 확인하는 것이다.

검증은 다음 관점으로 나눈다.

| 층 | 검증 질문 |
| --- | --- |
| Closed-loop correctness | session, trial, upload, evaluation, optimizer update가 끝까지 이어지는가 |
| AI safety | RAG output이 source와 ConstraintFilter 없이 search space를 바꾸지 않는가 |
| AI guardrails | schema, source, action, report guardrail이 기대대로 block/pass 되는가 |
| AI-Ops readiness | prompt/source/search space/evaluator/report version과 품질 metric이 남는가 |
| Report credibility | raw metric, derived result, AI-assisted narrative가 분리되어 표시되는가 |

## 설계-구현 추적성 gate

주요 설계 주장은 구현 또는 명시적 gap으로 연결되어야 한다.

| 설계 주장 | 검증 방식 |
| --- | --- |
| Android client는 VMAF를 측정하지 않는다 | Android code review와 manual E2E checklist |
| Requested/applied parameter를 분리한다 | Trial upload API 테스트와 report table 확인 |
| Optimizer 추천은 ConstraintFilter를 다시 통과한다 | Trial assignment integration test |
| RAG는 최종 parameter를 결정하지 않는다 | RAG schema test와 ConstraintDecision audit 확인 |
| Baseline 없이 completed가 될 수 없다 | BaselineService completion test |
| Report는 metric과 설명을 함께 보존한다 | ReportService golden output 또는 checklist |
| AI guardrail 위반은 action으로 이어지지 않는다 | guardrail blocked scenario test |
| AI-Ops telemetry는 session 단위로 남는다 | metadata 또는 artifact 존재 확인 |

## 단위 테스트

### ConstraintFilter

검증 항목:

- Capability에 없는 `profile`을 제외한다.
- Allowlist에 없는 vendor extension key를 제외한다.
- 출처 없는 RAG constraint 후보를 제외한다.
- ADR rule과 capability가 충돌할 때 더 보수적인 결정을 선택한다.
- Optimizer recommendation을 trial assignment 전에 재검증한다.
- Search space 변경 시 새 version을 생성한다.

### OptimizerService

검증 항목:

- Cold start trial이 중복 parameter를 생성하지 않는다.
- 이미 평가한 parameter 조합을 다시 추천하지 않는다.
- Observation 추가 후 다음 추천을 생성한다.
- Search space 밖 parameter를 생성하지 않는다.
- Search space version을 recommendation metadata에 포함한다.
- Failed trial parameter를 그대로 반복 추천하지 않는다.

### EvaluationService

검증 항목:

- Encoded artifact path가 없으면 실패로 기록한다.
- Bitrate 측정 결과를 observation에 저장한다.
- VMAF 측정 실패 시 평가 로그를 보존한다.

### ReportService

검증 항목:

- Pareto Set을 report에 포함한다.
- Baseline comparison을 report에 포함한다.
- Constraint decision log를 report에 포함한다.
- RAG output에 source reference가 없으면 report에 신뢰 근거로 표시하지 않는다.

### RagAgentService

Step 13 구현 시 검증 항목:

- Constraint candidate JSON schema를 검증한다.
- Source reference가 없는 constraint candidate를 search space에 반영하지 않는다.
- Retrieval snapshot path를 `RagOutput` metadata에 남긴다.
- Prompt version을 `RagOutput` metadata에 남긴다.
- LLM/RAG 실패가 trial assignment와 optimizer loop를 중단시키지 않는다.
- RAG report section이 raw metric 값을 새로 계산하거나 덮어쓰지 않는다.

### AI guardrails

Step 13 이후 검증 항목:

- Schema가 깨진 RAG output은 `ignored` 또는 rejected 상태로만 저장된다.
- Source reference 없는 constraint candidate는 `ConstraintFilter`에서 block 된다.
- RAG output이 Android trial assignment로 직접 전달되는 경로가 없다.
- Report에서 AI-assisted narrative는 raw metric trust level로 표시되지 않는다.
- Guardrail block 사유가 `ConstraintDecision`, `RagOutput`, 또는 AI-Ops event에 남는다.

### AI-Ops telemetry

검증 항목:

- Prompt version과 retrieval snapshot path가 session artifact에 남는다.
- RAG source coverage, schema validation result, constraint accepted/rejected count를 조회할 수 있다.
- Optimizer phase, seed, recommendation status가 metadata에 남는다.
- Evaluator mode와 failure log가 report 또는 artifact로 연결된다.
- RAG/optimizer/evaluator 변경 후 rollback 판단에 필요한 event가 남는다.

## 통합 테스트

### Trial lifecycle

시나리오:

1. Session 생성
2. Capability 등록
3. Next trial 생성
4. Trial result 업로드
5. Evaluation 수행
6. Optimizer observation 업데이트
7. 다음 trial 생성

성공 기준:

- Trial 상태가 `pending -> assigned -> uploaded -> evaluated` 순서로 변경된다.
- Observation이 trial과 연결된다.
- 다음 trial이 이전 parameter와 중복되지 않는다.
- Trial에 `search_space_version`과 `optimizer_trial_id`가 남는다.

### Failure lifecycle

시나리오:

1. Unsupported parameter가 포함된 trial 후보 생성 시도
2. ConstraintFilter가 후보를 거부
3. 거부 사유가 ConstraintDecision에 기록
4. RAG Agent가 제외 사유 설명 생성

성공 기준:

- Unsupported parameter가 Android client로 전달되지 않는다.
- Constraint decision log가 남는다.
- RAG 설명은 source reference를 포함한다.

### RAG safety lifecycle

시나리오:

1. RAG Agent가 source reference 없는 constraint candidate를 생성한다.
2. Backend가 `RagOutput`을 저장하되 신뢰 근거로 표시하지 않는다.
3. ConstraintFilter가 해당 candidate를 search space 변경에서 제외한다.
4. ReportService가 제외 사유와 RAG 미사용 상태를 표시한다.

성공 기준:

- Search space version이 변경되지 않는다.
- `ConstraintDecision` 또는 RAG metadata에 rejection reason이 남는다.
- 다음 trial recommendation은 기존 accepted search space 안에서만 생성된다.

### AI-Ops release gate

시나리오:

1. Prompt version 또는 retrieval corpus version을 변경한다.
2. 동일 fixture session으로 RAG output과 report를 생성한다.
3. Guardrail pass/block event와 report trust level을 확인한다.
4. 기존 raw metric과 Pareto calculation이 변경되지 않았는지 확인한다.

성공 기준:

- Source 없는 constraint candidate가 search space에 반영되지 않는다.
- Raw metric과 deterministic derived result는 RAG 변경으로 바뀌지 않는다.
- AI-Ops event 또는 report metadata에 변경 version이 남는다.
- 실패 시 이전 prompt/corpus version으로 rollback할 수 있다.

### End-to-end MVP lifecycle

시나리오:

1. Session 생성
2. Capability 등록
3. Baseline trial 실행 또는 선택
4. Cold start 5회 수행
5. Optimizer 기반 trial 수행
6. 최소 15회 evaluated trial 확보
7. Pareto Set 계산
8. Final report 생성

성공 기준:

- Session 상태가 `completed`가 된다.
- Report에 baseline, Pareto Set, trial table, constraint decision이 포함된다.
- 최종 parameter decision이 LLM 단독 출력이 아님을 audit trail로 확인한다.

## 실험 검증

### MVP 실험 조건

- Android device: 1대
- Codec: H.264/AVC 우선
- Input video: 동일 기준 영상
- Trial count: 최소 15회
- Search variable: `bitrate`, `i_frame_interval`, `profile`

### 실험 전제 기록

- 입력 영상 path와 checksum
- 해상도, framerate, duration
- Device model과 Android version
- Codec name과 MIME type
- Trial 실행 timestamp
- 가능하면 device temperature 또는 throttling 관련 metadata

### 측정 항목

- Trial별 requested parameter
- Trial별 applied parameter
- Bitrate
- VMAF
- Artifact path
- Encoder log
- Evaluation log
- Constraint decision
- Optimizer recommendation history

### 결과 검증

성공 기준:

- 최소 15회 trial 완료
- Pareto Set 산출
- Pareto Front plot 데이터 산출
- Baseline 대비 개선 사례 1개 이상 제시
- Failed trial이 있는 경우 실패 원인 후보와 로그가 리포트에 포함
- BD-Rate를 계산하지 못하는 경우 대체 비교 지표를 명시

## 리포트 검증

최종 리포트는 다음 항목을 포함해야 한다.

- Session metadata
- Device와 codec capability 요약
- Search space와 제외된 parameter 목록
- Trial result table
- Pareto Set
- Baseline 비교
- RAG Agent가 생성한 constraint 설명
- 최종 parameter가 optimizer와 constraint filter를 거쳐 선택되었다는 audit trail

리포트의 각 문장은 다음 trust level 중 하나로 분류할 수 있어야 한다.

| Trust level | 예시 |
| --- | --- |
| Raw metric | bitrate, VMAF, artifact path, evaluation log |
| Deterministic derived result | Pareto Set, baseline delta, failed trial count |
| AI-assisted narrative | RAG constraint explanation, failure cause candidate |
| Manual note | Android device setup gap, environment limitation |

AI-assisted narrative는 source reference가 없으면 결론 근거로 표시하지 않는다.

## 수동 점검 체크리스트

- Android client가 VMAF 측정을 수행하지 않는다.
- Backend가 trial 상태와 observation을 저장한다.
- RAG Agent가 final decision 권한을 갖지 않는다.
- Requested/applied parameter가 분리되어 있다.
- Unsupported parameter가 optimizer search space에서 제외된다.
- Final report가 raw metric과 설명을 함께 제공한다.
- Report에서 raw metric과 RAG interpretation이 구분되어 있다.

## 산출물 체크리스트

- `sessions` metadata
- `capabilities` metadata
- `trials` metadata
- `observations` metadata
- `constraint_decisions` metadata
- `optimizer_recommendations` metadata
- Encoded artifacts
- Evaluation logs
- RAG source snapshots
- Final report

## 리스크 기반 검증

| 리스크 | 검증 |
| --- | --- |
| Requested parameter가 실제로 적용되지 않음 | requested/applied/unknown parameter 분리 기록 확인 |
| Unsupported parameter가 client로 전달됨 | ConstraintFilter와 trial assignment API 테스트 |
| VMAF 측정 실패 | Evaluation failure log 보존 테스트 |
| RAG hallucination | Source 없는 RAG output 거부 테스트 |
| Trial 수 부족 | Session completed 전 최소 evaluated trial count 확인 |
| Guardrail 우회 | RAG output이 ConstraintFilter 없이 action으로 이어지지 않는지 테스트 |
| 운영 회귀 | prompt/source/optimizer 변경 후 release gate 테스트 |
