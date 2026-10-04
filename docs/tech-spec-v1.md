# 기술 명세서 v1 — WikiPulse

- 기준: 2026-09-27 문서화, `develop` 커밋 `d082303`까지의 코드·설정
- 연결 문서: [요구사항](requirements-v1.md) · [API](api-v1.md) · [ERD](erd-v1.md)
- 운영 상태는 2026-09-22~23에 남은 검증 기록을 인용한다. 이 문서 작성 시점의 서버 재접속 결과는 아니다.

## 1. 구성과 책임

| 계층 | 기술·역할 | 기준 |
| --- | --- | --- |
| 프론트엔드 | React 19, Vite 8, 펄스맵·이슈·종목·계정 화면 | `frontend/package.json`, `frontend/src/app/RouteContent.jsx` |
| API | Java 17, Spring Boot 3.5.16, Spring Security·Session JDBC | `backend/build.gradle` |
| 데이터베이스 | PostgreSQL 17 + pgvector 0.8.6, 종목 임베딩 `vector(1536)` | `db/migrations/` |
| 스트림 | Wikimedia EventStreams → Kafka 3.9 → Spark 3.5.3 Structured Streaming | `data-pipeline/producer`, `streaming` |
| 배치·리플레이 | Wikimedia 시간별 조회수·historical edits → HDFS 3.5(2 DataNode, 복제 2) → Python/Spark 처리 | `data-pipeline/batch`, `spike`, `cluster` |
| AI·외부 근거 | GATEWAY 임베딩·LLM, GDELT GKG, MediaWiki historical revision, yfinance 주가 | `backend/matching`, `data-pipeline/stock` |
| 배포 | Docker Compose, Nginx HTTPS; GitHub Actions로 lint·테스트·빌드 검증 | `infra/service/compose.yaml`, `.github/workflows/ci.yml` |

일반 Python 파이프라인과 서비스 Spark 이미지는 3.11 계열로 구성한다. 추가 EC2의 공식 Spark 이미지 기반 edit-stream driver에는 Python 3.8.10이 남아 있다는 2026-09-22 실측 기록이 있다. `data-pipeline/Dockerfile`은 일반 파이프라인용 `python:3.11-slim`을 사용하고, Spark 운영 이미지는 `wikipulse-spark:py311` 계열이다. 운영에서 관측한 정확한 이미지 태그는 배포 기록을 따른다.

## 2. 배포와 데이터 흐름

기본 EC2(`service.example.com`)는 Nginx·React 정적 자산·Spring API·PostgreSQL과 HDFS/Spark worker를 맡는다. 추가 EC2(`data.example.com`)는 Kafka broker·Spark Master·HDFS NameNode와 HDFS/Spark worker를 맡는다. 2026-09-22 기록에는 HTTPS 루트와 snapshots·map·rankings·stocks API 응답 200, EventStreams producer 및 edit-stream 잡 기동이 확인돼 있다. 이후 상태는 이 기록만으로 판단하지 않는다.

편집 이벤트는 `enwiki` namespace 0의 비봇 변경을 Kafka `wiki.edits`로 전달한다. Spark는 편집 창을 집계하고, 시간별 `other/pageviews` 원본이 들어오면 조회수 관문을 판정한다. 도착 전 후보는 `spike_candidate`, 확정 결과는 `spike`에 둔다. `page_view_hourly_ingest`로 원본이 실제 들어왔는지 기록한다. 2026-09-23 기준 2개월 리플레이는 한 시간 오프셋 오류를 고치기 위해 재실행 중이었다. 운영 스냅샷의 교정 완료 여부는 별도 검증이 필요하다.

클러스터링 기본 경로는 시점당 조회수 상위 20개 root, 동일 문서 24시간 쿨다운, 당시 revision의 wikitext 직접 링크로 CORE component를 만드는 순서다. sym focus `τ=0.005`와 D2 bridge 억제를 적용한다. `page_asof_links`가 revision별 링크 캐시다. 현재 페이지나 렌더된 `parse.links`로 historical 입력을 대체하지 않는다. Clickstream 확장 레이어는 기본 OFF다.

종목 후보는 `stock.embedding`의 코사인 상위 20개와 GDELT 근거 상위 10개를 합친다. 검증 모델 기본값은 `gpt-5.4-nano`, 요약 기본값은 `claude-sonnet-4-5-20250929`다. AI 작업은 후보 생성·검증·요약 워커로 분리한다. 요약·검증 재사용은 원본 클러스터 `snapshot_ts <=` 대상 `snapshot_ts`를 만족해야 한다. 일일 호출량은 `llm_daily_usage`에서 UTC 날짜별로 원자적으로 제한한다.

## 3. 데이터와 시점 계약

