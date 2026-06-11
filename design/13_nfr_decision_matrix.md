# 13. NFR Decision Matrix

## 목적

이 문서는 비기능 요구사항(NFR)별로 어떤 설계 후보를 비교했고, 왜 현재 설계를 선택했는지 정리한다.

이 프로젝트에서 NFR은 부가 조건이 아니라 architecture decision의 핵심 동인이다. Android hardware encoder는 지원 범위와 실제 적용 여부가 불확실하고, RAG/LLM output은 hallucination 가능성이 있으며, VMAF evaluation과 artifact upload는 실패할 수 있다. 따라서 재현성, 안전성, 구현 가능성, 확장성, 관측성, 실패 허용성, AI guardrails는 기능 설계보다 먼저 고려해야 하는 품질 속성이다.

## NFR별 결정 요약

| NFR | 선택한 설계 | 주요 대안 | 선택 이유 |
| --- | --- | --- | --- |
| NFR-001 재현성 | versioned metadata + artifact snapshot | console log only, in-memory state | trial decision과 결과를 나중에 재검토할 수 있어야 한다. |
| NFR-002 안전성 | ConstraintFilter + source validation + allowlist | client-side trust, LLM direct action | unsupported parameter와 RAG hallucination을 action 전에 차단한다. |
| NFR-003 구현 가능성 | 1 device, H.264/AVC, SQLite, local artifacts | multi-device platform, cloud DB | 1인 3개월 MVP에서 closed-loop 증명을 우선한다. |
| NFR-004 확장성 | Proxy/Strategy + versioned schema | direct `MediaFormat` mapping | codec/vendor 차이를 core loop와 분리한다. |
| NFR-005 관측 가능성 | session/trial status + recommendation/evaluation logs | final report only | 실험 중 실패 원인과 진행 상태를 추적해야 한다. |
| NFR-006 실패 허용성 | failed trial로 격리하고 loop 계속 진행 | fail-fast session abort | 일부 trial 실패가 전체 탐색 실패가 되면 MVP 검증이 어렵다. |
| NFR-007 AI guardrails와 AI-Ops | schema/source/action/report guardrails + lightweight telemetry | prompt-only guardrail, full AIOps platform | 안전성과 운영성을 확보하되 MVP 구현 범위를 넘지 않는다. |

## NFR-001 재현성

결정: session, search space, trial, observation, optimizer recommendation, report metadata를 저장하고 artifact snapshot을 보존한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Console log only | 구현이 가장 빠름 | query와 report 재생성이 어렵고 누락 위험이 큼 | 제외 |
| In-memory state | 테스트 초기 구현이 쉬움 | process 종료 후 재현 불가 | 제외 |
| Metadata DB + artifact snapshot | decision과 output을 함께 추적 가능 | schema와 artifact layout 관리 필요 | 선택 |
| Full event sourcing | replay와 audit이 강력함 | MVP에 과한 복잡도 | 후속 |

선택 이유:

- trial id로 requested/applied parameter, search space version, optimizer id, observation, artifact path를 추적할 수 있다.
- RAG retrieval snapshot과 evaluation log를 artifact로 남겨 설명과 metric을 재검토할 수 있다.
- full event sourcing은 이후 session 수가 늘어날 때 고려한다.

## NFR-002 안전성

결정: RAG output과 optimizer recommendation이 Android client로 가기 전에 ConstraintFilter와 allowlist를 통과해야 한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Backend recommendation을 client가 신뢰 | 구현이 단순함 | unsupported parameter가 encoder action으로 이어질 수 있음 | 제외 |
| Android client에서만 validation | device API와 가까움 | backend search space와 audit trail이 약해짐 | 보류 |
| ConstraintFilter 중심 validation | decision과 audit이 backend에 남음 | filter rule 구현 필요 | 선택 |
| LLM self-check | AI 설명과 통합 쉬움 | 안전 보장을 LLM에 의존하게 됨 | 제외 |

선택 이유:

- RAG constraint candidate는 source reference 없이는 search space에 반영하지 않는다.
- vendor extension key는 allowlist와 capability 검증 없이는 전달하지 않는다.
- optimizer recommendation도 trial assignment 직전에 다시 검증한다.

## NFR-003 구현 가능성

결정: 1인 3개월 MVP에 맞춰 scope를 제한하고, local-first backend로 시작한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Cloud-native multi-device platform | 확장성이 좋음 | 초기 구현과 운영 부담이 큼 | 제외 |
| Android-only implementation | 배포 구조가 단순함 | VMAF/AI/optimizer가 단말 부담을 키움 | 제외 |
| Python backend + SQLite + local artifact store | 빠르게 closed-loop 검증 가능 | 운영 규모는 제한됨 | 선택 |
| Full FastAPI/PostgreSQL stack 우선 | production 구조에 가까움 | 환경 의존성과 bootstrap 부담 증가 | 후속 |

선택 이유:

- 핵심 목표는 platform 완성이 아니라 Android hardware encoder를 포함한 closed-loop 증명이다.
- 첫 codec은 H.264/AVC, 첫 device는 1대로 제한한다.
- mock evaluator와 deterministic cold start를 통해 Android 접근 전에도 backend lifecycle을 검증한다.

## NFR-004 확장성

결정: Android parameter mapping은 `EncoderParameterProxy`, vendor-specific behavior는 `VendorExtensionStrategy`, search space는 versioned schema로 분리한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| `MediaFormat` 직접 mapping | 코드가 짧음 | parameter 추가 시 호출부가 쉽게 오염됨 | 제외 |
| Codec별 client fork | vendor 최적화가 쉬움 | 코드 중복과 유지보수 부담 증가 | 제외 |
| Proxy + Strategy | core loop와 vendor 차이를 분리 | 초기 구조가 조금 늘어남 | 선택 |
| Plugin architecture | 확장성이 매우 큼 | MVP에 과한 추상화 | 후속 |

