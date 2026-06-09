# 06. Verification Plan

## 검증 목표

MVP 검증의 목표는 제한된 parameter space에서도 closed-loop search가 재현 가능하게 동작하고, 결과 리포트가 실험 근거를 보존하는지 확인하는 것이다.

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

## 수동 점검 체크리스트

- Android client가 VMAF 측정을 수행하지 않는다.
- Backend가 trial 상태와 observation을 저장한다.
- RAG Agent가 final decision 권한을 갖지 않는다.
- Requested/applied parameter가 분리되어 있다.
- Unsupported parameter가 optimizer search space에서 제외된다.
- Final report가 raw metric과 설명을 함께 제공한다.

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
