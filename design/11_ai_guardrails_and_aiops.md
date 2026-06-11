# 11. AI Guardrails and AI-Ops

## 목적

이 문서는 Encoder Parameter Search 설계에 AI guardrails와 AI-Ops 개념을 어떻게 적용할 수 있는지 검토하고, MVP에서 적용할 범위와 후속 확장 범위를 구분한다.

결론부터 말하면 두 개념 모두 적용 가능하다. 다만 이 프로젝트에서 AI는 최종 parameter 결정자가 아니므로, guardrail의 중심은 prompt moderation이 아니라 `RagOutput`, `ConstraintFilter`, `OptimizerService`, `ReportService` 사이의 정책 게이트와 audit trail이다. AI-Ops도 LLM 운영만이 아니라 RAG 품질, optimizer 품질, evaluation 품질을 함께 관측하는 실험 운영 체계로 해석하는 것이 적절하다.

## 적용 가능성 요약

| 개념 | 적용 가능성 | MVP 적용 수준 | 이유 |
| --- | --- | --- | --- |
| AI guardrails | 높음 | 필수 | RAG output이 search space와 report에 영향을 줄 수 있으므로 정책 게이트가 필요하다. |
| AI-Ops | 중간-높음 | 경량 적용 | 1인 MVP에서는 full platform은 과하지만 prompt/source/model/evaluation versioning과 품질 metric은 설계 가치를 높인다. |
| Human-in-the-loop | 중간 | 선택 | MVP 자동 루프에는 넣지 않되, report review와 constraint allowlist 승인 단계에 둘 수 있다. |
| Model monitoring | 중간 | 후속 | RAG provider가 실제 도입된 뒤 latency, failure, source coverage를 관측한다. |
| Drift detection | 낮음-중간 | 후속 | 초기에는 device 1대와 corpus 제한으로 drift 개념이 작지만, 다중 기기/문서 갱신 이후 필요하다. |

## AI guardrails 적용 지점

### 1. Input guardrails

RAG Agent에 들어가는 입력을 제한한다.

- Retrieval corpus는 allowlist된 Android CDD, `MediaCodec`, `MediaFormat`, vendor 문서, session log로 제한한다.
- User-supplied free text가 prompt에 들어갈 경우 instruction과 evidence 영역을 분리한다.
- Trial log와 encoder log는 source로 쓰되, prompt instruction으로 해석하지 않는다.
- 외부 문서가 추가되면 source id와 snapshot path를 먼저 부여한다.

### 2. Retrieval guardrails

검색 결과의 품질을 통제한다.

- 최소 source reference 조건을 둔다.
- document title, section, uri, retrieval score, retrieved_at을 저장한다.
- source가 부족한 output은 report 참고 설명으로도 낮은 trust level을 부여한다.
- retrieval snapshot을 artifact로 저장해 나중에 같은 결론을 재검토할 수 있게 한다.

### 3. Output guardrails

LLM/RAG 출력은 schema와 source 조건을 통과해야 한다.

- `constraint_candidate`, `failure_analysis`, `report_section`별 JSON schema를 둔다.
- JSON schema 검증 실패 시 `RagOutput.status = ignored`로 저장한다.
- source reference가 없는 constraint candidate는 search space에 반영하지 않는다.
- RAG narrative는 raw metric이나 Pareto result를 덮어쓰지 않는다.

### 4. Action guardrails

AI output이 실제 encoder action으로 이어지는 경로를 차단한다.

```text
RagOutput
  -> schema/source validation
  -> ConstraintFilter accepted/rejected decision
  -> SearchSpace version update
  -> Optimizer recommendation
  -> ConstraintFilter re-validation
  -> Trial assignment
```

핵심 원칙:

- RAG Agent는 Android client로 parameter를 직접 보내지 않는다.
- Optimizer recommendation도 trial assignment 전에 다시 ConstraintFilter를 통과한다.
- Vendor extension key는 allowlist와 capability 검증 없이는 내려가지 않는다.
- Failed trial observation 하나만으로 전역 constraint를 만들지 않는다.

### 5. Report guardrails

Report에서 AI가 만든 설명과 측정 사실을 구분한다.

| Report 영역 | Source | Trust level |
| --- | --- | --- |
| Trial table | MetadataStore | Raw metric |
| VMAF/bitrate | EvaluationService | Raw metric |
| Pareto Set | ReportService deterministic calculation | Deterministic derived result |
| Baseline comparison | BaselineService/ReportService | Deterministic derived result |
| Constraint explanation | RagAgentService with source | AI-assisted narrative |
| Failure cause candidate | RagAgentService with trial log | AI-assisted narrative |

RAG 문장은 source-backed interpretation으로 표시하고, 최종 decision처럼 표현하지 않는다.

## Guardrail policy matrix

