"""이슈 섹션형 리포트를 만들어 issue_report 에 넣는다 (WP-223).

    python tools/issue_report_generate.py --dsn "$DSN" --cluster 391633 --out report.json
    python tools/issue_report_generate.py --dsn "$DSN" --cluster 391633 --out report.json --write
    python tools/issue_report_generate.py --dsn "$DSN" --cluster 391633 --from-json report.json --write

자동 생성 워커는 아직 없다. 시연 이슈처럼 **몇 개만** 채울 때 쓰는 일회성 도구다.

입력·규칙
    멤버 문서의 그 시점 도입부(`page_intro`, snapshot_ts 이하 마지막 revision), 판정 당시
    수치(`cluster_member.views`·`view_baseline`), 검증 통과 종목(`cluster_stock.verified`),
    기존 요약. 요약 프롬프트(summary_system_v1)와 같은 grounding 규칙이다 — 입력에 없는
    사실·숫자·회사를 쓰지 않고 투자 조언을 하지 않는다.

저장
    `issue_report` 행이 있어야 한다(요약이 먼저). 요약이 없는 이슈는 건너뛴다 —
    summary 가 NOT NULL 이라 리포트만 가진 행을 만들 수 없다.
    report_sections 는 API 모양 그대로 넣는다(evidenceIds 는 멤버 pageId 문자열, 멤버가
    아닌 id 는 버린다).

환경: LLM_GATEWAY_KEY (LLM 을 부를 때만). --from-json 이면 LLM 을 부르지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

MODEL = "claude-sonnet-4-5-20250929"
PROMPT_VERSION = "report_v1"
URL = "https://llm-gateway.example.com/api.anthropic.com/v1/messages"

SYSTEM = """You write a Korean-language issue report for an investment-information service. An "issue" is a topic whose Wikipedia articles showed a human edit followed by a page-view spike at the same time.

