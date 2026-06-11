# 00. Design Overview

## 목적

Encoder Parameter Search MVP는 Android hardware encoder의 parameter를 자동 탐색해, 제한된 search space 안에서 bitrate 대비 지각 화질(VMAF)이 개선된 Pareto-optimal parameter 후보를 찾는 closed-loop system이다.

이 설계 문서는 ADR에서 확정한 방향을 구현 가능한 단계별 산출물로 구체화한다.

## 설계 범위

MVP는 다음 범위에 집중한다.

- Android `MediaCodec` 기반 H.264/AVC encoding trial 실행
- Backend 기반 artifact 수신, bitrate/VMAF 측정, observation 저장
- 제한된 parameter search space 기반 multi-objective optimization
- RAG Agent를 통한 문서 기반 constraint 후보 생성과 결과 리포트 보조
- 최소 15회 trial 기반 Pareto Front, 개선 parameter 후보, baseline 비교 리포트 생성

MVP의 성공은 모든 기기와 모든 parameter 조합에 대한 전역 최적해를 보장하는 것이 아니라, 제한된 search space 안에서 baseline 대비 개선된 parameter 후보를 찾고 다음을 함께 증명하는 데 있다.

- Android hardware encoder를 포함한 closed-loop가 끝까지 반복 실행된다.
- 각 trial의 입력, 출력, 평가 결과, 결정 근거가 재현 가능하게 남는다.
- Optimizer와 RAG Agent의 책임이 분리되어 수치 결정과 설명 생성이 섞이지 않는다.

MVP에서 제외하는 범위는 다음과 같다.

- Android 단말 내 VMAF 측정
- LLM 단독 parameter 결정
- fine-tuning
- 모든 vendor extension key의 자동 탐색
- 다중 기기 병렬 실험 운영

## 설계 평가 관점

이 프로젝트는 단순히 encoder parameter를 몇 개 바꿔보는 도구가 아니라, AI가 포함된 실험 시스템을 어떻게 안전하게 설계하는지 보여주는 것을 목표로 한다.

따라서 설계 완성도는 다음 질문에 답할 수 있어야 한다.

- Android hardware encoder를 실제 실험 루프에 포함하면서도 무거운 평가와 AI 처리를 backend로 분리했는가
- Optimizer, Constraint Filter, RAG Agent의 책임과 권한이 섞이지 않는가
- LLM/RAG 출력이 source reference와 structured validation 없이 search space에 반영되지 않는가
- 최종 parameter 후보가 어떤 trial, observation, constraint decision을 거쳐 선택됐는지 역추적할 수 있는가
- AI guardrails가 RAG output, optimizer recommendation, report narrative에 각각 적용되는가
- AI-Ops 관점에서 prompt/source/search space/evaluator/report version이 남는가
- MVP 범위를 현실적으로 제한하면서도 H.265, QP, vendor extension key, 다중 기기로 확장 가능한가
- 현재 구현된 기능과 목표 설계가 문서에서 구분되는가

## 핵심 설계 결정

ADR 001, ADR 002에 따라 다음 결정을 따른다.

- Android Client는 인코딩 실행과 capability discovery를 담당한다.
- Backend는 평가, 최적화, session 상태, artifact 저장, 리포트 생성을 담당한다.
- Optimizer는 bitrate와 VMAF observation을 바탕으로 다음 trial parameter와 최종 Pareto-optimal 후보를 결정한다.
- RAG Agent는 문서 검색, constraint 후보 생성, 실패 원인 후보 제안, 리포트 생성을 보조한다.
- RAG Agent 출력은 structured constraint filter를 통과해야 search space에 반영된다.
- AI guardrails는 source validation, schema validation, ConstraintFilter 재검증, report trust level로 구성한다.
- AI-Ops는 별도 플랫폼보다 session-level telemetry와 versioned artifact로 경량 적용한다.
- 1차 MVP 탐색 변수는 `bitrate`, `i_frame_interval`, `profile`로 제한한다.
- `b_frame_count`, `bitrate_mode`, QP, vendor extension key는 지원 확인 후 확장한다.

## 현재 구현 성숙도

설계 문서는 target architecture를 설명하고, 구현 진행 문서는 실제 완료 상태를 추적한다. 현재 기준의 구분은 다음과 같다.

| 영역 | 현재 상태 | 목표 상태 |
| --- | --- | --- |
| Backend lifecycle | Session, capability, trial, upload, report API 구현 | 실제 Android closed-loop 15회 완료 |
| Optimizer | Deterministic cold-start recommendation 구현 | NSGA-II 또는 동등한 multi-objective optimizer 추가 |
| Evaluation | Mock evaluator와 real evaluator 실행 경계 구현 | `ffmpeg`/`libvmaf` VMAF parsing 완료 |
| Android client | Manual smoke-test app과 mock mode 시작 | Real device artifact upload 검증 |
| RAG Agent | 설계 계약만 정의 | Source-backed constraint candidate와 report draft 구현 |
| Report | Metric, Pareto, baseline, audit trail 중심 | RAG narrative와 source reference까지 포함 |
| AI guardrails/Ops | Source validation과 audit trail 설계 반영 | Guardrail tests, telemetry, rollback 기준 구현 |

## 문서 구조

설계 문서는 다음 흐름으로 읽는다.

1. 요구사항 정의
2. 시스템 아키텍처 정의
3. 컴포넌트 설계
4. 데이터/API 설계
5. 알고리즘/RAG 설계
6. 검증 계획
7. 리스크와 로드맵
8. 구현 계획과 진행 상태
9. 전체 설계 리뷰와 발전 방향
10. AI guardrails와 AI-Ops 적용 범위

## 산출물 완료 기준

설계 단계는 다음 조건을 만족하면 완료된 것으로 본다.

- 요구사항이 MVP 성공 기준과 연결되어 있다.
- 시스템 컴포넌트별 책임과 경계가 명확하다.
- Trial lifecycle과 실패 처리가 문서화되어 있다.
- API와 데이터 모델이 requested/applied parameter, observation, artifact를 분리해서 표현한다.
- Optimizer와 RAG Agent의 입출력 계약이 정의되어 있다.
- 검증 계획이 단위, 통합, 실험, 리포트 검증을 포함한다.
