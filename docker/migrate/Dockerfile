FROM python:3.11-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.3.5"
WORKDIR /db
ENTRYPOINT ["python", "/db/migrate_local.py"]
