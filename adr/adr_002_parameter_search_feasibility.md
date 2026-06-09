# ADR 002: Encoder Parameter Search Feasibility and MVP Scope

## Status
Accepted

## Context
Encoder Parameter Search MVP는 Android `MediaCodec` encoder parameter를 자동 탐색해 bitrate 대비 VMAF를 개선하는 closed-loop system을 목표로 한다.

Parameter search 자체는 구현 가능하지만, Android hardware encoder는 기기와 vendor마다 지원 범위와 실제 동작이 다르다. 일부 parameter는 `MediaFormat` 또는 vendor extension key로 설정할 수 있어도 encoder가 무시할 수 있으며, B-frame, QP, vendor-specific key는 단말별 편차가 크다.

따라서 MVP에서 모든 encoder parameter를 자동 탐색 대상으로 삼으면 구현 리스크가 커진다. 3개월 과제에서는 안정적으로 동작하는 핵심 parameter를 먼저 탐색하고, 기기 capability에 따라 탐색 공간을 축소하거나 확장하는 구조를 보여주는 것이 더 현실적이다.

RAG는 이 탐색 과정에서 직접 parameter 값을 고르는 역할보다, Android 문서, vendor codec 문서, 과거 benchmark 기록, trial 실패 로그를 검색해 탐색 공간을 안전하게 구성하는 역할에 적합하다.

## Decision
Parameter search는 MVP에 포함한다. 다만 초기 탐색 공간은 안정적으로 검증 가능한 parameter로 제한한다.

1차 MVP 탐색 변수는 다음으로 제한한다.

- `bitrate`
- `i_frame_interval` 또는 GOP
- `profile`, 단 기기와 codec이 지원하는 값만 사용

2차 확장 변수는 다음으로 둔다.

- `b_frame_count`, 단 기기 지원 시에만 사용
- `bitrate_mode`, 예: CBR, VBR, CQ
- QP 관련 parameter, 단 public API 또는 vendor key 지원이 확인된 경우에만 사용
- vendor extension key, 단 allowlist에 포함되고 실제 적용 여부를 검증할 수 있는 경우에만 사용

Backend optimizer가 다음 parameter set을 추천하고, Android client가 해당 parameter로 encoding trial을 수행한다. Backend는 encoded output을 받아 bitrate와 VMAF를 측정하고, observation을 optimizer에 다시 제공한다.

RAG Agent는 parameter를 직접 추천하지 않고, 탐색 공간 구성을 위한 문서 기반 constraint 후보를 생성한다. Backend는 RAG Agent의 constraint 후보를 structured constraint filter로 검증한 뒤 optimizer search space에 반영한다.

MVP에서 RAG Agent가 다루는 정보와 출력은 다음으로 제한한다.

- Android CDD, `MediaCodec`, `MediaFormat`, vendor codec 문서 검색
- 과거 benchmark 또는 trial observation 검색
- 지원되지 않거나 위험한 parameter 후보의 제외 사유 생성
- `configure()` 실패, requested/applied parameter 불일치, VMAF 측정 실패에 대한 원인 후보 생성
- 최종 Pareto 결과에 대한 문서 근거 포함 리포트 생성

MVP의 기본 optimizer는 구현 안정성을 위해 Optuna NSGA-II 또는 동등한 multi-objective optimizer를 사용할 수 있다. 고급 구현 또는 비교 실험에서는 BoTorch qNEHVI를 사용할 수 있다. 비교 기준으로 random search를 함께 실행해 optimizer 사용의 효과를 보여준다.

## Consequences
이 결정은 MVP 구현 가능성을 높인다. `bitrate`, `i_frame_interval`, `profile` 중심의 제한된 탐색만으로도 VMAF-bitrate trade-off와 Pareto Front를 만들 수 있다.

기기별 codec capability를 탐색 공간에 반영해야 하므로, Android client 또는 backend에 capability discovery 결과를 전달하는 흐름이 필요하다. Unsupported parameter는 optimizer 후보에서 제외해야 하며, 설정했지만 실제 적용 여부가 불확실한 parameter는 observation metadata에 기록해야 한다.

