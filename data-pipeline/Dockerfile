# 파이썬 파이프라인 (producer·live-cycle 등). Python 3.11 고정.
#
# 🔴 PySpark 3.5 는 3.12+ 에서 워커가 죽는다. 3.11 로 못박아 팀원 환경 차이를
# 원천 차단한다 — 이 컨테이너가 그 고정 장치다.
#
# Spark 잡(streaming/edit_windows.py, spike/baseline.py)은 이 이미지가 아니라
# apache/spark 이미지에서 돈다(compose 참고). 여기는 producer·live-cycle·stock
# 같은 일반 파이썬 스크립트용이다.

FROM python:3.11-slim

WORKDIR /app

# confluent-kafka 는 librdkafka 네이티브 라이브러리가 필요하다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

# 의존성을 먼저 설치해 레이어 캐시. requirements.txt 를 통째로 넣지 않는 이유는
# 거기 pytest(개발용)와 pandas(stock/prices.py 전용, 100 MB 대)가 같이 있어서다.
# ⚠️ 버전은 requirements.txt 와 같이 움직여야 한다 — 한쪽만 올리면 CI 와 컨테이너가
#    다른 버전으로 돈다.
# psycopg 는 live-cycle 이 DB 에 붙는 데 필요하다 (spike/candidate_store.py 등).
RUN pip install --no-cache-dir \
        confluent-kafka==2.6.1 \
        requests==2.32.3 \
        psycopg[binary]==3.3.5

# 🔴 여기 없는 패키지는 컨테이너 안에서 임포트가 안 된다.
#    ~~producer/ 만 복사~~ → spike·batch 를 더한다 (2026-09-20, WP-135).
#    루트 docker-compose.yml 의 live-cycle 서비스가 이 이미지로
#    `python -m spike.live_cycle` 을 부르는데, spike 가 이미지에 없어서
#    `ModuleNotFoundError: No module named 'spike'` 로 죽어 있었다 — 그 서비스는
#    한 번도 뜬 적이 없다. 2026-09-20 에 이미지를 직접 빌드해 확인했다.
#    batch 는 live_cycle 이 시간별 덤프를 받는 데 쓰고(batch.pageview_hourly_ingest),
#    producer 는 canonical_title(§5.1) 때문에 spike 쪽에서 들어온다.
COPY producer/ ./producer/
COPY spike/ ./spike/
COPY batch/ ./batch/

# 기본은 EventStreams → Kafka 프로듀서. compose 에서 command 로 바꿀 수 있다.
CMD ["python", "-m", "producer.wiki_edits"]