선택 이유:

- H.265/HEVC, QP, B-frame, vendor extension key를 추가해도 session/trial 모델을 유지할 수 있다.
- MVP에서는 `NoOpExtensionStrategy`로 시작하고, 지원 확인 후 vendor strategy를 추가한다.
- search space version이 있어 확장 전후 trial을 비교할 수 있다.

## NFR-005 관측 가능성

결정: session/trial status, constraint decision, optimizer recommendation, evaluation log, report metadata를 session 단위로 조회 가능하게 한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| 최종 report만 생성 | 구현이 단순함 | 실험 중 장애 원인 파악이 어려움 | 제외 |
| Raw log file 중심 | 기록은 많이 남음 | 상태 조회와 자동 검증이 어려움 | 보류 |
| Metadata status + artifact log | 진행 상태와 실패 원인 추적 가능 | 저장 항목 설계 필요 | 선택 |
| Observability stack 도입 | dashboard와 alert가 좋음 | MVP 운영 부담이 큼 | 후속 |

선택 이유:

- session status는 trial 수, evaluated count, failed count, active search space version을 제공한다.
- evaluation 실패 시 ffmpeg log path 또는 error message를 남긴다.
- AI-Ops는 초기에는 report metadata나 artifact JSON으로 경량 telemetry를 남긴다.

## NFR-006 실패 허용성

결정: configure, encoding, upload, evaluation, RAG 실패를 가능한 한 failed trial 또는 degraded report 상태로 격리하고 loop를 계속 진행한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Fail-fast session abort | 오류 처리가 단순함 | hardware encoder trial 실패가 잦으면 session이 쉽게 중단됨 | 제외 |
| 모든 실패 자동 retry | 성공 가능성 증가 | 같은 unsupported parameter를 반복할 수 있음 | 보류 |
| Failed trial 격리 + duplicate avoidance | loop 지속성과 안전성 균형 | failure classification 필요 | 선택 |
| Self-healing search space 자동 축소 | 운영성이 좋음 | 잘못된 일반화 위험 | 후속 |

선택 이유:

- `configure()` 실패와 evaluation 실패는 failed trial로 기록하고 다음 trial을 진행한다.
- failed parameter는 optimizer duplicate avoidance set에 포함한다.
- search space가 비거나 objective 계산이 반복 실패할 때만 조기 종료한다.
- 조기 종료 시에도 실패 report를 생성한다.

## NFR-007 AI guardrails와 AI-Ops

결정: schema/source/action/report guardrails와 lightweight AI-Ops telemetry를 적용한다.

| 후보 | 장점 | 단점 | 판단 |
| --- | --- | --- | --- |
| Guardrail 없음 | 구현이 빠름 | RAG hallucination이 action/report에 섞일 수 있음 | 제외 |
| Prompt-level guardrail만 적용 | 도입이 쉬움 | 실제 trial assignment safety를 보장하지 못함 | 제외 |
| Schema/source/action/report guardrails | action 경로와 report 신뢰도를 통제 | schema와 test가 필요함 | 선택 |
| Full AI-Ops platform | 운영성이 높음 | 1인 MVP에 과함 | 후속 |

선택 이유:

- RAG output은 schema validation과 source validation을 통과해야 한다.
- action guardrail은 ConstraintFilter가 담당한다.
- report guardrail은 raw metric, deterministic derived result, AI-assisted narrative를 분리한다.
- AI-Ops는 prompt/source/search space/evaluator/report versioning과 session-level telemetry에서 시작한다.

## NFR 간 trade-off

NFR은 서로 보강하기도 하지만 충돌도 있다.

| Trade-off | 선택한 균형 |
| --- | --- |
| 재현성 vs 구현 속도 | SQLite metadata와 artifact snapshot까지만 구현하고 full event sourcing은 미룬다. |
| 안전성 vs 탐색 폭 | QP, B-frame, vendor extension은 후속 확장으로 두고 1차 parameter를 제한한다. |
| 관측 가능성 vs 구현 범위 | dashboard 대신 status API, metadata, artifact log로 시작한다. |
| 실패 허용성 vs 잘못된 일반화 | failed trial은 보존하지만 observation 하나만으로 전역 rule을 만들지 않는다. |
| AI-Ops vs MVP 범위 | telemetry와 versioning은 남기되 full platform은 후속으로 둔다. |

## FR과의 연결

| NFR | 영향을 크게 받는 FR |
| --- | --- |
| NFR-001 재현성 | FR-001, FR-004, FR-006, FR-008, FR-009 |
| NFR-002 안전성 | FR-003, FR-004, FR-005, FR-007 |
| NFR-003 구현 가능성 | FR-001, FR-004, FR-006, FR-010 |
| NFR-004 확장성 | FR-002, FR-003, FR-005, FR-009 |
| NFR-005 관측 가능성 | FR-001, FR-006, FR-008, FR-009 |
| NFR-006 실패 허용성 | FR-004, FR-005, FR-006, FR-007 |
| NFR-007 AI guardrails와 AI-Ops | FR-003, FR-004, FR-007, FR-008, FR-009 |

## 결론

현재 설계는 NFR을 고려하고 있다. 다만 기존 요구사항 문서만 보면 NFR별 후보 비교가 FR보다 약하게 보일 수 있었다. 이 matrix를 통해 NFR이 architecture decision의 근거로 작동했음을 명시한다.
