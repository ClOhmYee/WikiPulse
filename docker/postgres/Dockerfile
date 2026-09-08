# PostgreSQL + pgvector. 스키마는 컨테이너 최초 기동 시 자동 적재된다.
#
# db/migrations 의 SQL 을 /docker-entrypoint-initdb.d 로 복사한다. 이 디렉터리의
# 파일은 데이터 볼륨이 비어 있을 때(최초 1회)만 알파벳 순으로 실행된다.
# 스키마를 고쳤으면 볼륨을 지우고(`docker compose down -v`) 다시 올린다.
#
# pgvector/pgvector 이미지는 vector 확장 바이너리를 들고 있어
# db/migrations/V1 의 CREATE EXTENSION vector 가 그대로 된다.
FROM pgvector/pgvector:pg16

COPY db/migrations/ /docker-entrypoint-initdb.d/
