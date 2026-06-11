# 10. Design Review and Evolution

## 목적

이 문서는 현재 설계를 평가자 관점에서 다시 점검하고, AI가 포함된 설계 프로젝트로서 더 잘 드러나야 하는 판단 근거와 발전 방향을 정리한다.

핵심 메시지는 다음과 같다.

- 이 프로젝트는 단순한 encoder 튜닝 스크립트가 아니라 Android hardware encoder, backend optimizer, RAG Agent를 분리한 closed-loop 실험 시스템이다.
- LLM/RAG는 최종 parameter 결정자가 아니라 문서 근거 기반 constraint 후보와 설명 생성자로 제한된다.
- 모든 trial은 requested/applied parameter, artifact, observation, optimizer recommendation, constraint decision을 통해 재현 가능한 audit trail을 가진다.
- 현재 구현은 backend closed-loop skeleton과 Android smoke-test app까지 진행됐고, RAG Agent와 real VMAF parsing은 명확한 다음 단계로 남아 있다.

## 리뷰 기준

설계 완성도는 기능 수보다 다음 기준으로 평가한다.

| 기준 | 질문 | 현재 판단 |
| --- | --- | --- |
| 문제 정의 | 왜 Android 단말과 backend를 분리해야 하는가 | 단말 제약과 VMAF/AI 비용을 근거로 설명됨 |
| 책임 분리 | optimizer, RAG, constraint filter의 권한이 구분되는가 | 핵심 경계는 명확하나 RAG 저장 모델 보강 필요 |
| 안전성 | LLM 출력이 직접 encoder 설정으로 이어지지 않는가 | ConstraintFilter 재검증으로 방어 |
| 재현성 | trial decision을 나중에 역추적할 수 있는가 | search space version, optimizer id, requested/applied 분리로 가능 |
| 구현 가능성 | 1인 3개월 MVP 범위로 줄였는가 | 1 device, H.264/AVC, 3개 parameter로 제한 |
| 검증 가능성 | 문서 요구사항이 테스트와 연결되는가 | backend 테스트는 존재하나 RAG/real evaluator gate 보강 필요 |
| 진화 가능성 | MVP 이후 확장 방향이 구조와 충돌하지 않는가 | Strategy/Proxy, versioned search space로 확장 가능 |
| AI 운영성 | prompt, source, optimizer, evaluator 변경을 추적할 수 있는가 | AI-Ops telemetry와 rollback 기준 보강 필요 |

## 현재 설계의 강점

### 1. AI 책임을 수치 결정에서 분리했다

LLM이 다음 parameter를 직접 추천하지 않고, optimizer가 VMAF maximize와 bitrate minimize를 담당한다. RAG Agent는 문서 검색, constraint 후보, 실패 원인 후보, report draft에 집중한다.

이 분리는 AI가 포함된 프로젝트에서 중요한 설계 판단이다. AI의 설명 능력은 활용하되, 수치 최적화의 재현성과 안전성을 훼손하지 않는다.

### 2. Android hardware 특성을 설계 중심에 놓았다

Backend simulation만으로 끝내지 않고, Android Client가 실제 `MediaCodec` capability discovery와 encoding trial을 맡는다. 이 선택은 구현 난이도를 높이지만 프로젝트 목표와 잘 맞는다.

### 3. Audit trail이 설계의 1급 요소다

`search_space_version`, `optimizer_trial_id`, `requested_params`, `applied_params`, `applied_params_unknown`, `constraint_decisions`가 분리되어 있다. 따라서 최종 후보가 어떤 제약과 observation을 거쳐 선택됐는지 추적할 수 있다.

### 4. MVP scope가 현실적이다

초기 search space를 `bitrate_kbps`, `i_frame_interval_sec`, capability-supported `profile`로 제한한다. QP, B-frame, vendor extension key는 설계상 매력적이지만 단말 편차가 커서 후속 확장으로 미뤘다.

## 보강이 필요한 지점

### 1. 목표 설계와 현재 구현 상태를 분리해야 한다

