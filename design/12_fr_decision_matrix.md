# 12. FR Decision Matrix

## 목적

이 문서는 기능 요구사항(FR)별로 어떤 설계 후보를 비교했고, 왜 현재 설계를 선택했는지 정리한다.

ADR 001과 ADR 002는 시스템 단위의 큰 결정을 설명한다. 이 문서는 그 결정을 FR 단위로 풀어, 요구사항이 단순 선언이 아니라 trade-off 검토를 거쳐 결정됐음을 보여준다.

## 검토 결과 요약

현재 설계 문서에서 architecture decision은 비교적 잘 드러난다.

- Android 단말과 backend를 분리한 closed-loop 구조
- LLM/RAG와 optimizer의 권한 분리
- ConstraintFilter를 통한 안전 경계
- requested/applied parameter 분리
- search space version과 optimizer recommendation audit trail

다만 FR 문서만 읽으면 후보 비교가 충분히 보이지 않는다. 예를 들어 FR-004는 optimizer를 사용한다고 말하지만, random-only, LLM-direct, deterministic cold start 같은 후보와 비교한 이유는 ADR과 알고리즘 문서에 흩어져 있다. 따라서 아래 decision matrix를 FR 추적성의 보조 문서로 둔다.

## 결정 기준

각 FR의 후보는 다음 기준으로 비교한다.

| 기준 | 설명 |
| --- | --- |
| 구현 가능성 | 1인 3개월 MVP에서 구현 가능한가 |
| 재현성 | 나중에 같은 session decision을 재검토할 수 있는가 |
| 안전성 | unsupported parameter나 LLM hallucination이 action으로 이어지지 않는가 |
| 실험 신뢰도 | Android hardware encoder와 backend evaluation을 실제로 검증하는가 |
| 확장성 | H.265, QP, vendor extension, 다중 기기로 확장 가능한가 |
| 검증성 | unit/integration/E2E test로 확인 가능한가 |

## FR별 결정 요약

| FR | 선택한 설계 | 주요 대안 | 선택 이유 |
| --- | --- | --- | --- |
| FR-001 Session 관리 | SQLite metadata 기반 state machine | in-memory state, file-only log | 재현성과 테스트 용이성이 높고 MVP에 충분히 단순하다. |
| FR-002 Capability discovery | Android client가 실제 codec capability를 보고 | 정적 capability 파일, backend 추정 | hardware encoder 차이를 반영하려면 client-side discovery가 필요하다. |
| FR-003 Search space 구성 | ADR rule + capability + ConstraintFilter | 전체 parameter 탐색, RAG-driven search space | 안전성과 구현 가능성을 위해 1차 parameter로 제한한다. |
| FR-004 Trial parameter 추천 | cold start 후 multi-objective optimizer | random-only, LLM-direct | 수치 objective는 optimizer가 맡고, LLM은 설명으로 제한한다. |
| FR-005 Encoding trial 실행 | Android `MediaCodec` + EncoderParameterProxy | backend simulation, Android all-in-one | 실제 hardware behavior를 보면서도 API 결합도를 낮춘다. |
| FR-006 평가 | backend `ffmpeg`/`libvmaf`, mock/real evaluator boundary | Android-side VMAF, mock-only | 단말 부담을 줄이고 lifecycle test와 real evaluation을 분리한다. |
| FR-007 RAG Agent 보조 | source-backed RAG + guardrails | RAG 없음, report-only RAG, LLM-direct | AI 설계 의도를 보이면서도 최종 decision 권한은 제한한다. |
| FR-008 결과 리포트 | metric + derived result + AI narrative 분리 | metric-only, LLM-generated report only | 설명력과 신뢰도를 동시에 확보한다. |
| FR-009 Audit trail | metadata + artifact 기반 audit | log-only, full event sourcing | MVP에는 가볍고 충분하며, 나중에 event table로 확장 가능하다. |
| FR-010 Baseline 실행 | Android default 우선, cold-start fallback | manual baseline only, fixed preset only | baseline 부재로 completion이 흔들리지 않도록 우선순위를 둔다. |

## FR-001 Session 관리

결정: session/trial 상태를 SQLite metadata store와 명시적 state transition으로 관리한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| In-memory state | 구현이 가장 빠름 | 재시작 후 재현 불가, audit trail 약함 | 제외 |
| File-only JSON log | 단순하고 사람이 읽기 쉬움 | 조회와 상태 전이 검증이 불편함 | 보류 |
| SQLite metadata store | 재현성, 조회성, 테스트 용이성 | schema 관리가 필요함 | 선택 |

선택 이유:

- session, trial, observation, constraint decision을 join해 report와 audit trail을 만들 수 있다.
- 1인 MVP에서는 PostgreSQL 같은 외부 DB보다 SQLite가 충분하다.
- 상태 전이 테스트가 쉽다.

