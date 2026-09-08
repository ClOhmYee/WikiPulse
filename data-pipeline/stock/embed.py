"""종목 사업 설명 수집 + 임베딩 (WP-34)

    python -m stock.summaries    # yfinance longBusinessSummary 수집
    python -m stock.embed        # 설명 -> text-embedding-3-small -> pgvector

두 단계를 나눈 이유
    수집(yfinance)은 느리고 잘 끊긴다. 임베딩(GATEWAY)은 크레딧을 쓴다. 한 스크립트로
    묶으면 중간에 죽었을 때 이미 임베딩한 것까지 다시 호출한다. DB 에 단계별로
    저장하고, 각 단계는 "아직 안 한 것"부터 이어서 한다.

GATEWAY
    엔드포인트 https://llm-gateway.example.com/api.openai.com/v1
    키는 LLM_GATEWAY_API_KEY 환경변수. 저장소에 넣지 않는다.
    502건 임베딩에 크레딧 100 남짓 들었다 (2026-09-07 실측).
"""

from __future__ import annotations

import os
import sys
import time

import psycopg
import requests

from . import db

GATEWAY_BASE = os.environ.get("LLM_GATEWAY_BASE_URL", "https://llm-gateway.example.com/api.openai.com/v1")
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536  # db/migrations/V1 의 vector(1536) 과 맞아야 한다
BATCH = 100  # OpenAI 임베딩은 한 요청에 여러 입력을 받는다


def _gateway_key() -> str:
    key = os.environ.get("LLM_GATEWAY_API_KEY")
    if not key:
        raise SystemExit("LLM_GATEWAY_API_KEY 가 필요하다. .env 참고.")
    return key


def embed_batch(texts: list[str]) -> list[list[float]]:
    resp = requests.post(
        f"{GATEWAY_BASE}/embeddings",
        headers={"Authorization": f"Bearer {_gateway_key()}"},
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    vectors = [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]
    for v in vectors:
        if len(v) != EMBED_DIM:
            raise RuntimeError(
                f"임베딩 차원이 {len(v)}다. 스키마는 {EMBED_DIM} — "
                "모델이 바뀌었거나 GATEWAY 설정이 다르다."
            )
    return vectors


def run() -> int:
    with psycopg.connect(db.dsn()) as conn:
        pending = db.tickers_missing_embedding(conn)
        if not pending:
            print("임베딩할 종목이 없다. 설명 수집(summaries)을 먼저 돌렸는가?", file=sys.stderr)
            return 0

        print(f"임베딩 대상 {len(pending)}종목", file=sys.stderr)
        done = 0
        for start in range(0, len(pending), BATCH):
            chunk = pending[start : start + BATCH]
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ticker, business_summary FROM stock WHERE ticker = ANY(%s)",
                    (chunk,),
                )
                rows = cur.fetchall()

            vectors = embed_batch([summary for _, summary in rows])
            db.save_embeddings(
                conn, [(ticker, vec) for (ticker, _), vec in zip(rows, vectors)]
            )
            done += len(rows)
            print(f"  {done}/{len(pending)}", file=sys.stderr)
            time.sleep(0.2)  # GATEWAY 를 몰아치지 않는다

    print(f"임베딩 완료: {done}종목", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
