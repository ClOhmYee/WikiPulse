# 이슈 대표 텍스트 규칙 비교 (WP-42)

급증 문서 클러스터를 임베딩·LLM 입력용 한 덩이 텍스트로 만드는 방식을 비교한
실험이다. 결과와 결론은 [RESULT.md](RESULT.md), 확정 규칙은 요구사항 명세 §6.2.

프로덕션 코드가 아니라 근거 재현용이다.

## 실행

파이썬 **3.11** 기준이다.

```bash
# uv를 쓰는 경우 (가상환경 없이 바로)
uv run --python 3.11 --with-requirements requirements.txt --no-project \
    python issue_text_experiment.py result.txt

# venv를 쓰는 경우
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python issue_text_experiment.py result.txt
```

`LLM_GATEWAY_KEY` 환경변수가 필요하다 (LLM 게이트웨이 키). 저장소에 넣지 않는다.

한 번 돌리면 임베딩 약 45건 + LLM 3건, 크레딧 70~75가 든다.

## 주의

- 출력은 UTF-8 파일로 쓴다. Windows 콘솔로 바로 뿌리면 한글이 깨진다.
- 정답 종목 목록은 잠정값이다. 확정은 WikiPulse-39에서 한다.
