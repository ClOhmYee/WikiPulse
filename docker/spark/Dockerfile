# Spark 실행 이미지 — 파이썬 3.11 고정 (WP-136).
#
# 왜 공식 이미지를 안 쓰나
#   `apache/spark:3.5.3-python3` 의 파이썬은 **3.8.10** 이다 (Ubuntu 20.04 focal,
#   2026-09-18 `docker run` 재확인). 저장소가 못박은 `psycopg 3.3.5` 는 3.9+ 를
#   요구해서 안 깔리고, 그래서 LIVE 스트리밍의 `SINK=spike` 경로가 실행되지 않았다.
#   🔴 그동안 LIVE 입구가 막혀 있던 원인이 이 한 줄이다.
#
#   focal 저장소에는 3.11 이 없어서 공식 이미지에 얹으려면 외부 PPA(deadsnakes)가
#   붙는다. 그럴 바에는 파이썬을 바닥으로 깔고 Spark 를 pip 로 올린다 —
#   파이썬·pyspark·psycopg 버전이 전부 이 파일 한 곳에서 고정된다.
#
# ⚠️ **드라이버와 워커는 같은 파이썬이어야 한다.** 버전이 갈리면 파이썬 워커가 뜨는
#    순간 executor 가 죽는다 (CLAUDE.md 인프라 절). EC2 Master·Worker 도 이 이미지로
#    같이 바꿔야 한다 — 절차는 `docker/README.md` 참고.
#    지금 스트리밍 잡에 파이썬 UDF 가 없어서 워커가 안 뜨지만, 그게 앞으로도 그렇다는
#    보장은 아니다. "지금은 안 터진다" 를 계약으로 삼지 않는다.
FROM python:3.11-slim-bookworm

# Spark 는 JVM 위에서 돈다. JRE 만 있으면 되고 JDK 는 필요 없다.
# procps 는 spark-submit 이 쓰는 `ps` 를 준다 — 없으면 기동 중 경고가 뜬다.
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        procps \
    && rm -rf /var/lib/apt/lists/*

# 🔴 버전은 전부 고정한다. pyspark 3.5.3 은 EC2 클러스터(WP-27)와 같은 판이고,
#    psycopg 3.3.5 는 data-pipeline/requirements.txt 와 같은 값이다 —
#    파이프라인 안에 드라이버가 두 벌이 되면 안 된다.
RUN pip install --no-cache-dir \
        pyspark==3.5.3 \
        "psycopg[binary]==3.3.5" \
        requests==2.32.3

# pip 로 깐 Spark 의 위치. spark-submit·jars 가 여기 있다.
ENV SPARK_HOME=/usr/local/lib/python3.11/site-packages/pyspark
ENV PATH="${SPARK_HOME}/bin:${PATH}"
# 드라이버와 워커가 같은 인터프리터를 쓰게 못박는다 (위 ⚠️).
ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3

WORKDIR /opt/app

# 잡 코드는 compose 가 마운트한다 — 이미지를 다시 굽지 않고 고칠 수 있게.
CMD ["spark-submit", "--version"]