- PostgreSQL 스키마의 정본은 `db/migrations`다. `db/apply_migrations.py`가 번호 순서대로 적용한다. 저장소 파일은 V1~V16·V20·V21이며 번호 17~19가 비어 있는 것은 누락 여부의 증거가 아니다. 적용 이력은 운영 DB의 `schema_migration`으로 따로 확인한다.
- `cluster_snapshot`은 완료된 0건 시점도 저장한다. `issue_cluster`은 한 시점의 이슈, `cluster_member`는 그 시점에서 고정한 지표다. 과거 API가 최신 원시 편집·조회수 행으로 값을 보충하면 안 된다.
- 리플레이의 대표 도입부는 `page_intro`에서 `rev_ts <= snapshot_ts`인 마지막 revision을 쓴다. 당시 revision이 없으면 현재 위키 도입부로 폴백하지 않는다.
- `wiki_page.title`은 영어 식별자다. `title_ko`는 ko.wikipedia 제목, `title_ko_fallback`은 Azure Translator 표시용 번역이다. 화면 표시 우선순위는 정식 한국어 제목 → 번역 → 영어다. 번역 문자열로 Wikipedia 링크를 만들지 않는다.
- V16의 `mobile_views`는 전체 `views`의 부분집합이다. 기존 행의 기본 0은 관측된 0이 아닐 수 있으므로 재적재 전 봇 비율 판정에 쓰지 않는다.
- 재클러스터링은 `issue_cluster` 하위 요약·종목·댓글·북마크를 CASCADE로 지울 수 있다. `persist_snapshot`은 downstream 데이터가 있으면 기본 중단하고, 명시적 삭제 허용 옵션과 dry-run을 분리한다.

## 4. API·인증·프론트 설정

공개 API base path는 `/api/v1`이다. 이슈 피드·스냅샷·맵·상세·기록·순위, 종목 목록·상세·주가, 계정·보관함 경로는 [API 명세](api-v1.md)에 적는다. `frontend/docs/openapi.yaml`은 기존 이슈·종목 경로 중심의 계약이며 2026-09-24 코드에 추가된 계정·기록 경로까지 완전히 반영한 파일로 취급하지 않는다. 신규 문서 작성에서는 Spring 컨트롤러와 DTO를 대조했다.

인증은 동일 출처 HTTPS 프록시에서 HttpOnly·SameSite=Lax 세션 쿠키(`WIKIPULSE_SESSION`)와 CSRF 토큰을 사용한다. 세션은 Spring Session JDBC에 저장한다. 운영 Secure 쿠키 설정과 V15 적용은 배포 시 확인 대상이다. 비밀번호는 BCrypt cost 12로 저장한다. 이메일 인증·재설정·소셜 로그인은 범위 밖이다.

프론트의 `VITE_DATA_SOURCE`는 `mock` 또는 `api`다. 로컬 `.env.example`은 mock, GitLab CI의 develop 빌드는 API 모드다. 기록 화면은 빌드 시 `VITE_ISSUE_HISTORY_ENABLED=true`와 API 모드가 모두 있어야 켜진다. Vite 환경변수는 실행 시가 아니라 빌드 시 번들에 고정된다. `wiki_page.title_ko` 채우기, 후보 생성, 검증, 요약 워커는 기본 설정에서 모두 OFF이며 켜기 전에는 자동 결과가 늘어나지 않는다.

## 5. 운영 한도와 검증 범위

| 항목 | 코드 기본값·계약 | 해석 |
| --- | --- | --- |
| 조회수 원본 지연 | 창 종료 뒤 125~153분 실측, 최종 노출 목표 2~3시간 | SLA 달성 보증이 아님 |
| 후보 생성 | 임베딩 K=20, GDELT K=10 | 검증 통과 종목의 제품 노출 개수 상한은 없음 |
| 3등급 검증 | `tier3-threshold=0` | 생략 게이트 OFF, 후보 최대 30회 검증 범위 |
| 워커 선택 | 요약·후보 각각 스냅샷별 상위 10개 기본 | 두 설정의 범위·출처를 맞춰야 함 |
| 일일 LLM 상한 | 요약 100회, 검증 300회/UTC일 기본 | `llm_daily_usage` 원장 기준; 배포 환경 override 가능 |
| 요약 재시도 | 모델별 저장 실패 최대 3회 기본 | 반복 과금 억제 |
| 종목 주가 | 로컬 시연 44종목 검증 기록 | 전체 종목 일봉 적재를 의미하지 않음 |

코드와 로컬 회귀 테스트는 배포 성공이나 데이터 충족을 대신하지 않는다. 확인된 운영 스키마 최대 버전은 2026-09-22 기준 V14이고, 그 뒤 파일(V15·V16·V20·V21)의 실제 운영 적용 상태는 이 문서 작성 과정에서 재확인하지 않았다. 기본 급증 판정의 실제 문서 생성일 연동, GDELT lift 자동 집계, AI 워커 상시 활성화, 수정된 2개월 replay 완료 역시 별도 구현·운영 증거가 필요하다.

## 6. 실행·근거

- 로컬 API: `cd backend && ./gradlew test` (Windows: `gradlew.bat`).
- 로컬 프론트: `cd frontend && npm ci && npm run build`.
- DB 스키마·검증: `db/apply_migrations.py`, `db/tests/`, `tools/test_local_migrations.py`.
- 계정 계약·배포 순서: [계정·보관함 구현 문서](backend/ACCOUNT_BOOKMARKS.md).
- 상세 실측·남은 이슈: [v0.3 기술 기록](tech-spec-v0.3.md), [2026-09-23 이어서 하기](https://github.com/ClOhmYee/WikiPulse).