INPUT (user message, JSON):
- snapshot_ts: the point in time of this report (UTC).
- short_summary: an existing 1-3 sentence Korean summary of the issue.
- members: the Wikipedia articles grouped into this issue. Each has page_id, title, is_seed, views (views in the spike hour), usual_views (the article's usual views for that hour; null = no history), and intro (the article introduction as of that time; may be null).
- stocks: listed companies that passed an LLM relevance check, with match_path and rationale. May be empty.

GROUNDING RULE:
- Use ONLY the input. Do not add events, results, scores, dates, causes, numbers or company names that are not in the input. General world knowledge is NOT a source of facts. If the intros do not say something (e.g. who won), do not say it.
- Numbers you mention must come from views / usual_views. You may describe a ratio computed from them.
- Never give price predictions, buy/sell language or investment advice.
- If stocks is empty, say plainly that no listed company passed the relevance check. Do not invent any.

OUTPUT: ONLY one JSON object, no code fences:
{"sections": [{"id": "...", "title": "...", "body": "...", "evidence_ids": [page_id, ...]}]}

Sections, in this order (Korean titles):
1. id "overview", title "이슈 개요" — what the issue is, 2-4 sentences.
2. id "documents", title "함께 움직인 문서" — which kinds of articles moved together and why they belong to one issue, 2-4 sentences. Mention a few representative titles.
3. id "signal", title "관측 신호" — how attention changed vs usual, using the numbers, 2-3 sentences.
4. id "stocks", title "관련 종목" — the verified companies and why (from rationale), or that none passed. 1-4 sentences.
evidence_ids lists the page_ids of the member articles each section relies on (0-6 ids, only ids from members). Body text is plain Korean prose; paragraphs may be separated by a blank line.
"""

MEMBERS_SQL = """
SELECT cm.page_id, p.title, cm.is_seed, cm.views, cm.view_baseline,
       (SELECT pi.intro FROM page_intro pi
         WHERE pi.page_id = cm.page_id AND pi.rev_ts <= %s
         ORDER BY pi.rev_ts DESC LIMIT 1)
  FROM cluster_member cm JOIN wiki_page p ON p.id = cm.page_id
 WHERE cm.cluster_id = %s
 ORDER BY cm.is_seed DESC, cm.weight DESC
"""

STOCKS_SQL = """
SELECT cs.ticker, s.name, cs.match_path, cs.rationale
  FROM cluster_stock cs JOIN stock s ON s.ticker = cs.ticker
 WHERE cs.cluster_id = %s AND cs.verified
 ORDER BY cs.ticker
"""

WRITE_SQL = """
UPDATE issue_report
   SET report_sections = %s::jsonb, report_model = %s, report_generated_at = now()
 WHERE cluster_id = %s
"""


def build_input(cur, cid: int) -> dict:
    cur.execute("SELECT snapshot_ts, label FROM issue_cluster WHERE id = %s", (cid,))
    row = cur.fetchone()
    if row is None:
        raise SystemExit(f"cluster {cid} 없음")
    snap, label = row
    cur.execute(MEMBERS_SQL, (snap, cid))
    members = [
        {"page_id": r[0], "title": r[1], "is_seed": r[2], "views": r[3],
         "usual_views": None if r[4] is None else round(float(r[4])),
         "intro": r[5][:1500] if r[5] else None}
        for r in cur.fetchall()]
    cur.execute("SELECT summary FROM issue_report WHERE cluster_id = %s", (cid,))
    summary = cur.fetchone()
    cur.execute(STOCKS_SQL, (cid,))
    stocks = [{"ticker": t, "name": n, "match_path": m, "rationale": r}
              for t, n, m, r in cur.fetchall()]
    return {"snapshot_ts": snap.isoformat(), "label": label,
            "short_summary": summary[0] if summary else None,
            "members": members, "stocks": stocks}


def call_llm(payload: dict) -> tuple[dict, dict | None]:
    import requests  # LLM 을 부를 때만 필요

    resp = requests.post(URL, timeout=180, headers={
        "x-api-key": os.environ["LLM_GATEWAY_KEY"], "anthropic-version": "2023-06-01",
        "content-type": "application/json"}, json={
        "model": MODEL, "max_tokens": 2500, "system": SYSTEM,
        "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]})
    resp.raise_for_status()
    body = resp.json()
    text = "".join(b.get("text", "") for b in body["content"])
    # 코드 펜스·앞뒤 설명이 붙어 와도 첫 '{' ~ 마지막 '}' 만 읽는다 (2026-09-24 실측: 펜스로 옴).
    return json.loads(text[text.index("{"): text.rindex("}") + 1]), body.get("usage")


def to_api_sections(report: dict, member_ids: set[int]) -> list[dict]:
    """LLM 출력 → API 모양. 멤버가 아닌 근거 id 는 버린다."""
    out = []
    for s in report.get("sections", []):
        if not s.get("id") or not s.get("title"):
            continue
        ids = s.get("evidence_ids", s.get("evidenceIds", []))
        out.append({"id": s["id"], "title": s["title"], "body": s.get("body", ""),
                    "evidenceIds": [str(i) for i in ids if int(i) in member_ids]})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="이슈 섹션형 리포트 생성 (WP-223)")
    p.add_argument("--dsn", required=True)
    p.add_argument("--cluster", type=int, required=True)
    p.add_argument("--out", help="생성 결과(입력·출력·사용량)를 남길 JSON 경로")
    p.add_argument("--from-json", help="이미 만든 --out 파일을 다시 쓴다(LLM 호출 없음)")
    p.add_argument("--write", action="store_true", help="issue_report 에 저장한다")
    args = p.parse_args(argv)

    import psycopg

    with psycopg.connect(args.dsn) as con:
        with con.cursor() as cur:
            payload = build_input(cur, args.cluster)
        member_ids = {m["page_id"] for m in payload["members"]}
        if payload["short_summary"] is None:
            print(f"cluster {args.cluster}: 요약(issue_report)이 없어 건너뛴다", file=sys.stderr)
            return 2

        if args.from_json:
            with open(args.from_json, encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("cluster_id") != args.cluster:
                raise SystemExit("--from-json 의 cluster_id 가 다르다")
            report, usage = saved["report"], saved.get("usage")
        else:
            report, usage = call_llm(payload)

        sections = to_api_sections(report, member_ids)
        if not sections:
            print("섹션이 비었다 — 저장하지 않는다", file=sys.stderr)
            return 1
        if args.out and not args.from_json:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"cluster_id": args.cluster, "model": MODEL, "usage": usage,
                           "input": payload, "report": report}, f, ensure_ascii=False, indent=2)

        print(f"cluster {args.cluster}: 멤버 {len(member_ids)} · 종목 "
              f"{[s['ticker'] for s in payload['stocks']]} · usage {usage}")
        for s in sections:
            print(f"\n## {s['title']}  (근거 {len(s['evidenceIds'])})\n{s['body']}")

        if args.write:
            with con.cursor() as cur:
                cur.execute(WRITE_SQL, (json.dumps(sections, ensure_ascii=False),
                                        f"{MODEL} ({PROMPT_VERSION})", args.cluster))
                if cur.rowcount != 1:
                    raise SystemExit(f"issue_report 갱신 {cur.rowcount}행 — 멈춘다")
            con.commit()
            print(f"\n저장: issue_report.report_sections (cluster {args.cluster})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
