# stock-text-poc

WP-43 — 종목 임베딩에 넣을 텍스트 규격을 정하기 위한 비교 실험이다.
결과와 결론은 [RESULT.md](RESULT.md), 확정 규칙은 요구사항 명세 §6.1.

## 실행

Python 3.11 필요. `LLM_GATEWAY_KEY` 환경변수 필요 (LLM 게이트웨이 키).

```bash
uv run --python 3.11 --with-requirements requirements.txt --no-project python stock_text_experiment.py result.txt
```

uv가 없으면 venv로:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows는 .venv/Scripts/pip.exe
.venv/bin/python stock_text_experiment.py result.txt
```

## 주의

- 크레딧을 쓴다 (1회 실행 6 크레딧 안팎 — `ai/issue-text-poc`보다 훨씬 저렴하다. LLM 호출이 없다)
- 종목·클러스터·정답 목록은 `ai/issue-text-poc`와 동일한 32종목 표본이다. 정답은 잠정값 — 확정은 WP-39
- 콘솔 출력이 아니라 파일로 쓴다. Windows 콘솔 인코딩 문제를 피하려고 UTF-8로 직접 연다
