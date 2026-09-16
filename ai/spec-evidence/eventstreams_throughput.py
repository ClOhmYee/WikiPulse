"""§11 "EventStreams 처리량" 행 재현. EventStreams recentchange 를 N초 표본해
전체·enwiki 이벤트/초와 평균 바이트/건을 낸다.

producer/sse.py 의 SSEClient 를 그대로 쓴다 — 이 스크립트는 표본만 뜨고 Kafka에는
안 쓴다.

실행: CONTACT_EMAIL 환경변수 필요(Wikimedia 정책 — data-pipeline/.env.example 참고).
    py -3 eventstreams_throughput.py [표본초]
"""

import json
import os
import sys
import time

sys.path.insert(0, "../../data-pipeline")
from producer.sse import SSEClient  # noqa: E402


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    contact = os.environ.get("CONTACT_EMAIL", "").strip()
    if not contact:
        raise SystemExit("CONTACT_EMAIL 환경변수가 필요하다 (Wikimedia 정책).")

    client = SSEClient(
        "https://stream.wikimedia.org/v2/stream/recentchange",
        user_agent=f"WikiPulse/0.1 (WikiPulse research; {contact})",
    )

    total = 0
    total_bytes = 0
    by_wiki: dict[str, int] = {}
    start = time.time()

    print(f"{seconds:.0f}초 표본 중...", file=sys.stderr)
    for payload in client.events():
        if time.time() - start >= seconds:
            break
        total += 1
        total_bytes += len(payload.encode("utf-8"))
        try:
            wiki = json.loads(payload).get("wiki", "?")
        except (json.JSONDecodeError, AttributeError):
            wiki = "?"
        by_wiki[wiki] = by_wiki.get(wiki, 0) + 1

    elapsed = time.time() - start
    print(f"\n표본 {elapsed:.1f}초 / 전체 {total}건 ({total / elapsed:.1f} events/s)")
    print(f"평균 {total_bytes / total:.0f} bytes/건" if total else "이벤트 없음")
    print("위키별 events/s (상위 10):")
    for wiki, n in sorted(by_wiki.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {wiki:20} {n:6}건  {n / elapsed:.2f}/s")


if __name__ == "__main__":
    main()
