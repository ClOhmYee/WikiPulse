# 리플레이 화면 시연 시드 (2026-07-17 ~ 2026-09-17)

`demo-2026-07-17_2026-09-17.sql` — Wikimedia API 실측값을 참고해 수작업으로 조립한
2개월 연속 일별 **API·화면 시연 시드**다. 실제 원본을 공통 파이프라인으로 재생한
산출물이 아니며, 최종 리플레이 데이터로 취급하지 않는다.

## 무엇이 들어있나

18개 이슈를 두 단계로 만들었다. 사건과 일부 수치는 실제 관측이지만 클러스터·점수·상태·
요약·종목 연결은 운영 파이프라인 산출물이 아니라 시연을 위해 구성한 값이다.

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
기준 충족 결과는 전부 포함. 이 16건은 `cluster_stock`을 안 채웠다. 실제 LLM
검증·GDELT/임베딩 계산은 실행하지 않았고, 마지막 이란 이슈 스냅샷 1건에만
§11 기존 실측을 인용한 CVX·XOM·FRO 예시 3건이 붙는다. 왕실 승계 이슈는 관련
상장 종목이 없다고 보고 의도적으로 비워 두었다.

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

## 검증에 쓰면 안 되는 것

2026-09-17 로컬 DB 기준 이 파일은 `issue_cluster` 1,112건을 만들고 전부
`CONFIRMED`로 고정한다. 그러나 `issue_report`는 각 이슈의 **마지막 스냅샷** 18건에만,
`cluster_stock`은 마지막 이란 이슈 스냅샷 1건에 3종목만 연결한다. 같은 `issue_key`라도
이전 날짜의 `cluster_id`를 조회하면 요약·종목은 비어 있다.

따라서 이 시드는 시간 슬라이더·API 형태·결측 UI를 보는 자료일 뿐, 다음 항목의 검증
근거가 아니다.

- `DETECTED → VERIFYING → CONFIRMED` 상태 전이
- 같은 이슈의 시점 간 LLM 판정 재사용과 요약·종목 연결
- 종목 임베딩·GDELT lift·LLM 검증 E2E
- 새 `사람 편집 1건 → 조회수 급등` detector 계약

이 네 항목은 WP-118·119·120에서 실제 파이프라인으로 검증한다. 최종 MVP 완료
조건은 고정 구간 **2026-07-17~2026-09-17**의 편집·`other/pageviews` 시간별 조회수·
`pageview_complete` 일별 user 조회수·GDELT·Clickstream 원본을 LIVE와 같은 정규화·감지·
클러스터링·요약·종목 매칭 계약으로 재생하고, 그 결과로 이 1,112개 시드를 교체하는 것이다.
실제 리플레이가 API·화면까지 검증되기 전에는 해당 원본을 삭제하지 않는다.

과거 시점의 버블 점수·멤버는 그 시점 스냅샷을 쓰고, 요약·검증 종목은 `issue_key` 단위로
재사용하되 선택 시점까지 완료된 결과만 보여야 한다. 조회수 미도착·GATEWAY/GDELT 장애는
빈 정상 결과가 아니라 후보 대기·재시도/처리 중이며, 모든 처리가 끝난 0종목만 정상 0건이다.

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

EC2 실물 DB에도 스키마상 적용할 수는 있지만 임시 시연 외에는 사용하지 않는다
(`db/migrations` V6까지 선행). 최종 MVP 데이터는 실제 공통 파이프라인 재생 결과여야 한다.
검증된 실데이터가 같은 구간을 쓰기 시작하면 이 시드는 제거한다:

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
