# 엔지니어링 복구 및 검증 — 2026-10-11

## 결과 범위

로컬 구현의 잘못된 성공 상태와 제한된 파일 접근 경계를 수정했다. 합성 자료 기반 구성요소 검증과 실제 로컬 추론·벡터 검색을 수행했다. 운영 컨테이너에는 배포하지 않았으며, 최종 교육용 PDF가 완성됐다고 주장하지 않는다.

## 확인한 결함 → 변경 → 검증

| 결함 | 변경 | 확인 |
| --- | --- | --- |
| Service가 실제 Worker 대신 상담·출결 모의 완료를 반환 | 모듈 경로로 등록 가능한 Worker 진입점으로 연결 | 임시 Redis/RQ에서 실제 실행과 실패 레지스트리 확인. 해당 검사의 모델은 stub |
| 모델 부재·오류를 완료 결과로 저장 | 실패 반환, 완료 파일 생성 금지, 큐 작업에서 예외 전파 | 실패·빈 응답·정상 응답 회귀 |
| 단순 라우팅만 하고 success 반환 | 실행 미연결은 not_implemented로 표시 | 합성 라우팅 회귀 |
| 모델 ID 불일치 시 임의 다른 모델 선택 | 명시 모델의 부재·모호성 거부 | 모델 선택 회귀 및 실제 로컬 호출 |
| 주소 정규식의 문자집합 오용과 부분 마스킹 | 행정구역·도로/지번 범위 수정 | 독립 정답 span 17개 및 비민감 대조군 |
| 감사 도구의 숨김 상태·drive-relative·ADS·junction 경계 | 제한 경로와 재분석 지점 차단, 잘라내기 전 마스킹 | 합성 임시 폴더·경로 회귀. 모든 OS 공격 경로 검증은 아님 |
| 잘못된 JSON 한 줄로 브리지 종료 | 제한된 오류 반환 후 다음 요청 처리 | 실제 stdio 프로세스 연속 요청 |
| cwd/timeout만으로 임의 Python을 sandbox라 표기 | 검증된 격리가 연결될 때까지 코드 실행 차단 | 실행 금지 회귀. 파일 읽기/쓰기는 기존 허용 루트 안으로 제한 |
| 기존 MCP 검사가 폐기된 wrapper API 및 동일 queue mock 사용 | 실제 SDK 도구 목록·독립 mock·실제 async submit 검사 | 두 묶음 19건 재검증 통과; 최초 실패 기록 보존 |
| 게시 스크립트의 staged diff 검사 실패 | 선별 샘플 끝 공백 제거, AST 동일성 및 해시 재검증 | 검사 우회 없이 게시 gate 재실행 |

중복 `_job_instruction`의 가려진 옛 구현은 legacy 이름으로 보존했다. 현재 활성 프롬프트 동작을 바꾸거나 사용하지 않던 기능을 자동 활성화하지 않았다.

## 실제 호출 경로

```text
LM Studio Harness Control tools
  → TypeScript bridge → Python monitor_bridge
  → Academy submit/status/artifacts 또는 읽기 전용 audit tools
  → Redis/RQ → 기존 Academy workflow
  → IP Fabric canonical → Nomic embeddings → derived SQLite vector index
  → Qwen generation → content validation → rendering / vision QA
```

이번 Academy 검증은 content validation에서 중단됐다. 다이어그램·vision QA·최종 문서 단계까지 통과한 경로로 표시하지 않는다. 별도 Service 상담 경로는 마스킹 → RQ 모듈 진입점 → Worker → 로컬 모델 → 결과 저장 구조이며, 실계정 Discord 송수신은 실행하지 않았다.

## 실제 결과

- Python 78 PASS / 1 SKIP, TypeScript build PASS / tests 4 PASS.
- 실제 Nomic 임베딩은 768차원. 새 임시 canonical 및 derived index로 검색·증분 생략·재구축 검증.
- 출력 길이를 제한한 Docker Qwen smoke PASS. 앞선 호스트 텍스트 호출의 90초 timeout은 별도 실패 증거로 유지.
- Academy 합성 E2E 1회: 실제 검색 및 생성 후 DNA 양 검증에서 BLOCKED. 기존 내장 수정 시도도 통과하지 못했다.
- 차단 메시지: X 모양만으로 세포 DNA 2C 단정, 2n=4 fixture와 복제 전후 1C→2C 관계 충돌. 판정 규칙의 일반 정확도까지 보증하는 결과는 아니다.
- 검증 환경은 read-only 소스 mount와 독립 writable state/output을 사용했다. 기존 운영 DB와 복구 사본은 수정하지 않았다.

## 남은 문제와 우선순위

1. 운영 Main은 이전 이미지의 `load_dotenv` 누락으로 재시작 중이다. 호스트 소스는 수정되어 있지만 이미지 반영은 이번에 수행하지 않았다. 서비스·Worker 배포 정합성을 별도 확인해야 한다.
2. 교육용 생성 결과와 validator 판단을 독립 과학 근거로 대조하고, 실패 사례를 해결한 뒤 실제 PDF/vision QA를 다시 검증해야 한다. 공식 교육과정 적합성은 미검증이다.
3. PII 탐지의 일반화, 클라우드 반출, hostile filesystem 경쟁 조건, 실제 사용자 효용은 미검증이다. 코드 실행 차단은 완성된 OS sandbox의 대체 구현이 아니다.
4. GUI 재설치와 운영 서비스 전체 통합은 이번 검증 범위가 아니다. 일반 업무 라우터의 미연결 업무는 미구현 상태를 정직하게 반환한다.

검증 명령 및 결과: [JSON 기록](evidence/recovery_validation_20261011.json). 소스 대응: [SHA-256 manifest](evidence/selection_manifest.json).
