"""Execute the actual ranking query against PostgreSQL, isolated by rollback."""
from pathlib import Path
import re
from conftest import q, x

source = (Path(__file__).parents[2] / 'backend/src/main/java/io/wikipulse/backend/issue/IssueQueryRepository.java').read_text(encoding='utf-8-sig')
SQL = re.search(r'@Query\(value = """(.*?)""", nativeQuery = true\)\s+List<[^;]+findRankings', source, re.S).group(1)
SQL = SQL.replace(':from', '%(from)s').replace(':asOf', '%(asOf)s')

def cluster(conn, key, score, time='2040-09-22T00:00:00Z', source='live', status='CONFIRMED', complete=True):
    if complete:
        x(conn, "INSERT INTO cluster_snapshot(snapshot_ts, source, score_version) VALUES (%s,%s,'v1') ON CONFLICT DO NOTHING", time, source)
    return q(conn, "INSERT INTO issue_cluster(snapshot_ts, source, issue_key, pulse_score, status, label) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id", time, source, key, score, status, key)[0][0]

def rankings(conn):
    with conn.cursor() as cur:
        cur.execute(SQL, {'from': '2040-08-23T00:00:00Z', 'asOf': '2040-09-22T00:00:00Z'})
        return [row[0] for row in cur.fetchall()]

def test_peak_dedup_boundaries_and_completed_snapshots(conn):
    cluster(conn, 'same', 5)
    peak = cluster(conn, 'same', 30, '2040-08-23T00:00:00Z', 'replay')
    other = cluster(conn, 'other', 20)
    cluster(conn, 'too-old', 100, '2040-08-22T23:59:59Z')
    cluster(conn, 'future', 100, '2040-09-22T00:00:01Z')
    cluster(conn, 'discarded', 100, status='DISCARDED')
    cluster(conn, 'incomplete', 100, '2040-09-21T01:00:00Z', complete=False)
    assert rankings(conn) == [peak, other]

def test_top_ten_ties_and_null_keys_do_not_collapse(conn):
    older = cluster(conn, 'tie', 10, '2040-09-21T00:00:00Z')
    newer = cluster(conn, 'tie', 10)
    ids = [cluster(conn, None, 10) for _ in range(12)]
    assert rankings(conn) == [newer, *ids[:9]]
    assert older not in rankings(conn)
