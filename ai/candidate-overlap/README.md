# 후보 겹침 재측정 (WP-48)

확정된 이슈 텍스트 규칙(§6.2)·종목 임베딩 규격(§6.1)으로 "임베딩 후보 vs GDELT 후보"
겹침을 다시 잰다. 정답은 `../matching-goldset/cases.py`, 결과·결론은 [RESULT.md](RESULT.md).

프로덕션 코드가 아니라 근거 재현용이다.

## 실행

```bash
py -3 overlap_experiment.py result.txt 10,20,30
```

두 번째 인자는 K 목록. `LLM_GATEWAY_KEY` 환경변수 필요.

- `summaries.json` / `embeddings.json`에 체크포인트한다 — 중간에 죽거나 다시 돌려도
  yfinance·GATEWAY 호출을 반복하지 않는다. K만 바꿔 재실행하면 크레딧 0.
- `sp500.json`은 위키피디아 S&P 500 표 파싱 결과 캐시. 지우면 다시 받는다.

## 주의

- 후보 풀은 S&P 500(502종목)이다. DB의 5,100종목 전수가 아니다 — 사유는 `sp500.py` docstring.
- GDELT는 DOC API ArtList(제목 250건)로 근사한다. "회사=사건 당사자"인 사건(CrowdStrike·IBM)만
  잡히고 "회사는 2차 영향"인 사건(Milton·2023 은행위기)은 제목에 회사명이 안 실려 신호가 죽는다.
  실제 파이프라인은 GKG organization 필드를 쓰므로 이 한계가 없다 — RESULT.md 참고.
- GDELT DOC API는 초당 요청 제한이 빡세다. 사례당 1회로 묶고 실패 시 90초 후 1회 자동 재시도한다.
