# 골든 데이 파이프라인 검증 — 2025-06-12 UTC

- 실행 시각: **2026-09-17 19:08~19:16 KST**
- 대상: 추가 EC2 HDFS·Spark 2 Worker → 기본 EC2 PostgreSQL
- 데이터 일자: **2025-06-12 UTC**
- 원칙: 기존 설정·컨테이너·UFW를 바꾸지 않고 총 2코어·executor 1 GiB로 실행
- 승인된 영구 변경: 해당 날짜의 원시 편집·조회수 집계를 PostgreSQL에 멱등 적재

## 1. 결론

실제 HDFS 원본을 두 Spark Worker가 읽어 문서·시간 단위로 결합하고 PostgreSQL에 적재하는
경로는 통과했다. 같은 입력을 두 번 적재해도 행 수가 늘지 않았다.

다만 `page_baseline`이 0건이고 실제 문서 생성 시각도 저장되지 않아, 조회수 100 이상인
4,474개 시간창을 `spike`로 확정하지 않았다. 따라서 이번 검증은
`원본 → Spark 집계 → 원시 신호 DB 적재`까지 PASS이고,
`spike → 클러스터 → 요약·종목 → API·화면`은 선행 데이터 부족으로 BLOCKED다.

## 2. 실제 입력

| 원본 | HDFS 경로 | 매니페스트 |
| --- | --- | --- |
| 편집 | `/wikipulse/raw/mediawiki_history/wiki=enwiki/year=2025/month=06` | 원본 515,334,641 B, 5,501,827행 읽음, namespace 0 편집 이벤트 3,361,013건, gzip shard 7개 |
| 조회수 | `/wikipulse/raw/pageview_complete/wiki=enwiki/date=2025-06-12/agent=user` | 원본 568,075,593 B, 49,889,862행 읽음, enwiki user 레코드 38,183,804건, gzip shard 10개 |

조회수 적재본에는 `ts_hour`가 있어 시간 단위 결합이 가능했다. 이번 canary에서는 운영
소스로 확정된 `other/pageviews`가 아니라 현재 HDFS에 있는 `pageview_complete` user를
사용했다. 인프라·데이터 계약 검증에는 유효하지만 운영 소스 대체로 간주하지 않는다.

## 3. Spark 실행

- 애플리케이션: `app-20260917100851-0008`
- 제한: total executor cores 2, executor core 1, executor memory 1 GiB, driver 512 MiB
- 참여 Worker: `192.0.2.10`, `192.0.2.20`
- 수행:
  1. 6월 편집 원본에서 6월 12일·봇 제외 편집 선택
  2. 제목을 공백형 canonical key로 정규화
  3. 문서·UTC 시간별 편집 수, 편집자 수, byte delta 집계
  4. 같은 키의 user 조회수 합계와 left join

| 지표 | 결과 |
| --- | ---: |
| 사람 편집 | 107,807건 |
| 편집 시간창 | 72,632개 |
| 편집 문서 | 60,412개 |
| 조회수 행 결합 성공 | 61,197개 |
| 조회수 행이 결합되지 않은 편집 시간창 | 11,435개 |
| 현재 조회수 100 이상 | 4,474개 |

조회수 미결합 11,435개는 곧바로 “조회수 0”으로 확정하지 않는다. 실제 0회, 제목 정규화
불일치, 원본 결손을 표본 대조한 뒤 구분해야 한다.

## 4. 실제 사건 표본

`Strait of Hormuz`는 이날 사람 편집 시간창이 없어 1차 관문을 통과하지 않았다. 사전에
기대 사건을 고정해 결과를 끼워 맞추지 않고, 실제 상위 결과를 사용했다.

| 문서 | UTC 시간 | 사람 편집 | 편집자 | 조회수 |
| --- | --- | ---: | ---: | ---: |
| Vijay Rupani | 12:00 | 28 | 17 | 103,716 |
| Vijay Rupani | 11:00 | 29 | 12 | 96,154 |
| Air India Flight 171 | 13:00 | 142 | 46 | 66,593 |
| Air India Flight 171 | 12:00 | 123 | 50 | 65,126 |

`Air India Flight 171`은 08:00의 편집 4건·조회수 3회에서 09:00의 편집 126건·조회수
24,669회로 상승했다. 기준선과 생성 시각이 준비되면 신규 문서 절대 하한 경로를 검증할
대표 골든 케이스다.

## 5. PostgreSQL 영구 적재

적재 전 해당 날짜의 `page_edit_window`, `page_view_hourly`, `spike`는 모두 0행이었다.

| 테이블 | 적재 결과 |
| --- | ---: |
| `wiki_page` | 60,412개 자연키 upsert |
| `page_edit_window` | 72,632행 upsert |
| `page_view_hourly` | 61,197행 upsert |
| `spike` | 0행 |

같은 CSV를 다시 적재한 뒤에도 `72,632 / 61,197 / 0`으로 동일했다. 자연키와 기본키
upsert가 재실행 중복을 막았다. 기존 행 삭제는 하지 않았다.

## 6. 단계별 판정