## FR-002 Capability discovery

결정: Android client가 `MediaCodecList`, `CodecCapabilities`, `EncoderCapabilities`를 조사해 backend에 등록한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Backend가 static capability를 사용 | backend 구현이 단순함 | 실제 기기/vendor 차이를 놓침 | 제외 |
| 사용자가 capability를 수동 입력 | 빠르게 시작 가능 | 오류 가능성이 높고 재현성 낮음 | 제외 |
| Android client가 capability를 보고 | 실제 encoder와 연결됨 | client 구현 필요 | 선택 |

선택 이유:

- 프로젝트 목표가 Android hardware encoder behavior 검증이므로 실제 단말 capability가 필요하다.
- raw payload를 저장하면 나중에 capability 해석 오류를 재검토할 수 있다.
- 지원 여부가 불확실한 항목은 unknown으로 남겨 search space에서 보수적으로 제외한다.

## FR-003 Search space 구성

결정: ADR rule과 capability를 기본으로 하고, RAG constraint candidate는 ConstraintFilter 검증 후에만 반영한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| 모든 parameter를 처음부터 탐색 | 최적화 폭이 넓음 | 단말별 실패 위험과 search cost가 큼 | 제외 |
| `bitrate`만 탐색 | 구현이 가장 쉬움 | AI parameter search 설계로 보이기 약함 | 제외 |
| 1차 parameter + capability filter | 구현 가능성과 설계 의미의 균형 | 최적화 폭은 제한됨 | 선택 |
| RAG가 search space를 직접 생성 | AI 활용이 눈에 띔 | hallucination과 unsafe parameter 위험 | 제외 |

선택 이유:

- 1차 MVP는 `bitrate_kbps`, `i_frame_interval_sec`, capability-supported `profile`로 제한한다.
- QP, B-frame, vendor extension key는 allowlist와 적용 검증 후 확장한다.
- search space version을 남겨 constraint 변경 전후 trial을 분리한다.

## FR-004 Trial parameter 추천

결정: 초기 cold start로 search space를 관측하고, 이후 multi-objective optimizer로 Pareto 후보를 확장한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Random-only search | 단순하고 baseline으로 유용 | trial 수가 적으면 비효율적 | baseline 후보 |
| LLM-direct recommendation | AI 사용이 분명함 | 수치 최적화 재현성과 안전성이 낮음 | 제외 |
| Deterministic cold start only | lifecycle 검증이 쉬움 | optimizer 효과를 보여주기 약함 | 초기 구현 |
| Cold start + MOBO/NSGA-II | Pareto objective와 잘 맞음 | 구현 복잡도 증가 | 목표 설계 |

선택 이유:

- VMAF maximize와 bitrate minimize는 명확한 multi-objective problem이다.
- LLM은 parameter 선택자가 아니라 constraint 해석과 report 설명자로 제한한다.
- recommendation metadata에 phase, seed, search space version을 남긴다.

## FR-005 Encoding trial 실행

결정: Android client가 `MediaCodec` trial을 실행하고, `EncoderParameterProxy`가 backend parameter schema와 Android API mapping을 분리한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Backend ffmpeg encoder simulation | 개발이 빠름 | Android hardware encoder behavior를 검증하지 못함 | 제외 |
| Android all-in-one 실행 | 네트워크 단순화 | VMAF/AI/optimizer가 단말 부담을 키움 | 제외 |
| Android encode + backend evaluation | 실제 encoder와 backend loop를 함께 검증 | client-server 통신 필요 | 선택 |

선택 이유:

- 실제 `MediaCodec.configure()` 성공/실패와 applied metadata가 핵심 observation이다.
- Proxy Pattern으로 parameter schema 변경이 `MediaCodec` 호출부 전체 변경으로 번지는 것을 막는다.
- requested/applied/unknown parameter를 분리해 hardware encoder의 불확실성을 드러낸다.

## FR-006 평가

결정: backend에서 bitrate와 VMAF를 평가하고, mock evaluator와 real evaluator 경계를 분리한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Android-side VMAF | artifact upload가 줄 수 있음 | 단말 부하, 배터리, 구현 난이도 증가 | 제외 |
| Backend real evaluator only | 실제 metric에 바로 접근 | Android 없이 lifecycle test가 어려움 | 보류 |
| Backend mock + real evaluator boundary | 테스트와 실제 평가를 분리 | mock metric은 실제 품질이 아님 | 선택 |

선택 이유:

- lifecycle test는 mock evaluator로 안정적으로 수행한다.
- real evaluator는 `ffmpeg`/`libvmaf` command, stdout, stderr, return code를 보존한다.
- 실제 VMAF parsing은 별도 completion gate로 둔다.

