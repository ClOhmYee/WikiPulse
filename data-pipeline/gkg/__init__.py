"""GDELT GKG 기관명 lift 집계 → cluster_org_mention 적재 (WP-65).

gdelt/ 가 HDFS 에 쌓은 GKG 원본을 읽어 이슈 기간의 동시 출현 기관명을 뽑고,
lift = P(기관|이슈 기사) / P(기관|전체 기사) 를 계산해 PostgreSQL 의
cluster_org_mention 에 적재한다. 종목 후보 생성(§6.3 b)과 LLM 검증의 RAG
컨텍스트가 이 산출물을 읽는다.

    parse.py   GKG CSV 파싱 (순수) — 조직명·테마·지역 추출
    lift.py    이슈 술어 + lift 집계·랭킹 (순수) — Spark reduce 와 단일프로세스가 공유
    match.py   기관명 → 종목 마스터 ticker 매칭 (순수)
    writer.py  cluster_org_mention 멱등 저장
    driver.py  Spark 배치 배선 + CLI

명세: docs/requirements-v0.3.md §6.2 (b)·§6.3·§11
"""
