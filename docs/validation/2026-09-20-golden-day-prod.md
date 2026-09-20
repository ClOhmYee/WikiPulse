# 2025-06-12 골든데이 운영 적재 — 판정→클러스터→화면

- 검증 ID: `VAL-2026-09-20-PROD-01`
- 실행일: 2026-09-20 KST
- 환경: **서비스 EC2 운영** (`service.example.com`)
- 대상: WP-149
- 판정: **PASS** — 운영 화면에 2025-06-12 실데이터 이슈가 뜬다

## 1. 발견 — 입력은 이미 운영에 있었다

운영 DB 가 "전 테이블 0행" 이라고 알려져 있었는데(WP-147), 실제로는 **replay
입력만 들어가 있고 판정을 한 번도 안 돌린** 상태였다.

```
page_edit_window   72,632   (2025-06-12 00:00 ~ 06-13 00:00, 문서 60,412)
page_view_hourly   61,197   (00:00 ~ 23:00)
wiki_page          60,412
---
page_baseline           0   ← 여기서 끊겼다
spike_candidate         0
issue_cluster           0
```

🔴 **이 경로는 WP-143·-137 과 무관하다.** -143(5432 사설망)은 데이터 EC2 →
서비스 EC2 방향이고, 이 작업은 서비스 EC2 안에서만 돈다. -137 은 다른 기간이다.

## 2. 절차 (저장소만 보고 재현 가능해야 한다)

창 산출물 파일(-58)은 서버에 없다. DB 에 행이 있으므로 **DB 에서 뽑아** `bulk_replay`
입력 형식으로 만든다.

```bash
# 1. page_edit_window ⋈ wiki_page ⋈ page_view_hourly → part-*.jsonl.gz
psql -t -A -c "
SELECT json_build_object(
  'wiki', p.wiki, 'title', p.title,
  'window_start', to_char(w.window_start AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS+00:00'),
  'window_end',   to_char(w.window_end   AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS+00:00'),
  'edit_count', w.edit_count, 'editor_count', w.editor_count, 'views', v.views)
FROM page_edit_window w
JOIN wiki_page p ON p.id = w.page_id
LEFT JOIN page_view_hourly v ON v.page_id = w.page_id AND v.ts_hour = w.window_start
ORDER BY w.window_start;" | gzip -c > <dir>/part-00000.jsonl.gz

# 2. 급증 판정 → spike
python -m spike.bulk_replay --windows <dir> --dsn "$DATABASE_URL"

# 3. 클러스터 스냅샷 → issue_cluster · cluster_member
python -m cluster.driver --dsn "$DATABASE_URL" --source replay
```

둘 다 **멱등**하다. `bulk_replay` 는 `(source, page_id, window_start)` upsert,
`cluster.driver` 는 `(source, snapshot_ts)` 를 지우고 다시 넣는다.

⚠️ `views` 는 없으면 `null` 로 내보낸다. `0` 으로 채우면 `bulk_replay` 가 "미적재" 로
읽어 판정이 갈린다(그쪽 주석).

## 3. 결과

| 단계 | 결과 |
| --- | --- |
| 판정 | 읽음 72,632 → 사전필터 탈락 56,723 → 판정 15,909(문서 13,497) → **급증 4,474** |
| spike 적재 | **4,474행 / 문서 2,238** |
| 클러스터 | **issue_cluster 4,474 · cluster_member 4,474 · 스냅샷 24개** |

화면(`/issues`, 2025-06-13 09:00 KST 스냅샷 기준 156개 이슈):

```
Air India Flight 171                          10.1
Ananda Lewis                                   9.3   (2025-06-11 사망)
Vijay Rupani                                   8.9   (171편 탑승 사망, 전 구자라트 주총리)
Air India                                      8.8
List of sole survivors of aviation accidents   8.1
Campbell Wilson                                7.8   (에어인디아 CEO)
June 2025 Los Angeles protests                 7.4
```

그날의 실제 화제가 상위에 정렬된다.

## 4. 🔴 이번에 드러난 결함 2건

### 4-1. 이미지에 `cluster/` 가 없었다 — **같은 누락 세 번째**

`python -m cluster.driver` 가 `ModuleNotFoundError: No module named 'cluster'` 로 죽었다.
`data-pipeline/Dockerfile` 이 `producer`·`spike`·`batch` 만 복사한다.

| 누락 | 발견 | 이슈 |
| --- | --- | --- |
| `spike` | live-cycle 이 한 번도 안 떴다 | -135 |
| `stock` | 운영 적재가 안 됐다 | -147 |
| `cluster` | 운영 클러스터 생성이 안 됐다 | **-149** |

⚠️ **모듈을 새로 만들면 Dockerfile 에 COPY 를 더하는 것까지가 그 작업이다.** 셋 다
운영에서 처음 드러났다 — 테스트는 소스 트리에서 돌아서 안 걸린다.

### 4-2. `issue_cluster.label` 을 아무도 채우지 않았다

`cluster/snapshot.py` 가 `label=None` 으로 두고, 백엔드 `matching` 에도 채우는 UPDATE 가
없는데 프론트 `PulseCluster.jsx` 는 `cluster.label` 로 제목을 그린다. 운영에 4,474
클러스터를 적재하고 나서야 **제목 없는 버블**로 드러났다.

⚠️ **데모 시드가 가려 줬다.** `docker/seed/*.sql` 은 제목을 직접 넣어 둬서
(`'2026 FIFA World Cup Final'`) 로컬 화면에서는 멀쩡해 보였다. 시드가 파이프라인 산출물과
다른 모양이면 이런 게 안 보인다.

→ `label = seed.title`(루트 씨드 제목)로 고치고 회귀 테스트를 걸었다.

## 5. ⚠️ 이 데이터의 한계 — 시연 전에 알아야 한다

- **급증 4,474건은 많다.** `page_baseline` 이 0이라 **전부** "기준선 없음" 경로를 탔고,
  명세 §3.2 의 절대 하한(조회수 100 이상)만으로 판정됐다. 진짜 기준선 대비 급증이
  아니다. 기준선은 28일치 과거가 있어야 하는데 운영엔 하루뿐이다.
- **멤버가 전부 1개다.** Clickstream 2025-06 덤프가 운영에 없어 씨드 단독 클러스터다.
  버블맵의 간선이 0이다.
- **관련 종목 0개다.** GKG 원본이 운영에 없고 매칭 워커도 꺼져 있다
  (`WIKIPULSE_MATCHING_*=false`). 종목 마스터·임베딩 5,311건은 준비돼 있다(-147).
- **`status` 가 전부 `DETECTED` 다.** 요약·검증 워커가 안 돌았다.

즉 **"수집 → 판정 → 클러스터 → 화면" 은 실데이터로 관통했지만, "클러스터 → 종목" 구간은
아직 비어 있다.**

## 6. 되돌리는 법

```sql
DELETE FROM issue_cluster WHERE source = 'replay';   -- cluster_member 는 CASCADE
DELETE FROM spike WHERE source = 'replay';
```
