# 05. Algorithm and RAG Design

## Optimization objective

MVP의 목적 함수는 다음 두 개이며, optimizer는 이 trade-off에서 Pareto-optimal parameter 후보를 찾는다.

- VMAF maximize
- Bitrate minimize

각 trial observation은 `(parameter, bitrate, vmaf)` 형태로 optimizer에 전달된다.

Optimizer는 objective 계산만 담당하며, Android capability 해석이나 RAG 문서 해석을 직접 수행하지 않는다.

## Search space

### 기본 search space

| Parameter | Type | 예시 범위 | 비고 |
| --- | --- | --- | --- |
| `bitrate_kbps` | integer | 1000-12000 | 입력 영상과 해상도에 맞춰 조정 |
| `i_frame_interval_sec` | integer/float | 1-5 | GOP 제어 |
| `profile` | categorical | baseline, main, high | capability에 따라 제외 가능 |

Search space는 version을 가진다. Trial은 생성 시점의 `search_space_version`을 저장해 나중에 constraint 변경이 있어도 당시 조건을 재현할 수 있게 한다.

### 확장 search space

| Parameter | 포함 조건 |
| --- | --- |
| `b_frame_count` | 기기 지원 확인 |
| `bitrate_mode` | codec capability 확인 |
| QP parameter | public API 또는 vendor key 지원 확인 |
| vendor extension key | allowlist와 적용 검증 통과 |

## Trial selection

### Cold start

초기 5회는 search space를 넓게 관측하기 위해 random, Sobol, Latin Hypercube 중 하나를 사용한다.

성공 기준:

- 동일 parameter 조합을 반복하지 않는다.
- Search space의 주요 범위를 포함한다.
- 실패 trial도 observation metadata로 보존한다.

### Multi-objective optimization

Cold start 이후에는 Optuna NSGA-II 또는 동등한 multi-objective optimizer를 사용한다.

추천 parameter는 다음 조건을 만족해야 한다.

- Structured constraint filter를 통과한다.
- 이미 평가한 조합이 아니다.
- Capability에 없는 parameter를 포함하지 않는다.
- Vendor extension key는 allowlist에 포함되어야 한다.

### Optimizer 입출력 계약

Input:

```json
{
  "session_id": "sess_001",
  "search_space_version": "space_001",
  "search_space": {
    "bitrate_kbps": {"type": "int", "low": 1000, "high": 12000},
    "i_frame_interval_sec": {"type": "float", "low": 1, "high": 5},
    "profile": {"type": "categorical", "choices": ["baseline", "main"]}
  },
  "observations": [
    {
      "params": {"bitrate_kbps": 4000, "i_frame_interval_sec": 2, "profile": "baseline"},
      "bitrate_kbps": 4100,
      "vmaf": 91.2
    }
  ],
  "failed_params": []
}
```

Output:

```json
{
  "optimizer_trial_id": "opt_006",
  "recommended_params": {
    "bitrate_kbps": 3500,
    "i_frame_interval_sec": 2,
    "profile": "main"
  },
  "metadata": {
    "phase": "mobo",
    "seed": 42
  }
}
```

Backend는 optimizer output을 바로 Android client에 전달하지 않고 Constraint Filter로 재검증한다.

## Pareto 계산

Trial A가 Trial B보다 다음 조건에서 우월하면 B는 Pareto Set에서 제외된다.

- A의 VMAF가 B 이상이다.
- A의 bitrate가 B 이하이다.
- 둘 중 하나는 엄격하게 더 좋다.

최종 리포트는 Pareto Set과 VMAF-bitrate plot 데이터를 포함해야 한다.

Failed trial은 Pareto 계산에서 제외하되, 실패율과 실패 parameter는 report에 포함한다.

## Baseline 비교

Baseline은 다음 우선순위로 선택한다.

1. Android 기본 encoder 설정
2. 사전에 지정한 기준 preset
3. Cold start trial 중 대표 parameter

