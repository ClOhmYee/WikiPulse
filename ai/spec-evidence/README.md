# 명세 §11 근거 수치 재현 스크립트 (WP-53)

`docs/requirements-v0.3.md` §11의 실측 수치를 뽑은 스크립트가 저장소에 없어서
(본문에도 "재현 스크립트는 아직 대부분 저장소 밖에 있다"고 적혀 있었다) 다시
뽑을 수 있게 올린다. 프로덕션 코드 아님 — 근거 재현·재검증용.

개인 절대경로·API 키 없음 — 전부 인증 불필요한 공개 엔드포인트만 쓴다
(`CONTACT_EMAIL`만 EventStreams 스크립트에 필요, Wikimedia 정책).

## 스크립트 ↔ §11 행 대응표

| 스크립트 | §11 행 | 2026-09-16 재실행 결과 | 원 실측(날짜) |
| --- | --- | --- | --- |
| `eventstreams_throughput.py` | EventStreams 처리량 | 전체 28.7/s · enwiki 1.7/s · 1,309 B/건 (15초) | 전체 31/s · enwiki 2/s · 1.5 KB/건 (2026-09-04) — 표본이라 매번 변동 |
| `gdelt_day_size_gaps.py` | GDELT GKG 하루 / GDELT 결손 | 2024-10-10 = 657 MB, 96/96 슬롯 존재. 결손 구간 이분 탐색으로 **2025-06-14 18:00~07-02 02:00 UTC로 확정**(15분 정밀도, 아래 함정) | 627 MB / 1.9 GB, 결손 2025-06-13~07-04 "전부"(2026-09-07, 표본 없이 어림잡은 경계) |
| `wikidata_ticker_trap.py` | Wikidata 티커 | naive 43 · correct 15,890 · NYSE+NASDAQ 3,910 | 40 / 15,875 / 3,905 (2026-09-04) — 며칠 새 소수 추가된 정도, 함정 재현 확인 |
| `wiki_link_graph_join.py` | 위키 링크 그래프 → 상장기업 | Hormuz 1405 중 2 · Milton 1219 중 3 · Iran 103,603 중 26 · Nvidia 2934 중 571 | Hormuz 1358 중 0 · Milton 1218 중 3 · Iran 4308 중 4 · Nvidia 507 (2026-09-04) — 아래 함정 참고, 방법론이 100% 같지 않다 |
| `dump_sizes.py` | Wikimedia 덤프 | mediawiki_history 2025-06=515,334,641B·2024-10=596,614,108B(§11과 **바이트까지 일치**), clickstream 501MB, pageview_complete 590MB | 515,334,641B·596,614,108B (2026-09-10), clickstream 471MB (2026-09-04) |

GDELT lift(Milton)와 임베딩 겹침은 이미 다른 poc가 재현 가능하게 갖고 있다 —
새로 안 만들었다: `ai/gkg-alias-poc/measure.py`(lift), `ai/candidate-overlap/`,
`ai/matching-goldset/`(임베딩 겹침).

## 실행

```bash
cd ai/spec-evidence
CONTACT_EMAIL=you@example.com py -3 eventstreams_throughput.py 15
py -3 gdelt_day_size_gaps.py 20241010
py -3 wikidata_ticker_trap.py
py -3 wiki_link_graph_join.py "Hurricane Milton"
py -3 dump_sizes.py
```

`edit_source_gap.py` 는 §11 행이 아니라 **WP-163 전용**이다. 실행법과
결과는 [편집 소스 공백 대안 실측](../../docs/validation/2026-09-21-edit-source-gap.md)
에 있다. 위 함정 2번(스냅샷 통째 교체)과 같은 축이고, 거기서 한 걸음 더 들어가
**마지막 달 파일이 잘려 있다**는 것까지 잰다.

`requirements.txt` 없음 — `requests` 하나만 쓰고 나머지는 표준 라이브러리 +
`data-pipeline`의 순수 함수(`gdelt/catalog.py`, `gkg/match.py`, `producer/sse.py`)
재사용.

## ⚠️ 재현 중 발견한 함정 (3건)

1. **GDELT 결손 구간 경계가 처음 기록(2026-09-07)보다 좁다.** 5점 표본으로는
   구간 시작·끝 정각(`2025-06-13 00:00`, `2025-07-04 23:45`)에 파일이 있다는
   것만 보였다 — "경계가 어디로 옮겨갔는지"는 몰랐다. `check_gap()`을 5점
   표본에서 **이분 탐색**으로 바꿔 15분 정밀도까지 좁힌 결과: 실제 결손은
   **2025-06-14 18:00 ~ 2025-07-02 02:00 UTC**뿐이다(양끝 경계 각각 확인,
   내부는 표본 4곳 전부 여전히 404 — 연속 결손 맞음). 원래 경계가 처음부터
   근사치였던 것으로 보인다("전부 404"는 맞았지만 범위가 넓게 잡혀 있었다).
   `docs/requirements-v0.3.md`·`tech-spec-v0.3.md`·`data-pipeline/gdelt`·
   `gkg`의 관련 서술을 이 값으로 갱신했다(WP-53 후속, 이 커밋).

2. **`mediawiki_history` 는 매달 스냅샷 디렉터리를 통째로 새로 깎고 옛것을
   지운다.** 2026-09-16 기준 살아있는 스냅샷은 `2026-07`·`2026-08` 뿐이다.
   콘텐츠는 안 사라졌다 — 스냅샷 디렉터리 안에 2001년부터 지금까지 전체
   콘텐츠 월이 다 들어있고(`{스냅샷}.enwiki.{콘텐츠월}.tsv.bz2`), 항상
   **최신 스냅샷 밑에서** 옛 콘텐츠 월을 찾아야 한다. `batch/ingest.py`
   (WP-56)는 이미 이걸 알고 `--snapshot`/`DUMP_SNAPSHOT` 파라미터로
   대응해뒀지만 `DEFAULT_SNAPSHOT = "2026-08"`가 **하드코딩**이라 다음 스냅샷
   교체 때 조용히 낡는다 — 재실행 전에 최신 스냅샷을 확인할 것.

3. **위키 링크 그래프 조인은 Wikidata 라벨 이름 매칭이라 완전히 같은 방법론이
   아니다.** 원 실측(2026-09-04)이 QID 기반 조인이었는지 기록이 없어 이 스크립트는
   상호명 정규화 매칭(`gkg/match.py` 재사용)으로 근사했다. Milton(3개)·Nvidia
   (571 vs 507, 같은 자릿수)는 방향이 맞지만, Hormuz는 0 대신 2개가 걸렸다
   (`.om`이라는 이름의 Wikidata 항목이 우연히 매치되는 등 문자열 매칭 특유의
   오탐), Iran은 이웃 자체가 4,308개가 아니라 103,603개로 나온다 — "Iran"이
   백링크가 극단적으로 많은 허브 문서라 그런 것으로 보이나, 원 실측이 백링크를
   포함했는지 원 스크립트가 없어 확인이 안 된다. **결론(CLAUDE.md 폐기 절)의
   방향 자체("사건 문서 주변엔 상장기업이 없다, Nvidia류 기업 문서만 예외")는
   이 근사로도 재현되지만, 정확한 개수를 그대로 믿지는 말 것.**

## 남은 것

- 인수조건 4("다른 팀원 PC에서 한 번 실행해 동작을 확인한다")는 이 커밋만으로는
  못 채운다 — 리뷰어가 로컬에서 한 번 돌려봐야 한다.
