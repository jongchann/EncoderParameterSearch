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

## MVP 완화 원칙

- 실패 trial은 숨기지 않고 session report에 포함한다.
- Capability가 불확실한 parameter는 search space에서 제외한다.
- 개선 효과가 작아도 closed-loop, audit trail, Pareto 산출이 성공하면 MVP 목표를 만족한다.
- RAG Agent 실패는 optimizer loop 중단 사유가 아니다.

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

