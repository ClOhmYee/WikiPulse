# 결과 (WP-45)

정답셋(-39) 5사례 × 후보 1개씩, 총 5쌍을 GATEWAY 경유 Claude(`claude-sonnet-4-5-20250929`)로
실호출. GDELT 동시출현 컨텍스트는 이번 실험에서 항상 비웠다 — GKG 기관명 추출(-47)이
아직 없어 실제로 채울 게 없다. "컨텍스트 없이 이슈 텍스트·종목 설명만으로 얼마나
잡히는가"가 이 실험이 같이 확인하려던 것이다.

## 오탐 하나 — 프롬프트 두 번 실패 후 구조를 바꿔서 잡음

1차 프롬프트에서 PayPal_buyout_collapse × XYZ(Block, Inc. — 정답셋상 노이즈)가
"Block이 PayPal과 직접 경쟁한다"는 이유만으로 계속 통과됐다.

- **1차 시도**: SUPPLY_CHAIN 정의에 "경쟁 일반은 부족, 이 사건으로 뭐가 달라지는지
  말해야 한다"를 추가 — 안 고쳐짐.
- **2차 시도**: "인수 협상 결렬 사례에서 경쟁사는 자동으로 관련 없다"는 반례를 프롬프트에
  그대로 박음 — 그래도 안 고쳐짐. 모델이 "직접 경쟁"이라는 표현 자체를 이미 "구체적"이라고
  읽고, 반례가 이 사례에 적용된다는 걸 스스로 연결하지 못했다.
- **원인 진단**: 프롬프트가 산문으로 규칙을 나열하는 방식은 모델이 "이 사건이 업계 전체에
  퍼지는 유형인가, 특정 회사 한정 사건인가"를 스스로 구분하게 만들지 못했다. PayPal
  건은 회사 하나에 국한된 사건인데, 모델은 "경쟁사"라는 배경지식만으로 관련성을 만들어냈다
  — 이슈 텍스트에 없는 사실(경쟁 구도)을 일반 지식에서 끌어온 것.
- **3차 — 구조를 바꿈**: 산문 규칙 대신 출력 스키마에 `issue_class`
  (`SINGLE_COMPANY_EVENT` / `SECTOR_OR_REGION_EVENT`) 필드를 강제로 먼저 채우게 하고,
  `SINGLE_COMPANY_EVENT`일 때는 "이슈 텍스트에 이름이 없는 경쟁사는 배경지식만으로
  통과시키지 말 것"을 하드 룰로 못박았다. **한 번에 고쳐짐** — PayPal×XYZ가
  `issue_class=SINGLE_COMPANY_EVENT`로 스스로 분류하고 reject로 바뀜.

**교훈**: 같은 규칙을 문장으로 반복해서 넣는 건 안 먹혔고, 판정 전에 분류를 강제하는
중간 필드를 추가하니 한 번에 풀렸다. 프롬프트 수정이 안 먹힐 때 문장을 더 세게 쓰기보다
출력 구조 자체를 바꾸는 게 나을 수 있다 — 이번 사례로 확인.

## 최종 판정 결과 (issue_class 게이트 적용 후)

| 사례 × 후보 | 기대 | 실제 |
| --- | --- | --- |
| Milton × NEE | verified(strong) | ✅ verified, SECTOR_OR_REGION_EVENT, REGION, strong |
| Milton × MNST | reject | ✅ reject |
| CrowdStrike × MSFT | verified(weak) | ⚠️ verified, SINGLE_COMPANY_EVENT, DIRECT_MENTION, **strong**(기대는 weak) |
| IBM_profit_warning × MU | 불확실(예상: reject) | ✅ reject — GDELT 없이는 근거 못 만듦(예상대로) |
| PayPal_buyout_collapse × XYZ | reject | ✅ reject — issue_class 게이트로 수정 |

5/5 스키마 준수, 5/5 중 4/5 정답셋과 완전 일치. 남은 1건(CrowdStrike×MSFT confidence)은
아래에서 별도로 다룬다 — 판정 자체(verified·match_path)는 정답셋과 같다.

## 발견

1. **GDELT 컨텍스트 없이도 등급1(교집합)급 정답·노이즈는 잘 가른다.** NEE·MNST는
   이슈 텍스트+종목 설명만으로 기대대로 판정됐다.

2. **컨텍스트 없이는 놓치는 정답이 있다 — 예상대로.** IBM×MU는 "CEO가 메모리칩
   지출 전환을 언급했다"는 이슈 본문에 없는 사실이라 거부됐다. 명세 §6.3이 이걸
   "등급2(GDELT 단독)가 필요한 이유"로 이미 짚고 있다 — GDELT 컨텍스트 없이 돌리면
   이 부류는 전량 놓친다는 걸 실측으로 재확인. -46·-47이 이 구멍을 메운다.

3. **`issue_class` 게이트로 "직접 경쟁사" 오탐 해소.** 위 절 참고. SINGLE_COMPANY_EVENT
   유형에서 이슈 텍스트에 안 나온 경쟁사는 배경지식만으로 통과 못 하게 구조적으로 막았다.

4. **CrowdStrike×MSFT의 confidence가 기대(weak)와 다르게 strong으로 나왔다.**
   틀린 판정은 아니다 — MSFT는 실제로 자사 제품(Windows)이 직접 망가진 당사자라
   "strong"도 방어 가능한 해석이다. 정답셋의 "weak" 라벨은 "MSFT 잘못이 아니다"에
   방점이 있고, 프롬프트는 "누구 잘못인가"가 아니라 "제품이 직접 영향받았는가"를
   묻는다 — 둘은 다른 축이라 불일치가 아니라 애초에 확신도의 정의가 안 맞았을
   수 있다. n=1로 결론 내지 않는다. 표본이 늘면(-48류 재측정) 다시 본다. **v1 범위
   밖으로 남긴다** — 판정(verified·match_path) 자체는 정답셋과 일치하고, confidence는
   DB(cluster_stock)에 저장 컬럼도 없어 화면 영향이 없다.

## 이번에 확정한 것

- 입력: (이슈, 후보 1개) 쌍당 1회 호출. 이슈 대표 텍스트(§6.2) + GDELT 컨텍스트(있으면,
  없어도 동작) + 후보 이름·티커·사업 설명.
- 출력: `issue_class`(2종, 판정 전 강제 분류) / `verified` / `match_path`(4종) /
  `confidence`(strong·weak) / `rationale_en` / `rationale_ko`. `verified=false`면
  `match_path`부터 나머지 전부 null. `issue_class`는 verified 여부와 무관하게 항상 채운다.
- SINGLE_COMPANY_EVENT 하드 룰: 이슈 텍스트에 이름이 없는 경쟁사는 "경쟁 관계"라는
  배경지식만으로 통과 금지.
- 재시도: 스키마 위반 시 같은 대화에 정정 요청 1회, 그래도 실패하면 폐기(상태 처리는
  -50에서 정한다). 실측 중 Milton×NEE에서 실제로 1회 발동해 정상 동작 확인.
- 프롬프트: `prompts/verify_system_v1.txt`. 스키마: `schema/verify_response_v1.json`.

## 남은 것 (v1 범위 밖)

- confidence 축이 "누가 원인인가"인지 "누가 영향받는가"인지 — 표본 늘려서 재검토.
- GDELT 컨텍스트를 실제로 채운 상태에서의 재측정 (-47 완료 후).
- `issue_class` 게이트가 SECTOR_OR_REGION_EVENT 쪽에서도 과탐/과소탐을 만드는지는
  이번 표본(사건형 1건)만으로는 못 본다 — Hormuz·은행위기류 추가 표본 필요.
