# 리플레이 시연 데이터 (2026-07-17 ~ 2026-09-17)

`demo-2026-07-17_2026-09-17.sql` — 실제 위키백과 이벤트 기반 2개월 연속 일별
리플레이 데이터. §10 "리플레이 시연 구간" 실행분(2026-09-17).

## 무엇이 들어있나

18개 이슈, 2단계로 만들었다 — 전부 실측이고 지어낸 시나리오는 없다.

**1단계 — 수동 선정 실제 사건 2건:**

| 이슈 | 기간 | 근거 |
| --- | --- | --- |
| 2026 Iran War — Strait of Hormuz Crisis | 07-17 ~ 09-15 (61일 연속) | 이란-이스라엘 확전·호르무즈 해협 긴장 지속 |
| Harald V 국왕 서거 — Haakon 8세 즉위 | 07-17 ~ 09-15 (61일 연속, 08-28 피크) | 노르웨이 국왕 서거·승계(실제 사건) |

**2단계 — "우리 기준 충족하면 다 뜨게" 요청으로 기계적 스캔 추가 16건:**
위키 Top-100 실측 조회수(일별, 61일 전체)에서 "61일 중 5일 이하 노출 AND
피크 조회수 30만 이상"인 문서를 걸러 찾았다 — 사람이 주제로 고르지 않았다.
FIFA 월드컵 결승 관련 6개 문서는 같은 사건이라 한 클러스터로 묶었고, 나머지
15건은 각각 단일 문서 이슈(배우·성우·정치인·스포츠 인물 부고·화제 등 실제
스파이크). 부적절한 콘텐츠 1건("Ejaculation")만 내용 사유로 제외, 그 외
기준 충족 결과는 전부 포함. 이 16건은 `cluster_stock`을 안 채웠다(-68
미착수라 실제 LLM 검증 없이는 종목 매칭 안 함 — 1단계 2건만 §11 기존 실측을
인용한 설명문이 예시로 붙어 있다).

날짜당 `cluster_snapshot` 1개(그날 활성 이슈 수만큼 `issue_cluster`) —
펄스맵 시간 슬라이더에서 매일 스크럽 가능하고, 날짜에 따라 몇 개가 겹쳐
뜨는지도 실측 그대로 다르다(최신 날짜 09-17은 16개, 조용한 날은 1~2개).

## 실측 vs 근사치 (SQL 파일 상단 주석에도 있음)

**실측(Wikimedia REST API, 2026-09-17 직접 호출)**: 전체 문서(1단계 8개 +
2단계 16개, FIFA 그룹 내 6개 포함)의 일별 edits·views. edits는 2026-08-31
이후 API 처리 지연으로 없다(NULL로 둠, 지어내지 않음). Mojtaba/Ali
Khamenei·혁명수비대의 edit_count·재급증배율은 이 프로젝트 §11 실측
(WP-77)을 재사용. "european_election_2014"는 실측 조회수가 2일치뿐
(아마 리다이렉트)이라 데이터 부족으로 최종 제외.

**이 파일의 근사치(실측 아님)**: view_baseline(관측 구간 자체의 하위
25%), spike_score·pulse_score(로그 스케일 배율, `spike/detector.py`의
실제 z-score 공식이 아님), cluster_stock 근거문(§11 수치를 인용한 설명문,
실제 LLM 검증 산출물 아님 — `-68` 미착수).

## 적용

```bash
# 로컬 docker-compose 스택이 떠 있는 상태에서
docker exec -i wikipulse-postgres psql -U wikipulse -d wikipulse < docker/seed/demo-2026-07-17_2026-09-17.sql

# 이전에 넣은 흔적 있으면 먼저 지우고 (스크립트가 issue_cluster는 자동 정리하지만
# cluster_snapshot은 issue_cluster에 FK로 안 묶여 있어 별도 정리 필요할 수 있음)
docker exec -i wikipulse-postgres psql -U wikipulse -d wikipulse -c "DELETE FROM cluster_snapshot WHERE source='replay';"
```

재실행해도 안전하다(멱등) — 파일 안에서 기존 `demo-%` issue_key와 해당
구간의 `cluster_snapshot`을 먼저 지운다.

## 서버 배포 시

EC2 실물 DB에 그대로 적용 가능(스키마 동일, `db/migrations` 먼저 적용된
상태여야 함 — `V6`까지). 이 데이터는 시연·개발용이며 실제 파이프라인
산출물이 아니므로, 실 파이프라인이 같은 issue_key로 데이터를 쓰기
시작하면 이 시드는 지우는 게 맞다:

```bash
docker exec -i <postgres 컨테이너> psql -U wikipulse -d wikipulse -c "DELETE FROM issue_cluster WHERE issue_key LIKE 'demo-%';"
docker exec -i <postgres 컨테이너> psql -U wikipulse -d wikipulse -c "DELETE FROM cluster_snapshot WHERE source='replay' AND completed_at::date = CURRENT_DATE;"
```

## 재생성 방법

원본 수집·SQL 생성 스크립트는 이 저장소에 커밋하지 않았다(일회성 스크래치,
`scratchpad/gen_replay_seed.py` + `build_sql.py` 패턴). 날짜 구간을
바꿔 다시 뽑고 싶으면:

1. Wikimedia REST API로 대상 문서들의 일별 `edits`(`metrics/edits/per-page`)·
   `views`(`metrics/pageviews/per-article`)를 구간 전체로 한 번에 받는다.
2. 날짜별로 순회하며 그날 `views` 실측이 있는 문서만 그 이슈의 멤버로 넣고,
   `cluster_snapshot`은 날짜당 1건(그날 활성 이슈 수 = `cluster_count`)으로 묶는다.
3. `cluster_member.window_start/window_end`는 반드시 채운다 — NULL이면 펄스맵
   계약 검증이 "metric window" 오류로 스냅샷 전체를 버린다(위 세이프모드 문서 참고).
