# 04. Data and API Design

## 데이터 모델

### Session

| 필드 | 설명 |
| --- | --- |
| `session_id` | Session 식별자 |
| `input_video_id` | 기준 입력 영상 식별자 |
| `target_codec` | 대상 codec |
| `target_mime` | 예: `video/avc` |
| `status` | Session 상태 |
| `search_space_version` | 현재 search space version |
| `baseline_trial_id` | Baseline으로 선택된 trial |
| `created_at` | 생성 시각 |
| `completed_at` | 종료 시각 |

### Device

| 필드 | 설명 |
| --- | --- |
| `device_id` | Device 식별자 |
| `model` | 기기 모델명 |
| `android_version` | Android version |
| `soc_vendor` | Qualcomm, Exynos, MediaTek 등 |

### Capability

| 필드 | 설명 |
| --- | --- |
| `capability_id` | Capability 식별자 |
| `device_id` | Device 식별자 |
| `codec_name` | Codec name |
| `mime_type` | MIME type |
| `profiles` | 지원 profile 목록 |
| `bitrate_modes` | 지원 bitrate mode 목록 |
| `supports_b_frame` | B-frame 지원 여부 후보 |
| `vendor_keys` | 지원 후보 vendor key 목록 |
| `raw_payload` | 원본 capability payload |

### Trial

| 필드 | 설명 |
| --- | --- |
| `trial_id` | Trial 식별자 |
| `session_id` | Session 식별자 |
| `index` | Trial 순번 |
| `status` | Trial 상태 |
| `requested_params` | Backend가 요청한 parameter |
| `applied_params` | Android가 실제 적용했다고 기록한 parameter |
| `applied_params_unknown` | 적용 여부를 확인하지 못한 parameter |
| `artifact_path` | Encoded artifact path |
| `optimizer_trial_id` | Optimizer 내부 trial 식별자 |
| `search_space_version` | Trial 생성에 사용한 search space version |
| `error_code` | 실패 코드 |
| `error_message` | 실패 메시지 |

### Observation

| 필드 | 설명 |
| --- | --- |
| `observation_id` | Observation 식별자 |
| `trial_id` | Trial 식별자 |
| `bitrate_kbps` | 측정 bitrate |
| `vmaf` | 측정 VMAF |
| `evaluation_log_path` | 평가 로그 path |
| `is_baseline` | Baseline observation 여부 |
| `created_at` | 생성 시각 |

### ConstraintDecision

| 필드 | 설명 |
| --- | --- |
| `decision_id` | Constraint decision 식별자 |
| `session_id` | Session 식별자 |
| `parameter_name` | 대상 parameter |
| `decision` | `accepted` 또는 `rejected` |
| `reason` | 결정 사유 |
| `source_type` | `capability`, `adr_rule`, `rag`, `observation` |
| `source_ref` | 출처 참조 |

### SearchSpace

| 필드 | 설명 |
| --- | --- |
| `search_space_version` | Search space version |
| `session_id` | Session 식별자 |
| `parameters` | Optimizer에 전달되는 parameter domain |
| `created_from` | `adr_rule`, `capability`, `rag`, `observation` 목록 |
| `created_at` | 생성 시각 |

### OptimizerRecommendation

| 필드 | 설명 |
| --- | --- |
| `optimizer_trial_id` | Optimizer 내부 trial 식별자 |
| `session_id` | Session 식별자 |
| `trial_id` | 연결된 backend trial |
| `search_space_version` | 추천에 사용된 search space version |
| `recommended_params` | 추천 parameter |
| `status` | `accepted`, `rejected`, `evaluated`, `failed` |
| `metadata` | optimizer score, seed, generation 등 |

## Parameter schema

### 1차 MVP parameter

```json
{
  "bitrate_kbps": 4000,
  "i_frame_interval_sec": 2,
  "profile": "baseline"
}
```

### 확장 parameter

```json
{
  "b_frame_count": 1,
  "bitrate_mode": "vbr",
  "qp_min": 18,
  "qp_max": 42,
  "vendor_extensions": {
    "example.key": "value"
  }
}
```

확장 parameter는 capability와 allowlist 검증을 통과한 경우에만 search space에 포함한다.

## API 설계

### Create session

```http
POST /sessions
```

Request:

```json
{
  "input_video_id": "sample_001",
  "target_mime": "video/avc",
  "target_codec": "auto"
}
```

Response:

```json
{
  "session_id": "sess_001",
  "status": "created"
}
```

### Register capability

```http
POST /sessions/{session_id}/capabilities
```

Request:

```json
{
  "device": {
    "model": "android-device",
    "android_version": "14",
    "soc_vendor": "unknown"
  },
  "codec": {
    "codec_name": "OMX.example.avc.encoder",
    "mime_type": "video/avc",
    "profiles": ["baseline", "main"],
    "bitrate_modes": ["cbr", "vbr"],
    "supports_b_frame": false,
    "vendor_keys": []
  },
  "raw_payload": {}
}
```

### Get next trial

```http
GET /sessions/{session_id}/trials/next
```

Response:

```json
{
  "trial_id": "trial_001",
  "requested_params": {
    "bitrate_kbps": 4000,
    "i_frame_interval_sec": 2,
    "profile": "baseline"
  }
}
```

### Upload trial result

```http
POST /sessions/{session_id}/trials/{trial_id}/result
```

Request metadata:

```json
{
  "applied_params": {
    "bitrate_kbps": 4000,
    "i_frame_interval_sec": 2,
    "profile": "baseline"
  },
  "applied_params_unknown": [],
  "artifact_upload_ref": "upload_001",
  "encoder_log": {}
}
```

Artifact binary는 같은 endpoint의 multipart body로 전송하거나, backend가 발급한 upload URL에 먼저 업로드한 뒤 `artifact_upload_ref`로 연결한다. MVP에서는 multipart upload를 기본으로 한다.

### Mark trial failure

```http
POST /sessions/{session_id}/trials/{trial_id}/failure
```

Request:

```json
{
  "error_code": "CONFIGURE_FAILED",
  "error_message": "MediaCodec configure failed",
  "requested_params": {}
}
```

### Get report

```http
GET /sessions/{session_id}/report
```

Response:

```json
{
  "session_id": "sess_001",
  "pareto_set": [],
  "baseline_comparison": {},
  "report_path": "artifacts/sess_001/report.md"
}
```

### Get session status

```http
GET /sessions/{session_id}
```

Response:

```json
{
  "session_id": "sess_001",
  "status": "running",
  "trial_count": 12,
  "evaluated_trial_count": 10,
  "failed_trial_count": 2,
  "search_space_version": "space_003"
}
```

### Get constraint decisions

```http
GET /sessions/{session_id}/constraints
```

Response:

```json
{
  "session_id": "sess_001",
  "decisions": [
    {
      "parameter_name": "b_frame_count",
      "decision": "rejected",
      "reason": "Capability discovery did not confirm support.",
      "source_type": "capability",
      "source_ref": "capability:sess_001"
    }
  ]
}
```

## Artifact layout

```text
artifacts/
  {session_id}/
    input/
    trials/
      {trial_id}/
        output.h264
        encoder_log.json
        evaluation_log.json
        requested_params.json
        applied_params.json
    rag/
      constraint_sources.json
      report_sources.json
    optimizer/
      recommendations.json
    report.md
```
