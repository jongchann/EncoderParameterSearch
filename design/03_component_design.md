# 03. Component Design

## Android Client

### EncoderParameterProxy

`EncoderParameterProxy`는 backend가 전달한 parameter를 Android `MediaFormat` 설정으로 변환한다.

책임:

- Parameter schema 검증
- `MediaFormat` key mapping
- `MediaCodec.configure()` 호출 전 설정 준비
- Requested parameter 기록

설계 의도:

- Backend parameter schema와 Android framework API 결합도를 낮춘다.
- 향후 codec별 mapping 차이를 분리하기 쉽다.

### VendorExtensionStrategy

Vendor-specific extension key 처리를 담당한다.

초기 MVP에서는 allowlist 기반으로 동작하며, 지원 확인이 되지 않은 key는 적용하지 않는다.

전략 후보:

- `QualcommExtensionStrategy`
- `ExynosExtensionStrategy`
- `MediaTekExtensionStrategy`
- `NoOpExtensionStrategy`

1차 MVP에서는 `NoOpExtensionStrategy` 또는 단일 vendor strategy만 구현해도 충분하다.

### CapabilityReporter

Codec capability discovery 결과를 backend에 전달한다.

수집 항목:

- Device model
- Android version
- Codec name
- MIME type
- Supported profiles
- Supported bitrate modes
- Resolution/framerate constraints
- B-frame 지원 여부 후보
- Vendor extension key 지원 후보

### TrialRunner

Backend에서 trial assignment를 받아 encoding을 수행한다.

책임:

- Trial parameter 수신
- EncoderParameterProxy 호출
- Encoding 실행
- Applied parameter metadata 수집
- Encoded artifact 업로드
- Trial result callback 전송

출력:

- `applied_params`
- `applied_params_unknown`
- `artifact_upload_ref`
- `encoder_log`
- `failure`, 실패 시

## Backend

### SessionService

Session lifecycle을 관리한다.

상태:

- `created`
- `ready`
- `running`
- `completed`
- `failed`

책임:

- Session 종료 조건 확인
- Baseline trial 선택 여부 확인
- Report 생성 요청

### TrialService

Trial lifecycle을 관리한다.

상태:

- `pending`
- `assigned`
- `uploaded`
- `evaluated`
- `failed`

책임:

- Trial assignment 생성
- Trial 상태 전이 검증
- Android client result 수신
- Failed trial 기록

### ConstraintFilter

Search space에 반영 가능한 parameter와 constraint를 결정한다.

입력:

- ADR 기반 기본 rule
- Capability discovery 결과
- RAG Agent constraint 후보
- Trial failure observation

출력:

- Accepted search space
- Rejected parameter와 사유
- Optimizer에 전달할 parameter domain

검증 원칙:

- Capability에 없는 parameter는 제외한다.
- Allowlist에 없는 vendor key는 제외한다.
- RAG Agent가 출처 없이 제안한 constraint는 제외한다.
- 실패 observation만으로 일반 rule을 만들지 않는다.
- Optimizer 추천값도 Android client로 내려가기 전에 다시 검증한다.

### SearchSpaceBuilder

ADR rule, capability, constraint decision을 조합해 optimizer용 parameter domain을 만든다.

책임:

- `bitrate_kbps` 범위 결정
- `i_frame_interval_sec` 범위 결정
- `profile` categorical 후보 결정
- Search space version 생성
- Accepted/rejected parameter 목록 저장

`SearchSpaceBuilder`는 domain 생성 담당이고, `ConstraintFilter`는 후보와 변경 요청 검증 담당이다.

### EvaluationService

Encoded artifact의 bitrate와 VMAF를 측정한다.

책임:

- Artifact path 확인
- Bitrate 계산
- `ffmpeg`/`libvmaf` 실행
- 측정 로그 저장
- Observation 생성

### OptimizerService

다음 trial parameter를 추천한다.

MVP 동작:

- Cold start 5회 수행
- 이후 multi-objective optimizer로 추천
- Objective는 VMAF maximize, bitrate minimize
- 이미 평가한 조합은 제외

입력:

- Search space version
- Evaluated observation 목록
- Failed trial 목록
- Baseline observation

출력:

- Optimizer trial id
- Recommended parameter
- Recommendation metadata

### RagAgentService

문서와 observation 기반 설명을 생성한다.

책임:

- Constraint 후보 생성
- Unsupported parameter 제외 사유 설명
- Trial failure 원인 후보 설명
- 최종 리포트 초안 생성

출력은 JSON schema를 우선 사용하고, 사람이 읽는 설명은 report 생성 단계에서 Markdown으로 변환한다.

## 저장소 컴포넌트

### MetadataStore

SQLite 또는 동등한 경량 DB를 사용한다.

저장 대상:

- Session
- Device
- Capability
- Trial
- Observation
- Constraint decision
- RAG output
- Report metadata

추가 저장 대상:

- Search space version
- Optimizer recommendation history
- Baseline selection

### ArtifactStore

초기 MVP에서는 로컬 파일 시스템을 사용한다.

저장 대상:

- Encoded bitstream
- Evaluation log
- RAG source snapshot
- Final report

ArtifactStore는 파일 저장만 담당하고, 파일과 session/trial의 연결은 MetadataStore가 담당한다.
