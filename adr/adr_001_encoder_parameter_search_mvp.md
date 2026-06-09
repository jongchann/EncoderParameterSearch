# ADR 001: Encoder Parameter Search MVP Architecture

## Status
Accepted

## Context
Encoder Parameter Search 프로젝트는 Android 단말의 encoder parameter를 자동 탐색해 bitrate 대비 지각 화질(VMAF)을 최적화하는 것을 목표로 한다.

Android 단말에서 VMAF 측정, AI 추론, 반복 탐색까지 모두 수행하면 발열, 스로틀링, 메모리, 배터리 제약이 커진다. 반면 단말은 실제 하드웨어 encoder 동작을 검증해야 하므로 완전히 서버 시뮬레이션으로 대체할 수 없다.

프로젝트는 1인 3개월 MVP를 전제로 하며, 초기 목표는 모든 기능을 완성하는 것이 아니라 제한된 파라미터 공간에서 closed-loop 탐색이 실제로 동작함을 증명하는 것이다.

AI 모델이 포함된 과제 설계 능력을 보여주기 위해 LLM을 사용할 수 있다. 다만 LLM이 수치 최적화 자체를 직접 수행하게 하면 재현성과 안전성이 떨어질 수 있으므로, LLM의 역할과 optimizer의 역할을 분리해야 한다.

## Decision
분산형 closed-loop 구조를 채택한다.

- Android Client는 `MediaCodec` 기반 인코딩만 수행한다.
- Backend는 encoded stream을 수신해 bitrate와 VMAF를 측정하고, 다음 encoder parameter를 계산한다.
- 최적화 방식은 다중 목적 베이지안 최적화(MOBO)를 기본 방향으로 한다.
- 초기 5회는 random, Sobol, 또는 Latin Hypercube 계열의 cold start 탐색을 수행한다.
- 이후 10~15회는 VMAF 최대화와 bitrate 최소화를 동시에 고려해 Pareto Front를 확장하는 파라미터를 선택한다.
- 성과 지표는 VMAF 기반 Pareto Front와 BD-Rate를 우선 사용한다.

MVP의 AI 구성은 두 계층으로 분리한다.

- Optimizer는 수치 기반 parameter recommendation을 담당한다.
- LLM 기반 RAG Agent는 문서 검색, 제약 설명, trial 요약, 실패 원인 후보 제안, 최종 리포트 생성을 담당한다.

LLM은 encoder parameter를 직접 최종 결정하지 않는다. LLM이 제안하거나 설명한 내용은 structured constraint filter와 optimizer의 탐색 공간 정의를 통과해야 하며, 실제 다음 trial parameter는 optimizer가 선택한다.

MVP의 기본 탐색 변수는 다음으로 제한한다.

- Bitrate
- GOP 또는 iframe interval
- B-frame count, 단 기기 지원 시에만 사용
- Vendor extension key, 단 allowlist에 포함되고 기기 지원이 확인된 경우에만 사용

Android 쪽 encoder 제어는 Proxy Pattern을 사용해 `MediaCodec` 설정과 backend parameter 주입을 분리한다. Vendor별 extension key 처리는 Strategy Pattern으로 분리해 Qualcomm, Exynos, MediaTek 등 AP별 차이를 런타임에 교체할 수 있게 한다.

RAG는 MVP에 포함하되 최적화 보조 계층으로 제한한다. Android CDD, vendor codec 문서, MediaCodec 문서, 과거 benchmark 결과를 조회할 수 있는 knowledge provider를 두고, LLM은 이 검색 결과를 바탕으로 unsupported parameter 제거 근거와 결과 리포트를 생성한다. Fine-tuning은 MVP에서 제외하고, 충분한 benchmark 데이터가 축적된 뒤 별도 결정으로 다룬다.

## Consequences
이 결정으로 Android 단말은 실제 hardware encoder 특성을 반영하면서도 무거운 평가와 추론 작업에서 분리된다.