| 위험 | Guardrail | 실패 시 동작 | Audit |
| --- | --- | --- | --- |
| RAG hallucination | source reference 필수 | constraint 미반영, report 근거 제외 | `RagOutput.status`, `ConstraintDecision.reason` |
| Prompt injection | corpus allowlist와 instruction/data 분리 | 해당 source 무시 | retrieval snapshot |
| Unsupported parameter | capability와 ADR rule 검증 | rejected decision 저장 | `ConstraintDecision` |
| Vendor key 오용 | allowlist와 적용 검증 | Android client 전달 금지 | rejected vendor key |
| Metric 조작 | RAG가 raw metric 수정 불가 | report section 거부 | report trust level |
| Optimizer 반복 추천 | evaluated/failed params 중복 회피 | recommendation rejected | `OptimizerRecommendation.status` |
| 실패 trial 과잉 일반화 | failure observation 단독 rule 승격 금지 | candidate로만 저장 | source_type=`observation` |
| RAG timeout | optimizer loop 계속 진행 | RAG unavailable 표시 | `RagOutput.status=ignored` 또는 report metadata |

## AI-Ops 적용 지점

AI-Ops는 이 프로젝트에서 다음 운영 질문에 답하는 체계다.

- 어떤 prompt version과 corpus snapshot으로 report가 생성됐는가
- RAG가 제안한 constraint 중 몇 개가 accepted/rejected 되었는가
- RAG 실패가 optimizer loop에 영향을 주지 않았는가
- optimizer가 random baseline 대비 더 나은 Pareto 후보를 찾았는가
- evaluator failure가 특정 device, codec, parameter에 편향되어 있는가
- report의 AI-assisted narrative가 source coverage를 충분히 갖는가

## AI-Ops telemetry

MVP에서는 heavyweight observability platform 대신 metadata와 artifact를 이용한 경량 telemetry로 충분하다.

| 영역 | Metric/Event | 저장 위치 |
| --- | --- | --- |
| RAG | prompt version, retrieval count, source coverage, schema validation result | `RagOutput`, `rag/retrieval_snapshots/` |
| Constraint | accepted/rejected count, rejection reason, source type | `ConstraintDecision` |
| Optimizer | phase, seed, duplicate avoidance, recommendation status | `OptimizerRecommendation.metadata` |
| Evaluation | evaluator mode, ffmpeg return code, VMAF parse status | evaluation log artifact |
| Android | requested/applied mismatch, unknown params, configure failure | Trial metadata, encoder log |
| Report | trust level counts, source-less narrative count | `ReportMetadata` |

## AI-Ops lifecycle

```text
version inputs
  -> run session
  -> collect telemetry
  -> generate report
  -> review guardrail violations
  -> decide promote/rollback/keep experimental
```

### Versioning

다음 항목은 version 또는 snapshot을 남긴다.

- prompt template version
- retrieval corpus version
- source snapshot path
- search space version
- optimizer phase and seed
- evaluator mode and command
- report template version

### Release gate

RAG Agent 또는 optimizer를 교체할 때는 다음 gate를 통과해야 한다.

- Source 없는 constraint candidate가 search space에 반영되지 않는다.
- 동일 session fixture에서 report raw metric이 바뀌지 않는다.
- 추천 parameter가 active search space 밖으로 나가지 않는다.
- RAG failure가 trial assignment API 실패로 전파되지 않는다.
- 최소 15 trial mock lifecycle이 계속 통과한다.

### Rollback 기준

다음 조건에서는 새 RAG prompt, retrieval corpus, optimizer strategy를 되돌린다.

- accepted constraint 중 source reference가 비어 있는 항목이 발생한다.
- unsupported parameter가 Android client로 전달된다.
- report가 AI narrative를 raw metric처럼 표시한다.
- duplicate recommendation 비율이 증가한다.
- evaluation failure가 특정 변경 이후 급증한다.

## MVP 적용 범위

MVP에 바로 넣기 좋은 범위:

- RAG output schema validation
- source reference required policy
- prompt version과 retrieval snapshot 저장
- report trust level 표시
- ConstraintFilter re-validation
- RAG failure가 optimizer loop를 막지 않는 fallback
- optimizer/evaluator/report metadata를 이용한 경량 telemetry

후속으로 미루는 것이 좋은 범위:

- 별도 AIOps dashboard
- automated drift detector
- live model performance monitoring
- human approval workflow
- multi-provider LLM routing
- prompt A/B test platform

## 설계 반영 위치

| 문서 | 반영 내용 |
| --- | --- |
| [04_data_api_design.md](04_data_api_design.md) | `RagOutput`, source schema, AI-Ops event 후보 |
| [05_algorithm_and_rag_design.md](05_algorithm_and_rag_design.md) | RAG processing pipeline과 guardrail 단계 |
| [06_verification_plan.md](06_verification_plan.md) | guardrail test와 AI-Ops release gate |
| [07_risk_and_roadmap.md](07_risk_and_roadmap.md) | RAG hallucination, 운영 drift, rollback 리스크 |
| [10_design_review_and_evolution.md](10_design_review_and_evolution.md) | 평가자 관점에서 AI 책임 경계 설명 |

## 결론

AI guardrails는 MVP 설계에 반드시 포함하는 것이 좋다. 이미 존재하는 `ConstraintFilter`, `RagOutput`, source reference, report trust level이 guardrail 역할을 할 수 있으므로 추가 구현 부담도 크지 않다.

AI-Ops는 MVP에서 경량으로 시작하는 것이 적절하다. 별도 플랫폼을 만들기보다 prompt/source/search space/evaluator/report versioning과 session-level telemetry를 남기면 충분하다. 이후 다중 기기, 외부 LLM provider, optimizer 교체가 들어오면 dashboard, drift detection, rollback workflow로 확장한다.
