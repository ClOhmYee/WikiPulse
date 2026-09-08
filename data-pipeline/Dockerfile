# 파이썬 파이프라인 (producer 등). Python 3.11 고정.
#
# 🔴 PySpark 3.5 는 3.12+ 에서 워커가 죽는다. 3.11 로 못박아 팀원 환경 차이를
# 원천 차단한다 — 이 컨테이너가 그 고정 장치다.
#
# Spark 잡(streaming/edit_windows.py, spike/baseline.py)은 이 이미지가 아니라
# apache/spark 이미지에서 돈다(compose 참고). 여기는 producer·stock 같은
# 일반 파이썬 스크립트용이다.
FROM python:3.11-slim

WORKDIR /app

# confluent-kafka 는 librdkafka 네이티브 라이브러리가 필요하다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

# 의존성을 먼저 설치해 레이어 캐시.
COPY producer/ ./producer/
COPY requirements.txt ./
RUN pip install --no-cache-dir confluent-kafka==2.6.1 requests==2.32.3

# 기본은 EventStreams → Kafka 프로듀서. compose 에서 command 로 바꿀 수 있다.
CMD ["python", "-m", "producer.wiki_edits"]
