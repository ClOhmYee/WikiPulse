"""시점별 클러스터·문서 그래프 생산 (WP-75).

버블맵(WP-74 조회 API)이 한 스냅샷을 통째로 그리도록, 급증 문서를
이슈 클러스터로 묶고 문서 쌍 간선·시점별 지표를 생산해 PostgreSQL 에 저장한다.

순수 로직(snapshot.py·score.py)은 Spark·DB 없이 테스트된다. writer.py 가
psycopg 로 저장하고, driver.py 가 실 데이터 소스를 배선하는 골격이다.
"""