| 단계 | 판정 | 근거 |
| --- | --- | --- |
| HDFS 실제 원본 읽기 | PASS | 편집 7개·조회수 10개 shard 읽기 |
| Spark 2노드 분산 집계 | PASS | 두 Worker executor 참여, 종료 코드 0 |
| 제목·시간 키 결합 | PASS | 61,197개 시간창 결합 |
| PostgreSQL 원시 신호 적재 | PASS | 트랜잭션 commit, 정확 행 수 확인 |
| 재실행 멱등성 | PASS | 두 번째 적재 후 행 수 불변 |
| 조회수 기준선 | BLOCKED | 해당 문서들의 `page_baseline` 0건 |
| 실제 생성 시각 | BLOCKED | `wiki_page.first_seen`은 시스템 관측 시각일 뿐 |
| `spike` 확정 | BLOCKED | 기준선·생성 시각 없이 4,474건을 확정하면 오탐 |
| 클러스터·요약·종목 | BLOCKED | 입력 `spike` 0건 |
| API·버블맵 | BLOCKED | Backend·Frontend 미배포 |

## 7. 다음 실행에 필요한 것

1. `2025-05-15~06-11`의 시간별 `other/pageviews`와 6월 12일 파일을 적재한다.
2. ~~`mediawiki_history.page_creation_timestamp`를 별도 컬럼에 보존한다.~~ → 최초 revision
   기준으로 교정 완료(2026-09-18). `page_first_edit_timestamp`를 우선하고 결측일 때만
   이벤트보다 미래가 아닌 `page_creation_timestamp`를 쓴다.
3. 기존 문서는 직전 28일, 생성 28일 미만 문서는 생성 이후 표본으로 `page_baseline`을 만든다.
4. `Air India Flight 171` 등 실제 표본에 두 단계 detector를 실행한다.
5. 확정 `spike`만 클러스터·요약·종목 검증으로 넘긴다.

## 8. 정리와 서버 영향

- HDFS 임시 경로 `/wikipulse/spark/_golden_day_20250612` 삭제 확인
- 양쪽 호스트와 Spark/PostgreSQL 컨테이너의 `/tmp/golden_day_*` 삭제 확인
- 설정, Compose, 컨테이너, UFW, 토픽은 변경하지 않음
- Spark worker 애플리케이션 로그는 기존 TTL 정책에 따라 잠시 남을 수 있음
- 영구 잔여물은 사용자 승인 범위인 PostgreSQL 원시 신호 행뿐임
- 종료 점검(19:20 KST): 양쪽 UFW active, 추가 EC2 가용 RAM 12 GiB·루트 디스크 300 GB 가용,
  HDFS 104 blocks HEALTHY·복제 2·누락/손상/미복제 0

## 9. 관련 로컬 회귀 검증

- 당시 전체 Python 테스트: **515 passed, 20 skipped, 0 failed/error**
- WP-118 로컬 구현 후 전체 회귀: **538 passed, 20 skipped, 0 failed/error**
- `git diff --check`: 통과
- 문서의 로컬 Markdown 링크와 이번 실행용 `golden_day_*` 임시 파일 제거: 확인
- 공통 판정기에 더해 실제 생성 시각 저장·직전 28일 기준선·시간별 조회수 후보 재평가를
  로컬 PostgreSQL에서 관통 검증했다. 이후 로컬 시간별 파일 loader도 구현했지만 이 골든
  데이 EC2 실행 결과에는 소급 적용하지 않았다. LIVE scheduler와 2개월 실데이터 검증이 없어 WP-118 전체
  완료로 판정하지 않는다.

## 10. 로컬 후속 검증 (2026-09-18, EC2 미사용)

위 EC2 실행 결과는 당시 사실로 유지하고, 같은 2025-06-12 입력을 로컬에서 현행 코드로
다시 검증했다. 편집 덤프 5,501,827행과 실제 `other/pageviews` 시간별 파일 24개를 사용했고,
기존 문서 기준선 값만 경로 검증용 통제값으로 주입했다. 따라서 아래 결과는 생성 시각·조회수
결합·재평가 경로의 증거이며 실제 28일 기준선 품질의 증거는 아니다.

| 항목 | 결과 |
| --- | ---: |
| 편집 윈도우 / 문서 | 72,632 / 60,412 |
| 최초 revision 확인 / 미확인 문서 | 60,363 / 49 |
| 시간별 조회수 적재 | 781,882행, 합계 19,713,507 |
| 재적재 후 상태 | 행 수·합계 동일 |
| 최종 평가 / creation 대기 | 72,559 / 73 |
| views 대기 / baseline 대기 | 0 / 0 |
| 저장된 spike | 4,465 |
| 재평가 두 번째 저장 | 0 |

`creation 대기 73`은 당일 행만으로 생성 시각을 만들었을 때의 보수적 결과다. 같은 2025-06
월 전체 메타데이터를 사용한 후속 전수 감사에서 13개 윈도우가 복원되어 대기는 60개가
됐다. 현재 MediaWiki API는 45개 잔여 제목 중 30개의 page ID가 당시와 달라 historical
replay 보정에는 사용할 수 없었다. 원인별 전수 결과는
[생성 기준 시각 대기 감사](validation/2026-09-18-creation-pending-audit.md)에 보존한다.

후속 코드·문서 반영 뒤 전체 Python·DB 회귀는 **556 passed, 20 skipped, 0 failed**였다.

`Air India Flight 171`은 덤프 최초 revision과 LIVE API가 모두 `08:58:02 UTC`였다.
08:00 윈도우는 편집 4·조회수 3으로 미탐, 09:00은 편집 126·조회수 24,669로 탐지됐다.
같은 시간대 중간에 생성된 문서를 허용하고, 신규 28일 경계는 `window_end`에서 계산한다.
메타데이터 시각이 `window_end` 이상이면 배치를 중단하지 않고 `creation` 대기로 남긴다.
