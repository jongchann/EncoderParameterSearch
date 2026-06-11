# 07. Risk and Roadmap

## 목적

이 문서는 MVP 구현 중 실패 가능성이 큰 지점을 미리 식별하고, 설계상 완화 전략과 후속 확장 순서를 정의한다.

## 주요 리스크

| 리스크 | 영향 | 완화 전략 |
| --- | --- | --- |
| Android encoder가 requested parameter를 무시함 | Observation 신뢰도 저하 | requested/applied/unknown parameter를 분리 기록 |
| `profile` 지원 정보와 실제 configure 결과가 다름 | Trial 실패 증가 | configure 실패를 constraint decision 후보로 기록하되 일반 rule로 즉시 승격하지 않음 |
| VMAF 측정 실패 | Objective 계산 불가 | artifact와 ffmpeg 로그 보존, 해당 trial은 failed evaluation으로 기록 |
| Trial 수가 적어 BD-Rate 계산이 불안정함 | 개선 효과 설명 약화 | BD-Rate가 불충분하면 VMAF-bitrate table/plot 비교로 대체 |
| RAG Agent hallucination | 잘못된 constraint 반영 위험 | source reference 필수화, ConstraintFilter 검증 없이는 search space 변경 금지 |
| Vendor extension key 적용 여부 불명확 | 탐색 결과 해석 어려움 | MVP 핵심 경로에서 제외하고 allowlist와 적용 검증 후 확장 |
| 단말 발열과 throttling | Trial 간 성능 편차 증가 | trial metadata에 device temperature 후보, timestamp, duration 기록 |
| 목표 설계와 현재 구현 상태 혼동 | 평가자가 완성 범위를 오해 | progress 문서와 review 문서에서 current/target을 분리 기록 |
| RAG output 저장 계약 부재 | AI 설명의 재현성 저하 | `RagOutput`, prompt version, retrieval snapshot을 Step 13 gate로 정의 |
| Real VMAF parsing 미완성 | 실제 objective 검증 지연 | ffmpeg log 보존 후 parsing 구현을 별도 completion gate로 관리 |
| Guardrail 우회 경로 발생 | RAG output이 action으로 직접 연결될 위험 | RAG는 `ConstraintFilter`와 trial assignment API를 우회할 수 없도록 component boundary 유지 |
| Prompt/corpus 변경에 따른 운영 회귀 | 같은 session에서도 설명과 constraint 후보가 불안정 | prompt/source versioning, AI-Ops release gate, rollback 기준 운영 |

## MVP 완화 원칙

- 실패 trial은 숨기지 않고 session report에 포함한다.
- Capability가 불확실한 parameter는 search space에서 제외한다.
- 개선 효과가 작아도 closed-loop, audit trail, Pareto 산출이 성공하면 MVP 목표를 만족한다.
- RAG Agent 실패는 optimizer loop 중단 사유가 아니다.
- AI guardrail이 block한 항목은 action으로 이어지지 않아야 한다.
- Prompt, corpus, optimizer, evaluator 변경은 version과 rollback 기준을 남긴다.

## 단계별 구현 로드맵

### Phase 1: Backend skeleton

- Session, trial, metadata store 구현
- Search space 생성
- Constraint decision log 구현
- Mock artifact 기반 evaluation 흐름 구현

완료 기준:

- Android client 없이도 mock trial 15회 lifecycle을 재현할 수 있다.

### Phase 2: Android encoding integration

- CapabilityReporter 구현
- EncoderParameterProxy 구현
- TrialRunner와 artifact upload 구현

완료 기준:

- 실제 Android device에서 1개 trial artifact를 backend에 업로드한다.

### Phase 3: Evaluation and optimizer loop

- `ffmpeg`/`libvmaf` evaluation 연결
- Cold start와 multi-objective optimizer 연결
- Pareto Set 계산

완료 기준:

- 동일 입력 영상 기준 최소 15회 closed-loop trial을 완료한다.

### Phase 4: RAG and reporting

- 제한된 corpus 기반 retrieval 구현
- Constraint candidate schema 구현
- Failure analysis와 final report 생성

완료 기준:

- 최종 report에 metric, Pareto 결과, constraint 근거, 실패 해석이 함께 포함된다.

## MVP 이후 확장

- 다중 Android device session 지원
- H.265/HEVC codec 추가
- `bitrate_mode`, B-frame, QP parameter 확장
- Vendor extension strategy별 allowlist 확장
- BoTorch qNEHVI 등 고급 MOBO 비교
- 축적된 benchmark 기반 prior 또는 fine-tuning 검토

## 현재 설계 debt

현재 debt는 구현 실패라기보다 단계적 MVP에서 의도적으로 남긴 결정 지점이다.

| Debt | 영향 | 해소 조건 |
| --- | --- | --- |
| RAG Agent 미구현 | AI 보조 설계가 아직 실행 경로에 없음 | `RagOutput` schema, retrieval snapshot, source validation 구현 |
| Deterministic cold-start optimizer | multi-objective optimizer 효과를 아직 비교하지 못함 | random baseline과 NSGA-II 또는 동등한 optimizer 추가 |
| Real VMAF parsing 미구현 | 실제 quality metric을 자동 산출하지 못함 | libvmaf 출력 parsing과 reference checksum 저장 |
| Android real-device E2E 미검증 | hardware encoder 실험 증거가 부족함 | Mock mode가 아닌 real upload 1회 성공 |
| FastAPI 선언과 stdlib server 구현 차이 | 기술 스택 설명 혼동 가능 | 환경 제약 유지 시 stdlib server를 명시하거나 FastAPI 전환 ADR 작성 |
| AI-Ops telemetry 미구현 | RAG/optimizer 변경 효과를 운영적으로 비교하기 어려움 | `AiOpsEvent` 또는 report metadata 기반 경량 event 저장 |

## 다음 ADR 후보

### ADR 003: RAG Agent implementation contract

결정 항목:

- local retrieval과 외부 LLM/API 사용 여부
- corpus 저장 위치와 snapshot 범위
- prompt versioning 방식
- RAG output의 trust level 표시 방식

### ADR 004: Real evaluator contract

결정 항목:

- raw H.264 bitstream을 평가 가능한 container로 변환할지 여부
- reference video checksum과 metadata 저장 방식
- libvmaf output parsing format
- evaluation retry와 failure policy

### ADR 005: Optimizer upgrade strategy

결정 항목:

- deterministic cold-start 이후 어떤 optimizer를 도입할지
- 작은 trial 수에서 random search 대비 개선을 어떤 지표로 보고할지
- optimizer state를 어느 수준까지 저장할지

### ADR 006: AI guardrails and AI-Ops policy

결정 항목:

- Guardrail policy를 code-level test로 어디까지 강제할지
- AI-Ops event를 별도 table로 둘지 artifact JSON으로 둘지
- prompt/source/optimizer/evaluator version 변경의 release gate
- rollback 기준과 report trust level 표시 방식