문서 일부는 Optuna NSGA-II, RAG Agent, real VMAF 평가를 목표 설계처럼 설명하지만, 현재 구현은 deterministic cold-start optimizer, mock evaluator, Markdown report 중심이다.

개선 방향:

- design 문서에서는 target architecture와 current implementation maturity를 분리한다.
- progress 문서에서는 미구현 기능을 gap으로 남기되, 왜 그 순서가 합리적인지 설명한다.
- README는 현재 실행 가능한 surface와 설계 목표를 동시에 보여준다.

### 2. RAG 저장 모델과 source contract가 더 구체적이어야 한다

RAG가 search space에 영향을 줄 수 있으려면 출력이 어떤 형태로 저장되고 검증되는지 분명해야 한다.

보강할 계약:

- `RagOutput` metadata model
- source id, document title, section, retrieval score 또는 observation id
- prompt version과 retrieval snapshot
- source 없는 constraint candidate는 rejected decision으로만 저장
- accepted/rejected 최종 권한은 `ConstraintFilter`

### 3. Report가 “AI 설명”과 “측정값”을 구분해야 한다

최종 report는 metric table과 RAG 설명을 함께 담되, 둘의 신뢰 수준을 구분해야 한다.

보강할 계약:

- raw metric: backend evaluator와 MetadataStore에서 나온 사실
- derived result: Pareto Set, baseline comparison
- AI-assisted narrative: RAG가 작성한 설명 초안
- decision audit: ConstraintFilter와 Optimizer가 실제로 결정한 기록

RAG 문장은 결론처럼 보이면 안 되고, source-backed interpretation으로 표시되어야 한다.

### 4. Real evaluator의 불확실성을 명시해야 한다

현재 real evaluator는 ffmpeg/libvmaf 실행 경계를 두었지만 VMAF parsing은 아직 gap이다. 설계 문서에는 이 gap을 실패가 아니라 의도된 단계적 구현으로 기록해야 한다.

완료 기준:

- ffmpeg command, stdout, stderr, return code 저장
- VMAF score parsing
- reference video checksum 기록
- 평가 실패 시 failed trial과 log 보존

### 5. Optimizer maturity level을 단계화해야 한다

MVP 초기 구현은 deterministic cold-start만으로도 closed-loop를 검증할 수 있다. 그러나 설계 목표는 multi-objective optimization이다.

단계:

1. Deterministic cold start: 중복 회피와 lifecycle 검증
2. Random/Sobol/LHS baseline: search baseline 확보
3. NSGA-II 또는 동등한 MOBO: Pareto 확장
4. Random search 대비 개선 비교: optimizer 사용 이유 검증

### 6. AI guardrails와 AI-Ops를 명시적 설계 요소로 둘 수 있다

현재 설계의 `ConstraintFilter`, `RagOutput`, source reference, report trust level은 이미 guardrail 역할을 한다. 여기에 prompt/source/search space/evaluator/report versioning과 session-level telemetry를 더하면 경량 AI-Ops도 자연스럽게 붙는다.

MVP에서는 별도 운영 플랫폼보다 다음을 우선한다.

- schema/source/action/report guardrail test
- prompt version과 retrieval snapshot 저장
- guardrail blocked event 기록
- RAG/optimizer/evaluator 변경 시 release gate
- report에서 AI-assisted narrative와 raw metric 구분

## 발전된 목표 아키텍처

```text
+--------------------+       +---------------------+
| Android Client     |       | Backend API         |
| - Capability       | ----> | - Session/Trial     |
| - MediaCodec       |       | - Upload/Evaluate   |
| - Applied metadata | <---- | - Report            |
+--------------------+       +----------+----------+
                                      |
             +------------------------+------------------------+
             |                        |                        |
             v                        v                        v
    +------------------+      +------------------+      +------------------+
    | ConstraintFilter |      | OptimizerService |      | RagAgentService  |
    | - Rule/capability|      | - Cold start     |      | - Retrieval      |
    | - RAG validation |      | - MOBO target    |      | - Explanation    |
    | - Audit decision |      | - Pareto data    |      | - Source snapshot|
    +------------------+      +------------------+      +------------------+
             |                        |                        |
             +------------------------+------------------------+
                                      v
                            +------------------+
                            | MetadataStore    |
                            | ArtifactStore    |
                            +------------------+
```

