# GDELT 컨텍스트 OFF vs ON — 검증 정확도 측정 계획 (WP-68)

> 상태: **계획 확정 · 실행 보류** (2026-09-17). 실 GKG 슬롯 fetch 필요. 실행 판단은 크레딧 상황을 보고 한다. 실행하면 이 문서에
> 결과 표를 채운다.

## 무엇을 재나

LLM 검증(-68)에 **GDELT 동시출현 컨텍스트를 넣는 것**이 판정 정확도를 실제로 올리는지를
정답셋(-39)으로 before/after 측정한다. -45 POC 는 컨텍스트를 항상 비워 돌렸고(당시 -47 미완),
그 결과 **컨텍스트 없이는 놓치는 정답 부류**가 있음을 실측했다(RESULT.md 발견 2번):

- `IBM_profit_warning × MU` — 이슈 본문에 없는 인과("고객이 메모리칩 지출로 이동")라
  이슈 텍스트+종목 설명만으로는 근거를 못 만들어 **reject**. 이 부류(2차 효과)가 타깃이다.

**가설**: GDELT 컨텍스트(상위 기관명)를 채우면 `IBM×MU`류가 reject → verify 로 뒤집힌다.
동시에 노이즈(무관 종목)가 컨텍스트 때문에 verify 로 새지는 않는지(오탐 증가)도 같이 본다.

## 측정 조건 (고정)

| 항목 | 값 |
| --- | --- |
| 정답셋 | `ai/matching-goldset/cases.py` (사건형 3 + 기업형 2, 정답 20 + 노이즈) |
| 모델 | `claude-sonnet-4-5-20250929` (프로덕션 확정 모델, -45) |
| 프롬프트 | `prompts/verify_system_v1.txt` (`prompt_version=v1`, 백엔드와 동일 파일) |
| 이슈 텍스트 | §6.2 확정 규칙 — `build_issue_text`(`verify_experiment.py`와 동일) |
| 변수 | GDELT 컨텍스트 **OFF(`""`)** vs **ON(상위 기관명 lift 내림차순 Top-15)** |
| 호출 단위 | (이슈, 후보 1개) 쌍당 1회 × {OFF, ON} = 쌍당 2회 |

컨텍스트 형식은 백엔드 런타임과 맞춘다: `cluster_org_mention` 상위 기관명을 `, ` 로 이은
문자열(백엔드 `VerificationRepository.topOrgMentions` + `VerificationService` 와 동일).
⚠️ 스키마에 '테마' 컬럼이 없어 **기관명만** 쓴다.

## ON 컨텍스트를 어떻게 만드나 (재사용 지점)

`ai/gkg-alias-poc/measure.py` 의 파이프라인을 그대로 쓴다 — 새로 짜지 않는다:

1. `fetch_zip` + `records_from_zip` — 각 사례 `event_window` 의 GKG 슬롯(90분 간격) 다운로드.
2. `gkg.lift`(`Aggregate` · `IssuePredicate` · `rank`) — 사례별 이슈 술어로 집계 → 기관 lift.
   - 🔴 **여기가 사례별 판단이 드는 유일한 지점**: `IssuePredicate(themes=…, locations=…)` 를
     사례마다 정해야 한다(Milton = `themes=("HURRICANE",), locations=("florida",)` 는 -47 에서
     검증됨). 나머지 4사례 술어는 **실행 시 실 GKG 를 보며 확정**한다 — 오프라인에서 추측으로
     박으면 https://github.com/ClOhmYee/WikiPulse "표본·명세만 보고 단정 금지"에 걸린다. 이 미확정이 실행 보류의 실질 이유다.
3. `gkg.match`(`build_ticker_index` · `merge_aliases` · `match_ticker`) + `gkg.aliases` —
   기관명을 티커로 붙일 필요는 **없다**(컨텍스트는 기관명 문자열 그대로). lift 상위 Top-15
   `org_name` 만 뽑아 컨텍스트로 쓴다.

## 실행 (보류 — 크레딧 확인 후)

```bash
cd ai/llm-verify-poc
# LLM_GATEWAY_KEY 환경변수 필요. 사례별 IssuePredicate 확정 후 measure_context.py 작성해 실행.
py -3 measure_context.py context_result.txt
```

호출 수 개산: 정답셋 쌍 수 × 2(OFF/ON). 노이즈까지 전부 돌리면 ~수십 회 + 사례당 GKG 슬롯
fetch(사건창 길이 × 슬롯). -45 실측 기준 LLM 쌍당 수십 크레딧이라 **총 크레딧은 백 단위**로
예상 — 만료 전 1회 실행이면 충분하다.

## 결과 (실행 후 채움)

| 사례 × 후보 | 기대 | OFF | ON |
| --- | --- | --- | --- |
| IBM_profit_warning × MU | verify(ON에서) | _(미측정)_ | _(미측정)_ |
| … | | | |

판정 규칙·issue_class 게이트·재시도는 백엔드(-68)와 같은 계약(`VerificationResponse.fromJson`)을
쓴다 — 이 측정은 프롬프트·컨텍스트의 효과만 격리해 본다.