Backend는 평가, 최적화, artifact 저장, 결과 리포트 생성을 중앙에서 담당하므로 실험 재현성과 로그 관리가 쉬워진다. 또한 여러 Android 기기나 코덱으로 확장할 때도 동일한 최적화 루프를 재사용할 수 있다.

LLM 기반 RAG Agent를 별도 계층으로 두면 AI 모델이 포함된 과제라는 점을 명확히 보여주면서도, 수치 최적화의 재현성과 안전성을 유지할 수 있다. LLM은 문서와 로그 해석에 강점을 쓰고, optimizer는 정량 objective를 기반으로 다음 trial을 선택한다.

단점은 client-server 통신, artifact 업로드, session 상태 관리가 필요하다는 점이다. 또한 RAG Agent가 생성한 설명은 실제 parameter 적용 전에 structured constraint로 검증되어야 하며, hallucination 가능성을 고려해 문서 출처와 raw observation을 함께 남겨야 한다.

## Alternatives Considered
### Android 단독 실행
단말 하나에서 인코딩, VMAF 측정, 최적화를 모두 수행하는 방식이다. 구조는 단순하지만 발열과 성능 제약이 크고, VMAF 및 AI 추론 비용 때문에 반복 탐색 속도가 느려질 가능성이 높다.

### Backend 시뮬레이션 전용
서버에서 ffmpeg encoder만 사용해 파라미터를 탐색하는 방식이다. 개발은 빠르지만 Android hardware encoder의 vendor-specific behavior를 검증하지 못하므로 프로젝트 목표와 맞지 않는다.

### RAG/Fine-tuning 우선 구현
문서 검색과 과거 데이터 기반 prior를 먼저 만드는 방식이다. 장기적으로 유용하지만 3개월 MVP에서는 closed-loop 탐색 검증보다 우선순위가 낮다.

### LLM 직접 파라미터 추천
LLM이 다음 encoder parameter를 직접 추천하는 방식이다. AI 사용이 눈에 잘 띄지만 수치 최적화 문제에서 재현성과 성능 검증이 어렵다. 따라서 MVP에서는 LLM을 parameter 결정자가 아니라 constraint 해석과 리포트 생성자로 제한한다.

## Success Criteria
MVP는 다음 조건을 만족해야 한다.

- 하나의 Android 기기에서 하나의 코덱(H.264/AVC 우선)을 대상으로 인코딩 trial을 수행한다.
- 동일 입력 영상 기준 최소 15회 parameter search를 완료한다.
- 각 trial에 대해 parameter, bitrate, VMAF, artifact path, 실행 metadata를 기록한다.
- 최종 Pareto Set과 Pareto Front를 산출한다.
- baseline 대비 BD-Rate 또는 VMAF-bitrate 비교 결과를 생성한다.
- LLM 기반 RAG Agent가 unsupported parameter 제약 근거, trial 요약, 최종 Pareto 결과 리포트를 생성한다.
- 최종 적용 parameter가 LLM 단독 출력이 아니라 structured constraint filter와 optimizer를 거쳐 선택되었음을 로그로 확인할 수 있다.

## Assumptions
- 첫 MVP backend는 Python 기반으로 구현한다.
- VMAF 측정은 backend에서 `ffmpeg`와 `libvmaf`를 사용하는 것을 기본으로 한다.
- 세션 상태 저장은 초기에는 SQLite 또는 동등한 경량 로컬 저장소로 충분하다.
- 기준 preset이 없으면 초기 random/Sobol 탐색 결과 또는 Android 기본 encoder 설정을 baseline으로 사용한다.
- LLM은 backend의 보조 agent로 사용하며, API provider나 local model은 구현 시점에 선택한다.
- LLM 출력은 사람이 읽는 설명과 constraint 후보 생성에만 사용하고, 최종 trial parameter는 optimizer가 결정한다.
- Fine-tuning은 충분한 benchmark 데이터가 축적된 뒤 별도 ADR에서 다시 결정한다.