중요한 권한 관계:

- `RagAgentService`는 `ConstraintCandidate`와 report draft만 만든다.
- `ConstraintFilter`는 candidate를 accepted/rejected decision으로 확정한다.
- `OptimizerService`는 accepted search space 안에서만 parameter를 추천한다.
- `SessionService`는 추천값을 다시 검증한 뒤 Android Client로 내려보낸다.
- `ReportService`는 metric, decision, RAG narrative의 출처를 분리해서 표시한다.

## 설계 문서 발전 방향

| 문서 | 보강 방향 |
| --- | --- |
| 00 Overview | 설계 평가 관점과 구현 maturity 구분 추가 |
| 01 Requirements | RAG output, report trust level, optimizer maturity 수용 기준 보강 |
| 02 Architecture | 권한 경계와 data/control flow를 더 명시 |
| 03 Component | RagAgentService, ReportService, real evaluator 책임 세분화 |
| 04 Data/API | `RagOutput`, `ReportMetadata`, source snapshot 계약 추가 |
| 05 Algorithm/RAG | RAG governance, source schema, prompt/retrieval version 추가 |
| 06 Verification | AI safety gate, report trust-level 검증, doc-code traceability 추가 |
| 07 Risk/Roadmap | current design debt와 next decision point 추가 |
| 09 Progress | target과 current gap을 계속 분리 기록 |

## 다음 설계 결정 후보

### ADR 003: RAG Agent provider와 storage contract

결정할 내용:

- local retrieval만 사용할지, 외부 LLM API를 사용할지
- source snapshot 저장 범위
- prompt versioning 방식
- RAG failure를 report에 표시하는 방식

### ADR 004: Real evaluation pipeline

결정할 내용:

- ffmpeg/libvmaf command contract
- raw bitstream과 container 처리
- reference video identity와 checksum
- VMAF parsing format

### ADR 005: Optimizer upgrade path

결정할 내용:

- deterministic cold-start 이후 NSGA-II를 언제 도입할지
- random search baseline을 어떻게 비교할지
- 작은 trial 수에서 optimizer 개선을 어떤 지표로 설명할지

### ADR 006: AI guardrails and AI-Ops policy

결정할 내용:

- Guardrail policy를 code-level test로 어디까지 강제할지
- AI-Ops event 저장을 metadata table로 둘지 artifact JSON으로 둘지
- prompt/source/optimizer/evaluator version 변경의 release gate
- rollback 기준과 report trust level 표시 방식

## 평가자에게 보여줄 핵심 문장

최종 발표나 README에서 다음 문장으로 프로젝트 의도를 압축할 수 있다.

> This system uses AI as a source-grounded design assistant, not as an unchecked parameter oracle. The optimizer owns numeric decisions, the constraint filter owns safety, and the RAG agent owns explanation and evidence discovery.

한국어 설명:

> 이 시스템에서 AI는 검증되지 않은 parameter 결정자가 아니라 근거 문서를 찾고 설명을 돕는 보조 계층이다. 수치 결정은 optimizer가, 안전 경계는 constraint filter가, 설명과 근거 수집은 RAG Agent가 맡는다.

## 발전 우선순위

1. `RagOutput` 저장 모델과 source schema를 확정한다.
2. AI guardrail policy와 AI-Ops event 저장 방식을 확정한다.
3. Report에 raw metric, derived result, AI-assisted narrative를 분리 표시한다.
4. real evaluator의 VMAF parsing과 reference video checksum을 완성한다.
5. backend-only 15 trial closed-loop smoke test를 progress 문서에 연결한다.
6. Android real-device one-artifact upload를 Step 11 완료 기준으로 검증한다.
7. deterministic cold-start 이후 random baseline과 NSGA-II upgrade를 비교 가능하게 만든다.