RAG Agent를 통해 문서 기반 제약과 실험 로그 기반 제약을 함께 설명할 수 있으므로, 단순한 black-box optimization보다 과제의 AI 설계 의도가 잘 드러난다. 단, RAG 출력은 hallucination 가능성이 있으므로 사람이 읽는 설명과 constraint 후보로만 사용하고, 최종 search space 변경은 structured rule과 capability data로 검증해야 한다.

초기에는 QP, B-frame, vendor extension key처럼 매력적인 parameter를 제한적으로만 다루기 때문에 최적화 폭이 작아질 수 있다. 대신 closed-loop search의 안정성과 재현성을 먼저 확보할 수 있다.

## Alternatives Considered
### 모든 parameter를 처음부터 탐색
QP, B-frame, bitrate mode, vendor extension key까지 한 번에 탐색하는 방식이다. 탐색 공간이 넓어 더 좋아 보이지만, 단말별 지원 편차와 encoder 무시 가능성 때문에 3개월 MVP에서는 실패 위험이 높다.

### Bitrate만 탐색
가장 구현하기 쉽지만, AI 기반 parameter search 과제로 보이기에는 탐색 공간이 지나치게 단순하다. 최소한 GOP 또는 profile을 함께 다뤄야 multi-parameter optimization의 의미가 있다.

### LLM이 parameter를 직접 추천
LLM이 다음 parameter를 직접 고르는 방식이다. 설명력은 높지만 수치 최적화의 재현성과 성능 검증이 어렵다. 따라서 LLM은 제약 설명과 리포트 생성에 사용하고, 실제 parameter recommendation은 optimizer가 담당한다.

### RAG를 최종 리포트에만 사용
RAG를 실험이 끝난 뒤 리포트 생성에만 사용하는 방식이다. 구현은 단순하지만 탐색 과정 자체에 AI가 기여하는 부분이 약해진다. 따라서 MVP에서는 리포트뿐 아니라 search space constraint 후보 생성과 실패 원인 후보 생성에도 RAG를 사용한다.

## Success Criteria
MVP parameter search는 다음 조건을 만족해야 한다.

- 동일 입력 영상 기준 최소 15회 encoding trial을 완료한다.
- 각 trial의 requested parameter와 applied parameter를 구분해 기록한다.
- Unsupported parameter는 optimizer search space에서 제외된다.
- RAG Agent가 문서 또는 과거 observation에 근거해 constraint 후보와 제외 사유를 생성한다.
- RAG Agent 출력이 structured constraint filter를 거쳐 search space에 반영되었는지 로그로 확인할 수 있다.
- Optimizer가 이미 평가한 parameter 조합을 반복 추천하지 않는다.
- Random search 대비 optimizer 기반 탐색의 Pareto Front 또는 VMAF-bitrate trade-off 개선을 보고할 수 있다.
- 1차 탐색 변수만으로도 baseline 대비 bitrate 감소 또는 VMAF 개선 사례를 제시할 수 있다.
- 최종 리포트는 Pareto 결과, 제외된 parameter 사유, 실패 trial 해석을 함께 포함한다.

## Assumptions
- 첫 codec은 H.264/AVC를 우선 지원한다.
- 첫 Android device는 1개로 제한한다.
- 1차 MVP에서 가장 신뢰할 수 있는 변수는 `bitrate`와 `i_frame_interval`이다.
- `profile`은 capability discovery 결과에 따라 탐색 대상에서 제외될 수 있다.
- QP와 vendor extension key는 후속 확장 대상이며, 지원 여부가 확인되지 않으면 MVP 핵심 경로에 넣지 않는다.
- RAG Agent는 vector DB 또는 경량 문서 검색 계층을 사용할 수 있으나, MVP에서는 검색 대상 문서를 제한된 corpus로 시작한다.
- RAG Agent가 생성한 constraint 후보는 최종 권한을 갖지 않으며, backend의 structured constraint filter가 최종 search space를 결정한다.
