# 기관명 → 티커 별칭 실측 (WP-47)

`data-pipeline/gkg/aliases.py`(프로덕션 별칭 테이블)를 만들기 전에 실 GDELT GKG
데이터로 "정확 일치만으로 몇 개나 놓치는지", "별칭을 더하면 몇 개가 붙는지"를
잰 근거 스크립트다. 프로덕션 코드가 아니다 — 실제 매칭은
`data-pipeline/gkg/match.py`(`merge_aliases`) + `driver.py`(`load_ticker_index`).

결과·발견: [RESULT.md](RESULT.md)

## 실행

```bash
py -3 measure.py result.txt
```

네트워크 필요(GDELT GKG 16슬롯 다운로드 + SEC/NASDAQ Trader 실시간 fetch). DB·Spark
불필요 — `gkg/lift.py`·`gkg/match.py`가 이미 순수 파이썬으로 설계돼 있다.

## 방법

1. Hurricane Milton(2024-10-10) 당일 GKG 15분 슬롯 중 90분 간격 16개를 직접 받는다
   (`gkg/README.md` §11 실측과 같은 표본).
2. `gkg.lift`로 이슈 술어(`theme=HURRICANE, location=florida`) 기관 lift 랭킹을 낸다.
3. `stock.universe.build_universe()`로 종목 마스터를 실시간으로 받아 정규화 색인을
   만든다(DB 불필요).
4. 별칭 적용 전/후로 `match_ticker`를 돌려 매칭 건수를 비교한다.

## 새 별칭 후보를 찾는 법

`result.txt`의 "여전히 미매칭" 목록(lift 내림차순)을 보고, 실제로 종목 마스터에
있는 회사의 자회사·구 사명·브랜드명인 것만 `gkg/aliases.py`에 추가한다. 짧은
단일 토큰(공용 명사·성씨와 겹치는 것)은 `BLOCKLIST_KEYS`에 넣고 등록하지 않는다.
