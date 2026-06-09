# 02. System Architecture

## 전체 구조

```text
+------------------+        +-------------------+        +------------------+
| Android Client   |        | Backend API       |        | Artifact Store   |
|                  | <----> |                   | <----> |                  |
| - Capability     |        | - Session         |        | - Encoded files  |
| - MediaCodec     |        | - Trial control   |        | - Logs           |
| - Upload         |        | - Evaluation      |        | - Reports        |
+------------------+        +---------+---------+        +------------------+
                         /            |            \
                        v             v             v
          +-------------+--+   +------+-------+   +--+---------------+
          | Constraint     |   | Optimizer    |   | RAG Agent        |
          | Filter         |   |              |   |                  |
          | - Rules        |   | - Recommend  |   | - Search docs    |
          | - Validation   |   | - Pareto     |   | - Explain        |
          | - Search space |   | - History    |   | - Report draft   |
          +----------------+   +--------------+   +------------------+
```

## 책임 분리

### Android Client

- Codec capability discovery
- Backend에서 trial parameter 수신
- `MediaCodec` configuration
- Encoding trial 수행
- Requested/applied parameter 기록
- Encoded artifact 업로드

Android Client는 VMAF 측정이나 optimizer 실행을 담당하지 않는다.

### Backend API

- Session 생성과 상태 관리
- Trial lifecycle 관리
- Artifact 수신
- Bitrate/VMAF 측정 실행
- Observation 저장
- Optimizer 호출
- RAG Agent 호출
- 최종 리포트 생성

Backend API는 Android Client가 알 필요 없는 optimizer state, RAG output, evaluation detail을 숨기고 trial assignment와 upload 계약만 노출한다.

### Constraint Filter

- Capability discovery 결과를 기반으로 search space를 만든다.
- ADR에서 제한한 MVP parameter 범위를 강제한다.
- RAG Agent가 만든 constraint 후보를 검증한다.
- Accepted/rejected decision을 audit log로 남긴다.

Constraint Filter는 RAG Agent보다 우선권을 갖고, Optimizer보다 앞단에서 후보 parameter domain을 제한한다.

### Optimizer

- Search space를 입력으로 받는다.
- Observation을 바탕으로 다음 parameter set을 추천한다.
- 이미 평가한 parameter 조합을 반복 추천하지 않는다.
- Pareto Set과 Pareto Front 계산에 필요한 데이터를 제공한다.

MVP에서는 Optuna NSGA-II 또는 동등한 multi-objective optimizer를 우선한다.

### RAG Agent

- Android CDD, `MediaCodec`, `MediaFormat`, vendor codec 문서, 과거 benchmark/trial 기록을 검색한다.
- Search space constraint 후보를 생성한다.
- 실패 trial에 대한 원인 후보를 생성한다.
- 최종 리포트를 설명 가능한 형태로 작성한다.

RAG Agent는 최종 parameter selection 권한을 갖지 않는다.

## 주요 흐름

### Session 시작

```text
User -> Backend: create session
Android Client -> Backend: register device and codec capability
Backend -> RAG Agent: collect optional constraint candidates
Backend -> Constraint Filter: build search space
Backend -> Optimizer: initialize study
```

### Trial 실행

```text
Backend -> Optimizer: ask next parameter
Optimizer -> Backend: recommended parameter
Backend -> Constraint Filter: validate recommendation
Backend -> Android Client: trial assignment
Android Client -> MediaCodec: configure and encode
Android Client -> Backend: upload artifact and applied metadata
Backend -> Evaluator: measure bitrate and VMAF
Backend -> Optimizer: add observation
```

### Constraint 보정

```text
Backend -> RAG Agent: ask constraint candidates
RAG Agent -> Backend: candidate constraints with sources
Backend -> Constraint Filter: validate candidates against capability and rules
Constraint Filter -> Backend: accepted/rejected constraints
Backend -> Optimizer: update search space when valid
```

### Session 종료

```text
Backend -> Optimizer: calculate Pareto result
Backend -> RAG Agent: summarize results
Backend -> User: final report
```

## 장애 처리 원칙

- `configure()` 실패 시 해당 parameter 조합은 failed trial로 기록한다.
- Artifact upload 실패 시 trial은 retry 가능한 상태로 둔다.
- VMAF 측정 실패 시 encoded artifact와 ffmpeg 로그를 보존한다.
- Requested/applied parameter 불일치는 실패가 아니라 observation metadata로 기록한다.
- RAG Agent 실패는 optimizer loop를 중단시키지 않는다.

## 상태 전이

### Session 상태

```text
created -> ready -> running -> completed
                  \-> failed
```

- `created`: session은 생성됐지만 capability가 등록되지 않았다.
- `ready`: capability와 search space가 준비됐다.
- `running`: 하나 이상의 trial이 assigned 또는 evaluated 상태다.
- `completed`: 종료 조건을 만족하고 report가 생성됐다.
- `failed`: 입력 영상, capability, artifact storage 등 session 핵심 전제가 깨졌다.

### Trial 상태

```text
pending -> assigned -> uploaded -> evaluated
          \           \-> failed
           \-> failed
```

- `pending`: backend가 trial을 생성했지만 client에 할당하지 않았다.
- `assigned`: Android client가 수행할 trial로 내려갔다.
- `uploaded`: encoded artifact와 applied metadata가 backend에 도착했다.
- `evaluated`: bitrate와 VMAF observation이 생성됐다.
- `failed`: configure, encoding, upload, evaluation 중 복구 불가능한 실패가 기록됐다.

## 경계 조건

- Backend는 Android client가 보낸 `artifact_path`만 신뢰하지 않고 업로드된 파일 존재 여부를 확인한다.
- Android client는 backend의 requested parameter를 그대로 기록하고, 실제 적용 확인이 불가능한 값은 `applied_params_unknown`에 남긴다.
- Optimizer recommendation은 trial assignment 전 Constraint Filter를 다시 통과한다.
- Session 종료 전 report는 생성할 수 있지만, `completed` 상태로 바꾸려면 최소 trial count와 baseline 비교 조건을 만족해야 한다.
