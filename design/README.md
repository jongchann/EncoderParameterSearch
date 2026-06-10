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

## 참조 ADR

- [ADR 001: Encoder Parameter Search MVP Architecture](../adr/adr_001_encoder_parameter_search_mvp.md)
- [ADR 002: Encoder Parameter Search Feasibility and MVP Scope](../adr/adr_002_parameter_search_feasibility.md)

## 설계 원칙

- MVP는 실제 Android hardware encoder에서 closed-loop search를 수행해 baseline 대비 개선된 parameter 후보를 찾는 데 집중한다.
- 최종 trial parameter는 optimizer가 결정하며, LLM/RAG 출력은 constraint 후보와 설명으로 제한한다.
- Unsupported parameter는 Android client로 내려가기 전에 backend constraint filter에서 제거한다.
- 모든 trial은 재현 가능한 audit trail을 남긴다.
