# LLM 검증 비용 실측 — 배치·모델 (WP-170)

검증이 LLM 비용의 90% 다. 후보 하나당 1회 호출이라 이슈 하나에 10~28회가 든다. 줄일
수단 두 가지(**후보 배치** · **모델 다운그레이드**)를 같은 입력으로 재고 고른다.

- 결과·근거: [RESULT.md](RESULT.md)
- 배치 시스템 프롬프트: [prompts/verify_batch_system_v2.txt](prompts/verify_batch_system_v2.txt)
- 단건 프롬프트는 **프로덕션과 같은 것**을 읽는다 — `ai/llm-verify-poc/prompts/verify_system_v1.txt`

> 🔴 프로덕션 코드가 아니다. 실제 구현은 백엔드(-68, `matching/LlmVerifier`)에 있다.
> 이 폴더는 계약 검증용 실험이다.

**결론: `gpt-5.4-nano` 단건 채택** — Sonnet 단건 대비 9.8배 싸고, 정답 일치 동률 이상,
오탐 0, 순서 민감도 없음. 자세한 수치와 한계는 RESULT.md.

## 쓰는 법

```bash
# 오프라인 — 문자 수 회계만. GATEWAY 키·크레딧 불필요
python ai/llm-verify-batch-poc/measure.py --case Milton

# 실호출 — 🔴 팀 크레딧을 쓴다
python ai/llm-verify-batch-poc/measure.py --case Milton --live --model gpt-5.4-nano
```

| 옵션 | 뜻 |
| --- | --- |
| `--case` | `ai/matching-goldset/cases.py` 의 사례 (Milton·CrowdStrike·PayPal_buyout_collapse·IBM_profit_warning·BankingCrisis2023) |
| `--model` | `claude-*` 면 Anthropic 경로, 그 외면 OpenAI 경로 |
| `--gdelt` | GDELT 기관명 컨텍스트. 비우면 `(none available)` |
| `--batch-only` | 단건 생략 |
| `--reverse` | 후보 순서 뒤집기 (순서 민감도) |
| `--limit` | 후보 수 상한 |

`LLM_GATEWAY_KEY` 는 저장소 루트 `.env` 에서 읽는다(환경변수가 있으면 그쪽 우선).

## 함정 (실제로 물린 것)

- ⚠️ **소액 호출은 크레딧 델타가 0 으로 찍힌다.** 정수 반올림이라 단가 역산이 안 된다.
  충분히 큰 페이로드로 재야 한다.
- ⚠️ **출력이 입력보다 5배 비싸다**(Sonnet 0.15 vs 0.03). 배치가 입력을 76% 줄여도
  출력은 후보 수만큼 그대로라 크레딧 절감은 61% 에 그친다. **호출 수로 비용을 추정하면
  틀린다.**
- ⚠️ **nano 계열은 추론 토큰을 먼저 먹는다.** `max_completion_tokens` 가 모자라면 본문이
  빈 문자열로 온다 — 에러가 아니라서 조용히 실패한다.
- ⚠️ **Anthropic 과 OpenAI 의 API 모양이 다르다.** `system` 위치도 `usage` 키 이름도
  다르다. 한쪽 모양으로 다른 쪽을 부르면 빈 응답이 온다.
- 🔴 **실호출 결과는 파일로 남긴다.** 2026-09-21 에 배치 단독 실행에서 판정을 화면에
  출력하지 않아 524 크레딧을 쓰고 결과를 못 봤다. 지금은 `result-*.json` 에 쓴다.
- ⚠️ **입력 재료는 캐시한다**(`cache.json`). 매 실행마다 위키·yfinance 를 다시 부르면
  같은 입력이 아니게 되고, WP-164 수집과 `api.php` 예산이 겹쳐 429 를 맞는다.

## 생성물

- `result-*.json` — **커밋한다.** 실호출 판정 원본이라 크레딧을 주고 얻은 증거다.
  RESULT.md 의 수치를 다시 세어볼 수 있는 유일한 근거고, 지우면 같은 돈을 다시 낸다.
- `cache.json` — gitignore. 위키·yfinance 응답 캐시라 언제든 다시 받을 수 있다.
