# LLM 검증 프롬프트·응답 형식 (WP-45)

이슈-종목 후보(cluster_stock, verified=false)마다 "왜 관련 있는가" LLM이 판정할 때
쓸 프롬프트·입출력 계약이다. 백엔드(Spring, -68)가 이 계약대로 호출부를 만든다.

- 시스템 프롬프트: [prompts/verify_system_v1.txt](prompts/verify_system_v1.txt)
- 출력 JSON 스키마: [schema/verify_response_v1.json](schema/verify_response_v1.json)
- 근거·실측: [RESULT.md](RESULT.md)

프로덕션 코드가 아니라 계약 검증용 실험이다. 실제 구현은 Spring(-68)에서 한다.

## 계약 요약

**호출 단위**: (이슈, 후보 종목 1개) 쌍마다 1회. 배치 호출 안 함 — 명세 §6.3의
비용 모델(이슈당 호출 수 = 등급1+등급2(+조건부 등급3))이 이미 이 전제 위에 있다.

**입력**: 이슈 대표 텍스트(§6.2, 영어) + GDELT 동시출현 컨텍스트(기관명, 있으면) +
후보 종목 이름·티커·사업 설명. 시스템 프롬프트는 고정, 사용자 메시지만 쌍마다 바뀐다.

**출력**: `issue_class`(`SINGLE_COMPANY_EVENT`·`SECTOR_OR_REGION_EVENT`, 판정 전 강제
분류) / `verified`(bool) / `match_path`(4종 enum 또는 null) / `confidence`(strong·weak
또는 null) / `rationale_en`(영어, 감사용) / `rationale_ko`(한국어, 사용자 노출용).
`verified=false`면 `match_path`부터 나머지 전부 null — 억지 연결 방지. `issue_class`는
verified 여부와 무관하게 항상 채운다 — SINGLE_COMPANY_EVENT일 때 "이슈 텍스트에 없는
경쟁사를 배경지식만으로 통과시키는" 오탐을 막는 게이트다(근거: RESULT.md). `confidence`는
DB(`cluster_stock`, -44 확정)에 저장 컬럼이 없다. 필요해지면 -44를 다시 열 것.

**재시도·폐기**: 응답이 JSON 파싱 실패거나 스키마 위반이면 같은 대화에 정정 요청을
1회 추가. 그래도 실패하면 폐기(해당 종목은 verified=false로 남기지 않고 그냥 건너뛴다
— 상태 처리는 별도 이슈 WP-50).

## 실행

```bash
py -3 verify_experiment.py result.txt   # 정답셋(-39) 5쌍 실호출
py -3 test_validate.py                  # 스키마 검증 로직만 오프라인 확인 (LLM_GATEWAY_KEY 불필요)
```

`LLM_GATEWAY_KEY` 환경변수가 필요하다 (`verify_experiment.py`만). 저장소에 넣지 않는다.