비교 지표는 BD-Rate를 우선한다. BD-Rate 계산이 어렵거나 데이터 포인트가 부족하면 VMAF-bitrate table과 plot 비교를 사용한다.

BD-Rate는 충분한 rate-quality point가 있을 때만 사용한다. MVP에서 point 수가 부족하면 baseline 대비 동일 또는 유사 VMAF 구간의 bitrate 차이를 보조 지표로 사용한다.

## Constraint filter

Constraint filter는 optimizer와 RAG Agent 사이의 안전 장치다.

입력:

- ADR rule
- Capability data
- RAG constraint candidate
- Trial failure observation

출력:

- Accepted parameter domain
- Rejected parameter와 사유
- Audit log

처리 규칙:

1. ADR에서 MVP 제외로 정한 parameter는 기본 제외한다.
2. Capability에서 지원되지 않는 parameter는 제외한다.
3. `profile`은 capability에 포함된 값만 허용한다.
4. Vendor extension key는 allowlist에 포함된 경우만 허용한다.
5. RAG Agent의 constraint 후보는 문서 출처 또는 observation 근거가 있어야 한다.
6. RAG Agent의 자연어 설명만으로 search space를 확장하지 않는다.

### Constraint decision lifecycle

```text
candidate -> validated -> accepted/rejected -> search_space_version updated
```

- `candidate`: RAG, capability, observation에서 constraint 후보가 생성됐다.
- `validated`: ConstraintFilter가 schema와 source를 확인했다.
- `accepted`: search space에 반영한다.
- `rejected`: audit log에는 남기지만 optimizer domain에는 반영하지 않는다.

Search space가 바뀌면 새 version을 만들고, 기존 trial의 version은 변경하지 않는다.

## RAG Agent 설계

### Knowledge source

MVP corpus는 제한적으로 시작한다.

- Android CDD
- Android `MediaCodec` 문서
- Android `MediaFormat` 문서
- Vendor codec 문서
- 과거 benchmark 결과
- 현재 session trial log

각 source는 retrieval 결과에 source id, 문서명, 섹션 또는 observation id를 포함해야 한다.

### RAG 출력 유형

#### Constraint candidate

```json
{
  "parameter_name": "b_frame_count",
  "candidate_decision": "rejected",
  "reason": "Capability discovery did not confirm B-frame support.",
  "sources": ["capability:sess_001"]
}
```

Constraint candidate는 `accepted`를 직접 만들 수 없다. `candidate_decision`은 RAG Agent의 의견이며, 실제 결정은 ConstraintFilter가 `ConstraintDecision`으로 저장한다.

#### Failure analysis

```json
{
  "trial_id": "trial_010",
  "failure_type": "CONFIGURE_FAILED",
  "candidate_causes": [
    "Requested profile may be unsupported by selected codec.",
    "Requested bitrate mode may not match codec capability."
  ],
  "sources": ["trial_log:trial_010"]
}
```

#### Final report section

RAG Agent는 최종 리포트의 설명 초안을 생성한다. Backend는 raw metrics, Pareto Set, constraint decision log를 함께 첨부한다.

## LLM 사용 제한

- LLM은 최종 parameter를 직접 결정하지 않는다.
- LLM 출력은 사람이 읽는 설명과 constraint 후보로 제한한다.
- Search space 변경은 structured constraint filter가 결정한다.
- 모든 RAG 출력은 source reference를 남긴다.

## Session 종료 조건

Session은 다음 조건을 만족하면 종료할 수 있다.

- Evaluated trial이 최소 15개다.
- Baseline observation이 선택되어 있다.
- Pareto Set 계산이 완료됐다.
- Report 생성에 필요한 raw metric과 constraint decision log가 존재한다.

다음 조건에서는 조기 종료할 수 있다.

- 연속된 configure 실패로 search space가 비어 있다.
- VMAF evaluation이 반복 실패해 objective를 계산할 수 없다.
- Android client가 더 이상 trial을 수행할 수 없다.

조기 종료도 실패 session report를 생성해 원인과 남은 gap을 기록한다.
