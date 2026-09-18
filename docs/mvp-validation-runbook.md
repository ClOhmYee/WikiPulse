# MVP 구현·검증 실행서

- 작성 기준: **2026-09-17 18:12~18:30 KST 로컬·EC2 실측 + 2026-09-18 로컬 후속 검증**
- 제품 정본: [requirements-v0.3.md](requirements-v0.3.md)
- 기술 정본: [tech-spec-v0.3.md](tech-spec-v0.3.md)
- 인프라 인계: [프로젝트 문서](https://github.com/ClOhmYee/WikiPulse)
- 골든 데이 실측: [golden-day-validation-2025-06-12.md](golden-day-validation-2025-06-12.md)

이 문서는 요구사항을 다시 정의하지 않는다. **무엇을 어디에서 확인해야 MVP라고 말할 수
있는지**와 그 실행 순서를 고정한다. 진행률은 Jira에서 관리하고, 이 문서에는 검증 계약과
재현 가능한 증거만 남긴다.

## 1. 완료 정의

MVP는 아래 한 문장을 실제 데이터로 시연할 수 있어야 한다.

> 최근 2개월 동안 어떤 이슈가 있었는지 시점별 버블맵으로 돌아보고, 지금 이슈가 되는
> 항목도 같은 화면에서 확인하며, 각 이슈의 한국어 요약과 검증된 미국 상장 종목 및 연결
> 근거를 본다.

다음 일곱 항목을 모두 통과해야 한다.

| 게이트 | 통과 조건 | 현재 판정 (2026-09-18) |
| --- | --- | --- |
| G1 원본 | `2026-07-17~09-17` 편집·시간별 조회수·일별 user 조회수·GDELT·Clickstream 원본의 날짜별 매니페스트와 결손 사유가 있다 | **FAIL** — EC2 HDFS에는 2025년 표본만 있고 해당 구간 원본을 찾지 못함 |
| G2 공통 판정 | 과거와 LIVE가 `사람 편집 1건 → 조회수 급등`의 같은 코드 경로를 사용한다 | **PARTIAL** — 2025-06-12 실제 편집 덤프와 24시간 `other/pageviews`의 로컬 PostgreSQL E2E 통과. LIVE scheduler·실제 28일 기준선·고정 2개월 회귀가 남음 |
| G3 스냅샷 | 과거 여러 시점과 최신 시점의 점수·멤버가 DB에 저장되고 미래 근거가 과거에 섞이지 않는다 | **PARTIAL** — 2025-06-12 실제 원본으로 seed-only 스냅샷 15개 저장. historical 도입부·멤버 조회수·`completeness`·revision 감사 필드는 WP-129로 로컬 구현했지만 실제 replay를 다시 돌리지 않았다. 요약·종목 결과 재사용의 대상 스냅샷 상한도 미완료 |
| G4 보강 | 이슈 요약, 후보 종목, LLM 검증, 상태 전이가 멱등 실행되고 실패와 정상 0건을 구분한다 | **PARTIAL** — 실제 BA 임베딩·후보·GATEWAY LLM 검증 통과. 요약 writer·상태 전이는 WP-119로 구현했지만 worker 기본값이 꺼져 있고 실제 GATEWAY 실행·GKG 검색 술어 자동 배선·EC2 검증이 없음 |
| G5 서빙 | PostgreSQL → Spring API → React 화면에서 지도·피드·리포트·종목 상세가 같은 시점을 가리킨다 | **PARTIAL** — 실제 canary DB → Spring API → Frontend dev proxy 통과. 상세 members 고정 조회는 WP-129로 구현했지만 같은 실데이터 경로를 재검증하지 않았고 브라우저 시각 검증·가격 연결도 남음 |
| G6 LIVE | 실제 편집 1건부터 최종 노출까지 통상 1~2시간, 시간별 원본 도착 뒤 내부 15분 이내로 이어진다 | **FAIL** — Kafka 실데이터와 실행 중 소비자가 없음 |
| G7 재현 | 로컬 명령과 EC2 배포 파일이 저장소에서 재현되고 비밀값은 외부 주입된다 | **FAIL** — EC2 `~/infra/*`가 저장소에 없음 |

**현재 결론:** UI mock은 시연 가능하고 분산 인프라는 동작하지만, 실제 2개월 원본과 LIVE
흐름을 사용한 MVP는 아직 아니다.

## 2. 판정 표기와 증거 규칙

| 표기 | 의미 |
| --- | --- |
| PASS | 명령·시각·입력 범위·결과가 남아 있고 같은 상태에서 재현 가능 |
| PARTIAL | 일부 경계·조건만 증명됐으며, 명시한 수동 단계·결함·미검증 항목이 남아 있음 |
| FAIL | 실행했으나 수용 기준을 만족하지 못함 |
| BLOCKED | 권한·키·외부 데이터 등 현재 작업자가 해소할 수 없는 선행 조건이 있음 |
| UNAVAILABLE | 필요한 실행 도구가 현재 장비에 없어 실행하지 못함 |

빌드 성공, mock 화면, 서비스 프로세스 존재를 실제 E2E 성공으로 바꾸어 쓰지 않는다. 모든
검증 기록에는 다음을 남긴다.

- Git 커밋 SHA와 실행 환경
- 입력 데이터 기간·건수·체크섬 또는 매니페스트
- 실행 명령과 시작·종료 시각
- 출력 행 수, 누락·중복 수, 단계별 지연
- PASS/FAIL/BLOCKED/UNAVAILABLE와 원인
- 서버 쓰기가 있었다면 생성 경로, 영구 잔여물, 정리 결과

## 3. 로컬에서 먼저 끝낼 일

정확성, 데이터 계약, 외부 API 비용, 브라우저 동작은 로컬에서 검증한다. 로컬에서 실패한
코드를 EC2에 올려 디버깅하지 않는다.

### L0. 개발 환경 기준선

| 항목 | 실행 | 통과 기준 |
| --- | --- | --- |
| Python | Python 3.11 환경에서 `python -m pytest data-pipeline db/tests -q` | 실패 0. Spark·외부 서비스 skip은 사유 기록 |
| Backend | Java 17에서 `backend/gradlew.bat test --no-daemon` | 실패 0 |
| Frontend 정적 검사 | `npm ci`, `npm run lint`, `npm run test:data`, `npm run test:contract`, `npm run build` | 모두 종료 코드 0 |
| Frontend 브라우저 | `npm run test:e2e`, `npm run test:api`; dev 서버 5174에서 `test:a11y`; preview 4174에서 `test:production` | 실패 0, 실제 API 호출 여부를 구분 |
| 로컬 스택 | Docker Desktop 기동 후 루트 `docker-compose.yml` | PostgreSQL·Kafka·Spark health 통과 |

2026-09-17~18 실행 결과:

- Python·DB 테스트: **556 passed, 20 skipped** (2026-09-18 로컬 전체 회귀)
- Frontend: lint PASS, 데이터 **27 passed**, 계약 **375개 스냅샷 및 500노드/1,000간선** PASS,
  E2E **38 passed**, API 모드 **13 passed**, 접근성 **48페이지/실패 0**, production smoke PASS
- Frontend production build PASS. 온보딩 청크 906.71 kB 경고는 기존 알려진 위험이며 빌드 실패는 아님
- Backend: **UNAVAILABLE** — 이 PC에는 Java 21만 있고 프로젝트 toolchain은 Java 17
- Docker: **UNAVAILABLE** — 로컬 Docker Desktop daemon이 꺼져 있음

### L1. 2개월 원본 카탈로그

원본을 처리하기 전에 다음 표를 날짜 단위로 만든다. 파일이 있다는 것과 기간이 완전하다는
것은 다르다.

| 원본 | 필수 범위 | 검증 |
| --- | --- | --- |
| 편집 | 2026-07-17~09-17 | enwiki namespace 0, 사람/봇 플래그, event-time, 중복 키 |
| `other/pageviews` | 같은 기간의 시간별 파일 | 24시간 슬롯, 압축 해제·행 파싱, 지연·결손 |
| `pageview_complete` user | 같은 기간의 일별 파일 | `agent=user`, 날짜별 매니페스트 |
| GDELT GKG | 같은 기간의 15분 파일 | 96슬롯/일과 공식 결손 구분 |
| Clickstream | 각 스냅샷에서 사용할 완료 월 | 스키마·월·행 수·직전 월 폴백 |

카탈로그에는 `source`, `period_start`, `period_end`, `file_count`, `bytes`, `checksum`,
`validation_status`, `gap_reason`을 둔다. 다운로드 실패를 정상 0건으로 기록하지 않는다.

**현재 실측:** 로컬 저장소와 EC2 HDFS에서 고정 MVP 구간의 실제 원본을 찾지 못했다.
프론트의 375일/1,112개 시드는 API·화면용 수작업 데이터이고 이 카탈로그를 대신하지 않는다.

### L2. 작은 실제 데이터로 공통 파이프라인 완성

전체 2개월 전에 실제 사건 하루를 골든 구간으로 정한다. 권장 순서는 `1시간 → 1일 → 7일
→ 2개월`이다. 각 확대 단계는 이전 단계의 모든 불변식을 다시 검사한다.

1. 편집 원본을 공통 `edit_event`로 정규화한다.
2. 사람 편집 1건 이상인 문서만 조회수 후보로 만든다.
3. 해당 시간의 `other/pageviews`가 도착하기 전에는 후보 대기로 남긴다.
4. 기존 문서는 직전 28일, 생성 28일 미만은 생성 이후 기준선으로 조회수 급등을 판정한다.
5. 통과 문서를 클러스터링하고 완료된 Clickstream 월만 연결 근거로 쓴다.
6. 스냅샷을 멱등 저장하고 같은 `(source, snapshot_ts)` 재실행에서 행 수가 늘지 않는지 본다.
7. GDELT 컨텍스트·임베딩 Top-K·LLM 검증·한국어 요약을 실행한다.
8. `DETECTED → VERIFYING → CONFIRMED`와 실패/재시도를 확인한다.
9. API와 브라우저에서 동일한 `snapshotTs`·`issueKey`·종목 연결을 확인한다.

1~4번의 로컬 코드 경로는 `page_metadata.py` → `page_metadata_sink.py` →
`baseline_refresh.py` → `hourly_pageview_ingest.py` → `recheck.py` 순서로 구현되어 있다.
시간별 gzip 파싱과 PostgreSQL 적재는 공식 포맷의 합성 파일에 더해 2025-06-12 실제
편집 덤프 5,501,827행과 `other/pageviews` 24개 파일로 관통 검증했다(2026-09-18).
72,632개 윈도우는 `평가 72,559 + creation 대기 73`으로 보존됐고 조회수·기준선 대기는
0개였다. 이때 73개는 **당일 행만으로 생성 메타데이터를 만든 결과**다. 같은 월 전체를
다시 읽으면 13개가 복원되어 `creation` 대기는 60개로 줄었다. historical replay는 대상
snapshot/month 전체에서 생성 시각을 보강하고, 현재 MediaWiki API는 미래 정보와 재생성된
동명 페이지가 섞이므로 LIVE 보강에만 사용한다. 상세 수치와 원자료는
[생성 기준 시각 대기 감사](validation/2026-09-18-creation-pending-audit.md)에 기록했다.
조회수 기준선 값은 경로 검증용 통제값이므로 실제 28일 기준선 품질 증거는 아니다. 실제
2개월 원본 실행과 파일 도착 주기 실행은 별도다.

5~9번은 `Air India Flight 171` 대표 이슈 하나로 후속 canary를 수행했다. 실제 원본에서
15개 spike·15개 seed-only 스냅샷을 저장하고 BA 임베딩·후보 생성·실제 GATEWAY LLM 검증,
PostgreSQL → Spring API → Frontend dev proxy까지 관통했다. canary 당시 GKG lift와 요약·상태
전이는 수동 bridge였고, 현재 Wikipedia 도입부 사용과 멤버 조회수·completeness 누락을
발견했다. 이후 WP-119·129로 해당 writer와 시점 고정 경로를 구현했지만 이 canary를
다시 실행하거나 EC2에서 검증하지 않았다. 따라서 이 결과는 경계 연결 증거이지 2개월 replay·LIVE 자동화 완료 증거가 아니다.
상세는 [1일 E2E canary](validation/2026-09-18-one-day-e2e-canary.md)를 따른다.

필수 음성 테스트는 원본 미도착, 중복 이벤트, 순서 역전, GATEWAY 실패, GDELT 결손, 검증 종목
0건, 과거 스냅샷에 미래 요약·Wikidata·Clickstream이 들어오는 경우다.

모든 실데이터 검증은 입력 범위·체크섬·명령·수치·한계와 함께
[검증 기록 색인](validation/INDEX.md)에 추가한다. 명세에는 검증에서 확정된 계약과 보고서
링크만 남긴다.

### L3. 종목 보강과 비용 검증

- 약 5,100개 미국 보통주 마스터와 사업 설명의 누락·중복·상장폐지 처리 확인
- `text-embedding-3-small` 1,536차원 적재 및 재실행 캐시 적중 확인
- 대표 사건 10건 이상에서 관련/무관 종목을 함께 평가해 근거 없는 종목이 노출되지 않는지 확인
- LLM 실패는 `VERIFYING` 또는 재시도로 남고 빈 정상 결과로 확정되지 않는지 확인
- GATEWAY 호출 수·크레딧·응답 지연을 사건별로 기록
- yfinance 가격 적재 → `/stocks/{ticker}/prices` → 그래프·이슈 마커까지 확인(WP-124)

### L4. 로컬 E2E 완료 기준

다음 SQL·HTTP·화면 증거가 한 실행에서 연결되어야 한다.

- `page_edit_window`, `page_view_hourly`, `spike`에 실제 원본 행 존재
- `cluster_snapshot`, `issue_cluster`, `cluster_member`, `cluster_edge`에 과거 여러 시점 존재
- `issue_report`, `cluster_stock`, `stock`, `stock_price`에 실제 파이프라인 결과 존재
- 8개 GET API가 mock 없이 해당 행을 반환
- `/pulse`에서 과거 시점 이동과 최신 시점 선택 가능
- 지도 → 리포트 → 검증 종목 → 종목 가격 → 관련 이슈 왕복 가능
- 같은 입력을 다시 실행해 중복이 늘지 않음

## 4. EC2에서만 확인할 일

EC2는 분산성, 장기 실행, 서버 간 네트워크, 배포 URL을 검증한다. 알고리즘 정확성이나 DTO
수정은 로컬에서 끝낸 후 올린다.

### E0. 변경 없는 사전 점검

접속할 때마다 아래를 먼저 확인한다.

- 두 서버의 `date -Is`, `uptime`, `free -h`, `df -h /`
- `sudo ufw status verbose`가 active인지 확인
- `docker compose ps`, `ss -lntup`
- HDFS `dfsadmin -report`, `fsck /wikipulse`
- Spark Master JSON의 `aliveworkers=2`, `activeapps=0`
- Kafka 토픽·파티션·offset·consumer group
- PostgreSQL `pg_isready`, 마이그레이션·핵심 테이블 행 수
- HTTPS 상태 코드와 실제 응답 본문

2026-09-17 실측 PASS:

- HDFS 2 DataNode, 복제 2, under-replicated/missing/corrupt block 0
- Spark Worker 2대 ALIVE, 제한된 2코어·executor 1GB 작업이 양쪽 Worker에서 실행
- Spark Parquet 20행 HDFS 왕복 일치, 전용 임시 경로 삭제 확인
- Kafka 3파티션 발행·직접 읽기 성공
- PostgreSQL 트랜잭션 쓰기·읽기·ROLLBACK 성공, 영구 행 변화 없음
- 외부 HTTPS 200, UFW active, 두 서버 디스크 사용률 4%, 가용 RAM 12~13 GiB

### E1. EC2에 올리기 전에 필요한 승인

다음은 환경 변경이므로 인프라 담당 또는 사용자 승인을 받은 뒤 실행한다.

- 저장소 checkout·이미지 build/pull·패키지 설치
- `.env`·GATEWAY 키·DB 비밀번호·인증서 작성 또는 교체
- Compose 파일 수정, 컨테이너 생성·재시작·삭제
- DB migration·seed·실데이터 INSERT/UPDATE/DELETE
- Kafka 토픽 생성·삭제·retention 변경·대량 발행
- HDFS 원본 업로드·삭제·replication 변경
- Spark 장기 job 제출 또는 자원 상한 확대
- UFW, Security Group, DNS, Nginx, TLS, Jenkins 변경

승인 요청에는 목적, 정확한 명령, 예상 CPU/RAM/디스크, 영향 서비스, 중단 기준, 복구 명령을
포함한다. 승인 전에는 읽기 전용 명령만 실행한다.

### E2. EC2 검증 순서

1. **저장소 재현성:** `~/infra/*`를 비밀값 없는 템플릿으로 저장소에 옮기고 버전을 고정한다.
2. **1일 canary:** 실제 하루 원본만 HDFS에 업로드해 매니페스트·복제 2·체크섬을 확인한다.
3. **1일 분산 replay:** Spark UI와 로그에서 양쪽 Worker가 실제 task를 수행하고 DB 결과가 로컬과 일치하는지 확인한다.
4. **2개월 업로드:** 날짜별 작은 batch로 올리고 매 batch 뒤 HDFS health·용량·결손을 확인한다.
5. **2개월 replay:** 날짜 checkpoint를 남기고 실패 날짜부터 재시작 가능하게 한다. 전체 재실행으로 멱등성을 확인한다.
6. **LIVE canary:** EventStreams producer와 consumer를 제한 시간 실행해 Kafka lag·중복·시간별 조회수 대기를 계측한다.
7. **서비스 배포:** Backend·Frontend를 띄우고 Nginx가 정적 placeholder가 아니라 실제 앱/API를 라우팅하는지 확인한다.
8. **외부 E2E:** 공인 HTTPS에서 과거 지도·최신 지도·리포트·종목 상세를 브라우저로 검증한다.
9. **재시작 복구:** 한 번에 한 컴포넌트만 재시작해 checkpoint, offset, DB 멱등성이 유지되는지 확인한다.

### E3. 보수적 자원 상한

첫 canary는 Spark `cores.max=2`, executor 1GB, 단일 job으로 시작한다. 다음 조건이면 새 작업을
중단하고 상태만 기록한다.

- 가용 RAM 4 GiB 미만 또는 OOM 발생
- 루트 디스크 가용 공간 150 GiB 미만
- HDFS under-replicated/missing/corrupt block 1개 이상
- Kafka consumer lag가 계속 증가하거나 broker health 실패
- PostgreSQL health 실패 또는 예상 밖의 영구 행 변화
- 기존 서비스가 응답하지 않거나 UFW가 inactive

t3 CPU credit 상태는 프로젝트 계정 권한 없이는 직접 확인하지 못하므로, 장기 replay 전
CloudWatch/계정 측 확인이 필요하다. 이를 확인하지 않은 채 24시간 스트리밍을 시작하지 않는다.

## 5. MVP 우선순위

### P0 — 없으면 MVP가 아님

1. 실제 2개월 원본 카탈로그와 결손 처리
2. WP-118의 2단계 판정 및 시간별 조회수 대기·재평가
3. 실제 원본 replay → 시점별 cluster snapshot. historical 대표 텍스트·멤버 증거값 고정 코드는 구현됐으므로 실제 원본으로 재검증
4. WP-119 요약 worker 활성화·실제 GATEWAY 상태 전이 검증과 요약/종목 재사용의 대상 스냅샷 상한·원 유효 시각 보존
5. WP-120의 GKG 자동 배선·Docker GATEWAY/worker 설정·2개월 수작업 seed 교체. 상세 시점 고정과 임베딩·LLM 한 종목 canary는 로컬 통과
6. WP-124의 가격 API·그래프 연결
7. 실제 DB/API/브라우저와 이후 LIVE 누적 검증. DB/API/Frontend proxy canary는 통과했으나 브라우저·가격·LIVE는 남음

### P1 — 안정적인 시연에 필요

- 실패 재시도, checkpoint, 멱등 재실행, 결손·정상 0건 표시
- one-command 로컬 실행과 EC2 compose 템플릿
- 최소 모니터링: 데이터 기준시각, Kafka lag, 마지막 성공 snapshot, 디스크 사용량
- 시연 직전 고정 데이터 백업과 복구 절차

### P2 — MVP 이후

- Jenkins 자동 배포, Redis 도입, 회원·관심종목·알림·서버 토론
- 장기간 보존 최적화와 완전한 운영 모니터링
- 분산 노드 확대와 고가용성

P2 때문에 P0 구현을 늦추지 않는다.

## 6. 최종 시연 체크리스트

- [ ] 2개월 시작·끝·중간 날짜에서 버블맵이 열리고 서로 다른 실제 사건이 보인다.
- [ ] 최신 시점은 과거 replay와 같은 계약이며 LIVE 기준시각을 표시한다.
- [ ] 선택한 버블의 한국어 요약과 원문 근거가 있다.
- [ ] 관련 종목은 검증 통과분만 보이고 연결 근거가 있다.
- [ ] 종목 상세에 실제 가격과 해당 이슈 시점 마커가 있다.
- [ ] 과거 화면에 미래 문서·요약·종목·Clickstream·Wikidata가 섞이지 않는다.
- [ ] 원본 미도착·GATEWAY 실패·정상 종목 0건이 서로 다른 상태로 보인다.
- [ ] 서비스 재시작 또는 같은 replay 재실행 뒤 중복이 생기지 않는다.
- [ ] mock·수작업 seed·실제 파이프라인 결과를 화면과 검증 기록에서 혼동하지 않는다.

위 체크박스가 모두 실제 데이터 증거와 함께 닫힐 때만 “MVP 완료”로 판정한다.
