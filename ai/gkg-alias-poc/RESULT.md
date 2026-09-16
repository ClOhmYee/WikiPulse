# 결과 (WP-47)

Hurricane Milton(2024-10-10) 실 GKG 16슬롯(90분 간격, `gkg/README.md` §11과 동일
표본) — 코퍼스 26,910 / 이슈 기사 2,226 / 기관 271건(min_issue_count=3). 종목
마스터는 SEC company_tickers + NASDAQ Trader 실시간 fetch(5,393종목).

## 매칭 건수 — 별칭 전후

| | 매칭 | 비율 |
| --- | --- | --- |
| 별칭 전(정확 일치만) | 16/271 | 5.9% |
| 별칭 후 | 30/271 | 11.1% |

+14건. 전부 실제 GKG 기관명으로 관찰된 문자열이고, 대응 ticker가 종목 마스터에
있는 것만 확인 후 등록했다(추측 없음).

## 별칭 전 매칭(16건) — 오탐 없음 확인

`mosaic company`→MOS, `lee enterprises`→LEE, `duke energy`→DUK,
`baxter international`→BAX, `pearson`→PSO, `united airlines`→UAL,
`super micro computer`→SMCI, `boeing`→BA, `pfizer`→PFE, `goldman sachs`→GS,
`walmart`→WMT, `new york times`→NYT, `delta air lines`→DAL, `nvidia`→NVDA,
`nasdaq`→NDAQ, `microsoft`→MSFT. 육안 확인 결과 전부 정답 — 정확 일치는
이미 안전하다는 걸 재확인.

## 별칭으로 새로 붙은 것 (14건)

| ticker | 원 GKG 기관명 | lift |
| --- | --- | --- |
| NEE | florida power light company | 12.09 |
| NEE | florida power light | 12.09 |
| DUK | duke energy florida | 12.09 |
| DIS | walt disney world resort | 12.09 |
| NWSA | new york post | 9.27 |
| WBD | cnn | 8.32 |
| DIS | disney | 4.27 |
| WBD | cable news network inc | 4.03 |
| WBD | discovery company | 4.03 |
| VZ | verizon | 2.59 |
| META | facebook | 2.50 |
| WBD | warner bros | 1.90 |
| GOOGL | google | 0.77 |
| META | instagram | 0.56 |

FPL·Duke Energy Florida처럼 lift가 높은(사건과 강하게 동시출현) 것도 있고,
Google·Instagram처럼 lift<1(사건과 무관, 배경 잡음)인 것도 있다 — 별칭은
"이 기관이 실존 상장사 자회사/브랜드인가"만 판정하고, 관련성 자체는 lift가
이미 표현하므로 낮은 lift가 섞여도 문제가 아니다(§6.3 다운스트림이 lift로
거른다).

## 짧은 이름 — 오탐 방지가 실제로 걸린 사례

블록리스트(`meta`·`apple`·`delta`·`target`·`block`)는 사전 정의 항목이지만,
이번 실측에서 실제로 발견해 블록리스트에 추가한 게 둘 있다:

- **`dodge`** (이슈 5/코퍼스 12) — Stellantis 브랜드지만, 허리케인 기사에서는
  거의 확실히 "폭풍을 피하다"라는 동사다. 등록했으면 오탐이었을 사례.
- **`mcdonald`** (이슈 3/코퍼스 100, lift 0.36 — 애초에 사건과 무관) — GKG가
  아포스트로피를 지워 "McDonald's"가 "mcdonald"가 되고, 이건 흔한 성씨와도
  겹친다. 근거(관련성)도 약해 등록 안 함.

정확히 명세가 우려한 "짧은 이름 오탐"이 이 표본에서 실제로 나타났고, 블록리스트
정책이 의도대로 걸렀다.

## 등록하지 않은 것 (근거: 실존하지 않거나 확인 불가)

- **`publix`**(9.67) — 비상장(직원 소유). 상장 티커 자체가 없다.
- **`spacex`**(5.71) — 비상장(일론 머스크 개인 소유).
- **`porsche`**(5.26) — 독일 프랑크푸르트 상장, SEC/NASDAQ 종목 마스터 범위 밖.
- **`twitter`**(0.67, X Corp) — 2022년 비상장 전환, 대응 티커 없음.
- 짧고 근거 약한 것(`adm`·`young`·`christie`·`schwartz`·`stern` 등) — 회사와
  성씨/약어가 겹치고 표본 3~5건뿐이라 실측만으로는 판정 불가. 등록 보류.

## 남은 것

- 별칭 15개는 전부 Milton(사건형 1건)에서 나왔다. 기업형 이슈(IBM·PayPal류)나
  다른 사건에서 재실측하면 새 별칭·새 블록리스트 후보가 더 나올 것 — 운영
  중 미매칭 로그를 보고 갱신한다(`aliases.py` 갱신 방법 절).
- `adm`류 근거 약한 후보는 등록도 블록리스트도 안 했다 — 다음 실측에서
  표본이 늘면 다시 본다.