## FR-007 RAG Agent 보조

결정: RAG Agent는 source-backed constraint candidate, failure analysis, report section draft를 만들되 최종 decision 권한은 갖지 않는다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| RAG 없음 | 구현이 단순함 | AI 포함 설계 의도가 약함 | 제외 |
| Report-only RAG | 안전하고 구현 쉬움 | 탐색 과정에 AI 기여가 약함 | 보류 |
| LLM-direct parameter 추천 | AI 역할이 강하게 보임 | 안전성, 재현성, 검증성 낮음 | 제외 |
| Guarded RAG assistant | AI 설명력과 안전성 균형 | schema/source/telemetry 필요 | 선택 |

선택 이유:

- RAG output은 `RagOutput`으로 저장하고, source reference와 prompt version을 남긴다.
- Constraint candidate는 `ConstraintFilter`가 accepted/rejected로 확정한다.
- RAG failure는 optimizer loop를 중단하지 않는다.

## FR-008 결과 리포트

결정: raw metric, deterministic derived result, AI-assisted narrative를 분리한 final report를 생성한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Metric-only report | 객관적이고 단순함 | 설계 의도와 실패 해석이 부족함 | 제외 |
| LLM-generated report only | 읽기 쉬움 | metric 신뢰도와 audit trail이 약함 | 제외 |
| Hybrid report with trust levels | 설명력과 신뢰도 균형 | report 구조가 더 복잡함 | 선택 |

선택 이유:

- Pareto Set, baseline comparison, trial table은 deterministic service가 만든다.
- RAG narrative는 source-backed interpretation으로만 표시한다.
- source 없는 RAG 문장은 최종 결론 근거로 쓰지 않는다.

## FR-009 Audit trail

결정: metadata store와 artifact store를 결합해 trial decision을 역추적한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Plain log only | 구현이 쉬움 | query와 report 생성이 어려움 | 제외 |
| Full event sourcing | audit이 강력함 | MVP에 과함 | 후속 |
| Metadata + artifact audit | 구현 가능성과 추적성 균형 | event replay는 제한적 | 선택 |

선택 이유:

- trial id로 requested parameter, optimizer trial id, search space version, observation, report path를 추적할 수 있다.
- RAG source snapshot과 evaluation log는 artifact로 보존한다.
- AI-Ops event는 초기에는 artifact JSON 또는 report metadata로 시작하고, 필요하면 table로 승격한다.

## FR-010 Baseline 실행

결정: Android default encoder trial을 우선 baseline으로 사용하고, 없으면 cold-start trial 중 중심 bitrate에 가까운 observation을 선택한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Manual baseline only | 사람이 의도를 명확히 지정 | 자동 lifecycle이 막힐 수 있음 | 제외 |
| Fixed preset only | 비교가 안정적 | device capability와 맞지 않을 수 있음 | 보류 |
| Default trial + cold-start fallback | 자동 completion과 비교 가능성 균형 | baseline 의미를 report에 설명해야 함 | 선택 |

선택 이유:

- completed session은 baseline observation을 가져야 한다.
- baseline 없이 report는 생성할 수 있지만 completed 전환은 막는다.
- baseline selection reason을 report metadata에 남긴다.

## Cross-cutting decision: AI guardrails와 AI-Ops

AI guardrails와 AI-Ops는 단일 FR이 아니라 FR-003, FR-004, FR-007, FR-008, FR-009에 걸친 cross-cutting concern이다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Guardrail 없음 | 구현이 빠름 | AI hallucination이 action/report에 섞일 수 있음 | 제외 |
| Prompt-level guardrail만 적용 | 도입이 쉬움 | action safety를 보장하지 못함 | 제외 |
| Schema/source/action/report guardrail | 실제 action 경로를 통제 | metadata와 test가 필요함 | 선택 |
| Full AI-Ops platform | 운영성이 좋음 | 1인 MVP에 과함 | 후속 |

선택 이유:

- RAG output은 schema/source validation을 거친다.
- ConstraintFilter가 action guardrail 역할을 한다.
- ReportService가 trust-level guardrail 역할을 한다.
- AI-Ops는 prompt/source/search space/evaluator/report versioning과 session-level telemetry에서 경량으로 시작한다.

## 남은 보강 포인트

다음 항목은 아직 ADR로 확정되지 않은 decision point다.

- ADR 003: RAG Agent provider와 storage contract
- ADR 004: Real evaluator contract
- ADR 005: Optimizer upgrade strategy
- ADR 006: AI guardrails and AI-Ops policy

이 문서는 현재 설계 선택의 근거를 설명하지만, 위 항목의 구현 세부사항은 각 ADR에서 별도 확정한다.
