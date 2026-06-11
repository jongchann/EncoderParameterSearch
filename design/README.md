# Encoder Parameter Search Software Design

이 디렉터리는 ADR 001, ADR 002를 바탕으로 작성한 소프트웨어 설계 단계별 산출물이다.

## 설계 산출물

| 단계 | 문서 | 목적 |
| --- | --- | --- |
| 0 | [00_design_overview.md](00_design_overview.md) | 설계 범위, 핵심 결정, 문서 관계 정의 |
| 1 | [01_requirements.md](01_requirements.md) | 기능/비기능 요구사항과 MVP 성공 기준 정의 |
| 2 | [02_system_architecture.md](02_system_architecture.md) | 전체 시스템 구조, 책임 분리, 주요 흐름 정의 |
| 3 | [03_component_design.md](03_component_design.md) | Android client, backend, optimizer, RAG agent 컴포넌트 설계 |
| 4 | [04_data_api_design.md](04_data_api_design.md) | 데이터 모델, API, artifact 저장 규칙 정의 |
| 5 | [05_algorithm_and_rag_design.md](05_algorithm_and_rag_design.md) | parameter search, constraint filter, RAG 보조 흐름 설계 |
| 6 | [06_verification_plan.md](06_verification_plan.md) | 테스트, 실험 검증, 리포트 산출 기준 정의 |
| 7 | [07_risk_and_roadmap.md](07_risk_and_roadmap.md) | 주요 리스크, 완화 전략, MVP 이후 확장 계획 정의 |
| 8 | [08_implementation_plan.md](08_implementation_plan.md) | MVP 구현 순서, API, 테스트 계획 정의 |
| 9 | [09_implementation_progress.md](09_implementation_progress.md) | 구현 진행 상태, 검증 결과, 다음 단계 기록 |
| 10 | [10_design_review_and_evolution.md](10_design_review_and_evolution.md) | 전체 설계 리뷰, AI 책임 경계, 발전 우선순위 정리 |
| 11 | [11_ai_guardrails_and_aiops.md](11_ai_guardrails_and_aiops.md) | AI guardrails, AI-Ops 적용 가능성, 운영 기준 정리 |
| 12 | [12_fr_decision_matrix.md](12_fr_decision_matrix.md) | FR별 설계 후보, 장단점, 최종 결정 근거 정리 |
| 13 | [13_nfr_decision_matrix.md](13_nfr_decision_matrix.md) | NFR별 설계 후보, 품질 속성 trade-off, 최종 결정 근거 정리 |
| 14 | [14_implementation_gap_review.md](14_implementation_gap_review.md) | 설계 강화 이후 현재 구현 gap과 후속 작업 우선순위 정리 |

## 추천 읽기 순서

평가자가 설계 의도를 빠르게 파악해야 한다면 다음 순서로 읽는다.

1. [00_design_overview.md](00_design_overview.md): 프로젝트 목표와 책임 분리
2. [02_system_architecture.md](02_system_architecture.md): Android/backend/optimizer/RAG 구조
3. [05_algorithm_and_rag_design.md](05_algorithm_and_rag_design.md): parameter search와 RAG 안전 경계
4. [06_verification_plan.md](06_verification_plan.md): 검증 전략과 성공 기준
5. [09_implementation_progress.md](09_implementation_progress.md): 현재 구현 상태
6. [10_design_review_and_evolution.md](10_design_review_and_evolution.md): 설계 리뷰와 다음 발전 방향
7. [11_ai_guardrails_and_aiops.md](11_ai_guardrails_and_aiops.md): AI guardrails와 AI-Ops 적용 범위
8. [12_fr_decision_matrix.md](12_fr_decision_matrix.md): FR별 후보 비교와 결정 근거
9. [13_nfr_decision_matrix.md](13_nfr_decision_matrix.md): NFR별 후보 비교와 품질 속성 trade-off
10. [14_implementation_gap_review.md](14_implementation_gap_review.md): 구현 gap과 다음 작업 우선순위

## 참조 ADR

- [ADR 001: Encoder Parameter Search MVP Architecture](../adr/adr_001_encoder_parameter_search_mvp.md)
- [ADR 002: Encoder Parameter Search Feasibility and MVP Scope](../adr/adr_002_parameter_search_feasibility.md)

## 설계 원칙

- MVP는 실제 Android hardware encoder에서 closed-loop search를 수행해 baseline 대비 개선된 parameter 후보를 찾는 데 집중한다.
- 최종 trial parameter는 optimizer가 결정하며, LLM/RAG 출력은 constraint 후보와 설명으로 제한한다.
- Unsupported parameter는 Android client로 내려가기 전에 backend constraint filter에서 제거한다.
- 모든 trial은 재현 가능한 audit trail을 남긴다.
- 목표 설계와 현재 구현 상태를 분리해 기록한다.
- AI guardrails는 RAG schema, source validation, ConstraintFilter, report trust level로 구현한다.
- AI-Ops는 prompt/source/search space/evaluator/report versioning과 session-level telemetry에서 경량으로 시작한다.
- 주요 FR은 후보군의 장단점과 최종 선택 근거를 함께 기록한다.
- 주요 NFR은 품질 속성별 trade-off와 architecture decision 근거를 함께 기록한다.
- 설계와 구현의 차이는 gap review 문서에 기록하고 Step별 후속 작업으로 연결한다.
