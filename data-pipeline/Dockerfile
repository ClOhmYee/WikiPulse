# 파이썬 파이프라인 (producer·live-cycle 등). Python 3.11 고정.
#
# 🔴 PySpark 3.5 는 3.12+ 에서 워커가 죽는다. 3.11 로 못박아 팀원 환경 차이를
# 원천 차단한다 — 이 컨테이너가 그 고정 장치다.
#
# Spark 잡(streaming/edit_windows.py, spike/baseline.py)은 이 이미지가 아니라
# apache/spark 이미지에서 돈다(compose 참고). 여기는 producer·live-cycle·stock
# 같은 일반 파이썬 스크립트용이다.

FROM python:3.11-slim AS base

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
#
#    ⚠️ **같은 누락이 세 번째다.** `spike`(-135) · `stock`(-147) · `cluster`(-149).
#    전부 운영에서 `ModuleNotFoundError` 로 처음 드러났다. 모듈을 새로 만들면
#    **여기에 COPY 를 더하는 것까지가 그 작업이다.**
#
#    cluster 는 `python -m cluster.driver` 로 스냅샷을 만든다(-149). 외부 의존성이
#    없고(표준 라이브러리 + 이미 있는 psycopg) batch·spike 만 쓰므로 base 에 둔다.
COPY producer/ ./producer/
COPY spike/ ./spike/
COPY batch/ ./batch/
COPY cluster/ ./cluster/

# 기본은 EventStreams → Kafka 프로듀서. compose 에서 command 로 바꿀 수 있다.
CMD ["python", "-m", "producer.wiki_edits"]


# --- stock 전용 타깃 (WP-147) ---------------------------------------
#
# 🔴 **`stock/` 도 위 COPY 목록에서 빠져 있었다.** 이 파일 맨 위 주석이 "여기는
#    producer·live-cycle·stock 같은 일반 파이썬 스크립트용" 이라고 적어 뒀는데 정작
#    복사가 없어서 `python -m stock.universe` 가 `ModuleNotFoundError: No module
#    named 'stock'` 로 죽는다 — 2026-09-20 EC2 에서 실제로 그렇게 죽었다.
#    `-135` 의 `spike` 누락과 **같은 유형**이다: 주석은 있는데 COPY 가 없다.
#
# ⚠️ 그런데 base 에 그냥 더할 수 없다. `stock/summaries.py`·`prices.py` 는
#    yfinance 와 pandas 가 필요한데 둘이 100 MB 대이고, producer·live-cycle 은 쓰지
#    않는다. 그래서 **별도 타깃**으로 뺀다 — 상주 서비스 이미지는 그대로 가볍게 둔다.
#
# 쓰는 쪽은 `infra/stock/compose.yaml` 이 `target: stock` 으로 지정한다.
FROM base AS stock

# ⚠️ 버전은 stock/requirements.txt 와 같이 움직여야 한다.
#    yfinance 0.2.51 은 `.history()` 가 깨져 전 종목 0행이 조용히 나온다(README).
RUN pip install --no-cache-dir \
        yfinance==1.7.0 \
        pandas==3.0.5

COPY stock/ ./stock/


# --- 기본 타깃 --------------------------------------------------------------
#
# 🔴 **이 스테이지가 마지막이어야 한다.** `target` 없이 빌드하면 도커는 **마지막
#    스테이지**를 만든다. stock 이 마지막이면 producer·live-cycle 이미지에까지
#    yfinance·pandas 가 딸려 들어간다. 순서를 바꾸지 말 것.
FROM base AS runtime
