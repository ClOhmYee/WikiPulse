# LIVE Pipeline Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a restart-safe Wikipedia EventStreams → Kafka → two-node Spark edit-window pipeline on the data EC2 without touching the serving stack or writing to PostgreSQL.

**Architecture:** A Python 3.11 producer synchronously confirms each selected event with Kafka before atomically advancing an SSE cursor file. A standalone Spark driver reads `wiki.edits`, removes replay duplicates by `meta_id`, aggregates edit windows on the existing two-worker cluster, and keeps its checkpoint in replicated HDFS. The two new processes live in an isolated Compose project under `/home/deploy/infra/pipeline`.

**Tech Stack:** Python 3.11, pytest, confluent-kafka 2.6.1, requests 2.32.3, Spark Structured Streaming 3.5.3, Kafka 3.9.0, HDFS 3.5.0, Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-18-live-pipeline-phase1-design.md`

> **경로 변경 (2026-09-19):** 이 계획서가 `deploy/live-pipeline/`으로 적은 배포 파일은
> develop 통합 후 `infra/pipeline/`으로 옮겼다. EC2 compose 정본을 `infra/*`에 둔다는
> WP-133 규칙을 따른 것이며, 서버 경로 `/home/deploy/infra/pipeline`은 그대로다.

## Global Constraints

- Deploy only to the data EC2 `data.example.com`; do not alter Spring Boot, PostgreSQL, Nginx, or frontend files on the service EC2.
- Do not change or restart the existing Kafka, Spark Master/Workers, HDFS NameNode/DataNodes, their Compose files, or UFW rules.
- Use Kafka topic `wiki.edits`, one partition, replication factor 1, and retention `604800000 ms`; never delete or recreate an existing topic.
- Use HDFS checkpoint `/wikipulse/checkpoints/edit-windows-v1`; never delete it without a separate approval.
- Keep `SINK=console`; no PostgreSQL writes are allowed in this phase.
- Keep the Spark application at or below 2 total cores and 1 GiB per executor; keep the producer at or below 0.25 CPU and 256 MiB.
- Keep `.env`, `CONTACT_EMAIL`, and cursor state out of Git and command output.
- Stop before the next step if an existing infrastructure container becomes unhealthy, free memory stays below 2 GiB, root disk reaches 80%, or Kafka/Spark makes no progress for five minutes.
- Commit implementation locally only while the Jira issue key cannot be verified; do not push a branch with a guessed issue key.

---

### Task 1: Durable SSE cursor and frame identity

**Files:**
- Create: `data-pipeline/producer/cursor.py`
- Modify: `data-pipeline/producer/config.py`
- Modify: `data-pipeline/producer/sse.py`
- Create: `data-pipeline/tests/test_cursor.py`
- Create: `data-pipeline/tests/test_sse.py`

**Interfaces:**
- Produces: `CursorStore(path: str | None)`, `CursorStore.load() -> str | None`, and `CursorStore.save(event_id: str) -> None`.
- Produces: immutable `SSEEvent(data: str, event_id: str | None)` values from `SSEClient.events()`.
- Produces: `Config.cursor_file: str | None`, loaded from `SSE_CURSOR_FILE`.
- Consumed by: Task 2 producer acknowledgement flow.

- [ ] **Step 1: Write cursor persistence tests**

```python
# data-pipeline/tests/test_cursor.py
import json

import pytest

from producer.cursor import CursorStore


def test_missing_cursor_returns_none(tmp_path):
    assert CursorStore(tmp_path / "cursor.json").load() is None


def test_cursor_round_trip_uses_versioned_json(tmp_path):
    path = tmp_path / "cursor.json"
    store = CursorStore(path)
    store.save('[{"topic":"eqiad","offset":7}]')
    assert store.load() == '[{"topic":"eqiad","offset":7}]'
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": 1,
        "event_id": '[{"topic":"eqiad","offset":7}]',
    }


def test_invalid_cursor_fails_closed(tmp_path):
    path = tmp_path / "cursor.json"
    path.write_text('{"version":2,"event_id":"x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="cursor"):
        CursorStore(path).load()


def test_disabled_cursor_is_a_noop():
    store = CursorStore(None)
    store.save("event-1")
    assert store.load() is None
```

- [ ] **Step 2: Run the cursor tests and confirm the missing module failure**

Run: `python -m pytest data-pipeline/tests/test_cursor.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'producer.cursor'`.

- [ ] **Step 3: Implement the smallest atomic cursor store**

```python
# data-pipeline/producer/cursor.py
from __future__ import annotations

import json
import os
from pathlib import Path


class CursorStore:
    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path else None

    def load(self) -> str | None:
        if self.path is None or not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cursor 파일을 읽을 수 없다: {self.path}") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or not isinstance(payload.get("event_id"), str)
            or not payload["event_id"]
        ):
            raise ValueError(f"cursor 파일 형식이 잘못됐다: {self.path}")
        return payload["event_id"]

    def save(self, event_id: str) -> None:
        if self.path is None:
            return
        if not event_id:
            raise ValueError("빈 SSE event id는 저장할 수 없다")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump({"version": 1, "event_id": event_id}, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
```

- [ ] **Step 4: Write SSE frame tests before changing the parser**

```python
# data-pipeline/tests/test_sse.py
from producer.sse import SSEClient, SSEEvent


class Response:
    def iter_lines(self, decode_unicode=True):
        return iter(["id: event-7", 'data: {"wiki":"enwiki"}', ""])


def test_parser_returns_payload_with_event_id():
    client = SSEClient("https://example.invalid", user_agent="test")
    events = client._parse_frames(Response())
    assert next(events) == SSEEvent('{"wiki":"enwiki"}', "event-7")


def test_last_event_id_moves_only_after_caller_finishes_event():
    client = SSEClient("https://example.invalid", user_agent="test")
    events = client._parse_frames(Response())
    next(events)
    assert client.last_event_id is None
    list(events)
    assert client.last_event_id == "event-7"


def test_initial_cursor_is_sent_as_last_event_id_header():
    client = SSEClient(
        "https://example.invalid",
        user_agent="test",
        last_event_id="event-6",
    )
    assert client._headers()["Last-Event-ID"] == "event-6"
```

- [ ] **Step 5: Change the parser and configuration with no additional dependency**

Add this value type and constructor parameter in `producer/sse.py`, then yield `SSEEvent(payload, pending_id)` while preserving the existing post-yield cursor advance:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class SSEEvent:
    data: str
    event_id: str | None


def __init__(..., last_event_id: str | None = None) -> None:
    ...
    self.last_event_id = last_event_id
```

Add to `Config` and `Config.from_env()`:

```python
cursor_file: str | None

cursor_raw = _env("SSE_CURSOR_FILE", "").strip()
cursor_file=cursor_raw or None,
```

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest data-pipeline/tests/test_cursor.py data-pipeline/tests/test_sse.py data-pipeline/tests/test_normalize.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit the isolated cursor primitive**

```bash
git add data-pipeline/producer/cursor.py data-pipeline/producer/config.py data-pipeline/producer/sse.py data-pipeline/tests/test_cursor.py data-pipeline/tests/test_sse.py
git commit -m "feat: persist EventStreams cursor atomically"
```

### Task 2: Advance the cursor only after Kafka acknowledgement

**Files:**
- Modify: `data-pipeline/producer/wiki_edits.py`
- Create: `data-pipeline/tests/test_wiki_edits.py`

**Interfaces:**
- Consumes: `CursorStore` and `SSEEvent` from Task 1.
- Produces: `publish_and_checkpoint(producer, *, topic: str, key: bytes, value: bytes, event_id: str, cursor: CursorStore) -> None`.
- Guarantee: a delivery error or flush timeout never advances the persisted SSE cursor.

- [ ] **Step 1: Write acknowledgement ordering tests**

```python
# data-pipeline/tests/test_wiki_edits.py
import pytest

from producer.cursor import CursorStore
from producer.wiki_edits import publish_and_checkpoint


class FakeProducer:
    def __init__(self, error=None, remaining=0):
        self.error = error
        self.remaining = remaining
        self.callback = None

    def produce(self, topic, key, value, on_delivery):
        self.callback = on_delivery

    def flush(self, timeout):
        if self.callback is not None:
            self.callback(self.error, object())
        return self.remaining


def test_acknowledged_event_advances_cursor(tmp_path):
    path = tmp_path / "cursor.json"
    publish_and_checkpoint(
        FakeProducer(), topic="wiki.edits", key=b"k", value=b"v",
        event_id="event-7", cursor=CursorStore(path),
    )
    assert CursorStore(path).load() == "event-7"


@pytest.mark.parametrize(
    "producer",
    [FakeProducer(error=RuntimeError("delivery failed")), FakeProducer(remaining=1)],
)
def test_failed_delivery_does_not_advance_cursor(tmp_path, producer):
    path = tmp_path / "cursor.json"
    with pytest.raises(RuntimeError):
        publish_and_checkpoint(
            producer, topic="wiki.edits", key=b"k", value=b"v",
            event_id="event-7", cursor=CursorStore(path),
        )
    assert not path.exists()
```

- [ ] **Step 2: Run the focused test and confirm the missing function failure**

Run: `python -m pytest data-pipeline/tests/test_wiki_edits.py -q`

Expected: import fails because `publish_and_checkpoint` does not exist.

- [ ] **Step 3: Implement synchronous acknowledgement at the existing 2 events/s scale**

```python
def publish_and_checkpoint(
    producer: Producer,
    *,
    topic: str,
    key: bytes,
    value: bytes,
    event_id: str,
    cursor: CursorStore,
) -> None:
    delivery_errors: list[object] = []

    def delivered(err: object | None, _message: object) -> None:
        if err is not None:
            delivery_errors.append(err)

    producer.produce(topic, key=key, value=value, on_delivery=delivered)
    remaining = producer.flush(10)
    if delivery_errors:
        raise RuntimeError(f"Kafka delivery failed: {delivery_errors[0]}")
    if remaining:
        raise RuntimeError(f"Kafka acknowledgement timeout: {remaining} pending")
    cursor.save(event_id)
```

In `main()`, load the cursor before constructing `SSEClient`, consume `frame.data`, require `frame.event_id` for an event selected for publication, and call `publish_and_checkpoint`. Preserve skip and malformed counters. Remove the old asynchronous `_on_delivery` path so there is only one delivery policy.

- [ ] **Step 4: Run producer tests**

Run: `python -m pytest data-pipeline/tests/test_cursor.py data-pipeline/tests/test_sse.py data-pipeline/tests/test_wiki_edits.py data-pipeline/tests/test_normalize.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the acknowledgement boundary**

```bash
git add data-pipeline/producer/wiki_edits.py data-pipeline/tests/test_wiki_edits.py
git commit -m "feat: checkpoint SSE cursor after Kafka acknowledgement"
```

### Task 3: Remove replay duplicates before Spark aggregation

**Files:**
- Modify: `data-pipeline/streaming/edit_windows.py`
- Modify: `data-pipeline/tests/test_edit_windows.py`

**Interfaces:**
- Produces: `prepare_live_events(raw: DataFrame, *, watermark: str) -> DataFrame`.
- Consumes: Kafka DataFrame with a binary/string `value` column containing `EDIT_EVENT_SCHEMA` JSON.
- Guarantee: null 또는 공백뿐인 `meta_id` 행은 제외하며, 반복된 유효 `meta_id`는 한 번만 센다.

- [ ] **Step 1: Add batch-testable contract tests**

```python
from streaming.edit_windows import prepare_live_events


def test_live_preparation_removes_duplicate_meta_id(spark):
    duplicate = event(meta={"id": "same-id"})
    raw = spark.createDataFrame([(duplicate,), (duplicate,)], "value string")
    assert prepare_live_events(raw, watermark="10 minutes").count() == 1


@pytest.mark.parametrize("meta_id", [None, "", " \\t"])
def test_live_preparation_rejects_missing_or_blank_meta_id(spark, meta_id):
    payload = json.loads(event())
    payload["meta_id"] = meta_id
    payload = json.dumps(payload)
    raw = spark.createDataFrame([(payload,)], "value string")
    assert prepare_live_events(raw, watermark="10 minutes").count() == 0
```

- [ ] **Step 2: Run the tests and confirm the missing function failure**

Run: `python -m pytest data-pipeline/tests/test_edit_windows.py -q`

Expected: import fails because `prepare_live_events` does not exist.

- [ ] **Step 3: Implement one preparation boundary and reuse it in `build_stream`**

```python
def prepare_live_events(raw: DataFrame, *, watermark: str) -> DataFrame:
    events = (
        raw.select(F.from_json(F.col("value").cast("string"), EDIT_EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_ts", F.to_timestamp("event_ts"))
        .filter(F.col("meta_id").isNotNull() & F.col("meta_id").rlike(r"\S"))
    )
    if events.isStreaming:
        return (
            events.withWatermark("event_ts", watermark)
            .dropDuplicatesWithinWatermark(["meta_id"])
        )
    return events.dropDuplicates(["meta_id"])
```

Replace the duplicated parse block in `build_stream()` with:

```python
events = prepare_live_events(raw, watermark=env("WATERMARK", DEFAULT_WATERMARK))
```

Keep `aggregate_edit_windows()` unchanged so historical batch parity semantics do not change.

- [ ] **Step 4: Run focused and parity tests**

Run: `python -m pytest data-pipeline/tests/test_edit_windows.py data-pipeline/tests/test_stream_batch_parity.py -q`

Expected: all tests pass or only the repository's pre-existing environment-dependent Spark skips occur; no failure is allowed.

- [ ] **Step 5: Commit the deduplication boundary**

```bash
git add data-pipeline/streaming/edit_windows.py data-pipeline/tests/test_edit_windows.py
git commit -m "fix: deduplicate replayed live edits before aggregation"
```

### Task 4: Add an isolated EC2 Compose definition

**Files:**
- Create: `deploy/live-pipeline/compose.yaml`
- Create: `deploy/live-pipeline/.env.example`
- Create: `deploy/live-pipeline/README.md`
- Modify: `data-pipeline/.env.example`
- Modify: `data-pipeline/README.md`

**Interfaces:**
- Consumes: repository `data-pipeline` directory as `PIPELINE_APP_DIR`.
- Consumes: existing Spark and Hadoop configuration from `SPARK_INFRA_DIR`.
- Produces: Compose services `producer` and `edit-stream`; neither publishes a host port.

- [ ] **Step 1: Write the Compose file with hard resource and logging bounds**

```yaml
name: wikipulse-pipeline

x-logging: &bounded-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"

services:
  producer:
    build:
      context: ${PIPELINE_APP_DIR:-../../data-pipeline}
    container_name: wikipulse-producer
    network_mode: host
    init: true
    restart: ${RESTART_POLICY:-no}
    cpus: 0.25
    mem_limit: 256m
    environment:
      CONTACT_EMAIL: ${CONTACT_EMAIL:?Set CONTACT_EMAIL in .env}
      KAFKA_BOOTSTRAP_SERVERS: ${KAFKA_BOOTSTRAP_SERVERS:-192.0.2.10:9092}
      KAFKA_TOPIC: wiki.edits
      WIKIS: enwiki
      LOG_EVERY_SECONDS: "30"
      SSE_CURSOR_FILE: /var/lib/wikipulse-producer/last-event-id
    volumes:
      - ${PIPELINE_STATE_DIR:-./state}:/var/lib/wikipulse-producer
    logging: *bounded-logging

  edit-stream:
    image: apache/spark:3.5.3-python3
    container_name: wikipulse-edit-stream
    network_mode: host
    init: true
    restart: ${RESTART_POLICY:-no}
    mem_limit: 1536m
    environment:
      SPARK_LOCAL_IP: ${DATA_SERVER_IP:-192.0.2.10}
      SPARK_CONF_DIR: /opt/spark/conf
      HADOOP_CONF_DIR: /opt/hadoop-conf
      PYSPARK_PYTHON: python3
      PYSPARK_DRIVER_PYTHON: python3
      KAFKA_BOOTSTRAP_SERVERS: ${KAFKA_BOOTSTRAP_SERVERS:-192.0.2.10:9092}
      KAFKA_TOPIC: wiki.edits
      STARTING_OFFSETS: earliest
      MAX_OFFSETS_PER_TRIGGER: "50000"
      WINDOW_SIZE: 1 hour
      SLIDE_SIZE: 5 minutes
      WATERMARK: 10 minutes
      TRIGGER_INTERVAL: 30 seconds
      SHUFFLE_PARTITIONS: "8"
      CHECKPOINT_DIR: hdfs://192.0.2.10:8020/wikipulse/checkpoints/edit-windows-v1
      SINK: console
    volumes:
      - ${SPARK_INFRA_DIR:-/home/deploy/infra/spark}/conf:/opt/spark/conf:ro
      - ${SPARK_INFRA_DIR:-/home/deploy/infra/spark}/hadoop-conf:/opt/hadoop-conf:ro
      - ${PIPELINE_APP_DIR:-../../data-pipeline}/streaming:/opt/app/streaming:ro
      - ${PIPELINE_IVY_DIR:-./ivy}:/tmp/ivy
    working_dir: /opt/app
    entrypoint: ["/opt/spark/bin/spark-submit"]
    command:
      - --master
      - ${SPARK_MASTER:-spark://192.0.2.10:7077}
      - --packages
      - org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.3
      - --conf
      - spark.cores.max=2
      - --conf
      - spark.executor.cores=1
      - --conf
      - spark.executor.memory=1g
      - --conf
      - spark.jars.ivy=/tmp/ivy
      - /opt/app/streaming/edit_windows.py
    logging: *bounded-logging
```

- [ ] **Step 2: Add a non-secret environment template**

```dotenv
# deploy/live-pipeline/.env.example
CONTACT_EMAIL=operator@example.com
PIPELINE_APP_DIR=../../data-pipeline
PIPELINE_STATE_DIR=./state
PIPELINE_IVY_DIR=./ivy
RESTART_POLICY=no
SPARK_INFRA_DIR=/home/deploy/infra/spark
DATA_SERVER_IP=192.0.2.10
SPARK_MASTER=spark://192.0.2.10:7077
KAFKA_BOOTSTRAP_SERVERS=192.0.2.10:9092
```

- [ ] **Step 3: Document exact preflight, start, observe, stop, and recovery commands**

`deploy/live-pipeline/README.md` must state that production `.env` is mode `0600`, topic/checkpoint deletion is prohibited, `producer` starts before `edit-stream`, and only these two services may be stopped during rollback. Keep `RESTART_POLICY=no` throughout canary validation; only after every canary gate passes, change it to `unless-stopped` and apply the policy to `producer` first, then `edit-stream`. Include these commands:

```bash
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env up -d --build producer
sudo docker compose --env-file .env logs --since 3m producer
sudo docker compose --env-file .env up -d edit-stream
sudo docker compose --env-file .env logs --since 5m edit-stream
sudo docker compose --env-file .env stop edit-stream producer
```

- [ ] **Step 4: Document `SSE_CURSOR_FILE` in pipeline examples**

Add `SSE_CURSOR_FILE=` to `data-pipeline/.env.example` with a comment that empty preserves local ephemeral behavior. Update `data-pipeline/README.md` to explain acknowledgement-before-cursor and HDFS production checkpoints.

- [ ] **Step 5: Validate Compose interpolation without starting a container**

Run:

```bash
docker compose \
  -f deploy/live-pipeline/compose.yaml \
  --env-file deploy/live-pipeline/.env.example \
  config --quiet
```

Expected: exit code 0 and no output.

- [ ] **Step 6: Commit deployment configuration**

```bash
git add deploy/live-pipeline data-pipeline/.env.example data-pipeline/README.md
git commit -m "ops: define isolated LIVE pipeline deployment"
```

### Task 5: Run the local release gate

**Files:**
- Modify only if a test exposes a defect in Tasks 1–4.

**Interfaces:**
- Consumes: all code and configuration from Tasks 1–4.
- Produces: one exact Git commit and a passing local evidence set suitable for EC2 packaging.

- [ ] **Step 1: Run all directly affected tests**

Run:

```bash
python -m pytest \
  data-pipeline/tests/test_cursor.py \
  data-pipeline/tests/test_sse.py \
  data-pipeline/tests/test_wiki_edits.py \
  data-pipeline/tests/test_normalize.py \
  data-pipeline/tests/test_edit_windows.py \
  data-pipeline/tests/test_stream_batch_parity.py -q
```

Expected: no failures. Record skips separately; do not describe a skipped integration as passed.

- [ ] **Step 2: Run the broader Python regression suite**

Run: `python -m pytest data-pipeline -q`

Expected: no failures. Existing external-service skips are acceptable only when their reason is printed and recorded.

- [ ] **Step 3: Build the exact producer image locally**

Run: `docker build -t wikipulse-producer:phase1 data-pipeline`

Expected: build succeeds using Python 3.11 and confluent-kafka 2.6.1.

- [ ] **Step 4: Revalidate Compose and inspect the rendered service boundaries**

Run:

```bash
docker compose -f deploy/live-pipeline/compose.yaml \
  --env-file deploy/live-pipeline/.env.example config --quiet
docker compose -f deploy/live-pipeline/compose.yaml \
  --env-file deploy/live-pipeline/.env.example config --services
```

Expected: exit code 0; service output contains only `producer` and `edit-stream`.

- [ ] **Step 5: Record the release commit and require a clean tree**

Run: `git status --short --branch && git rev-parse HEAD`

Expected: no uncommitted files and one commit hash to record in EC2 validation evidence.

### Task 6: Deploy and verify the Producer canary on the data EC2

**Files:**
- Create on EC2: `/home/deploy/infra/pipeline/compose.yaml`
- Create on EC2: `/home/deploy/infra/pipeline/.env` with mode `0600`
- Create on EC2: `/home/deploy/infra/pipeline/app/` from the verified Git commit
- Create on EC2: `/home/deploy/infra/pipeline/state/`
- Create on EC2: `/home/deploy/infra/pipeline/ivy/`

**Interfaces:**
- Consumes: the clean, locally verified Git commit from Task 5 and a user-provided `CONTACT_EMAIL`.
- Produces: a running `wikipulse-producer`, a persisted cursor, and advancing `wiki.edits` offsets.

- [ ] **Step 1: Obtain the contact address without printing or committing it**

Ask the user for the Wikimedia `CONTACT_EMAIL` immediately before deployment. Do not read unrelated server `.env` files to discover one. Do not include the address in validation documentation.

- [ ] **Step 2: Run read-only preflight on both EC2 hosts**

Check `docker ps`, container health, `free -h`, `df -h /`, and `sudo ufw status`. On the data EC2 also list Kafka topics, inspect `wiki.edits` if present, and confirm `/home/deploy/infra/pipeline` does not already contain another deployment. Stop and report instead of overwriting an existing directory.

- [ ] **Step 3: Create a versioned archive from the verified commit**

Run locally with the exact commit from Task 5:

```bash
: "${VERIFIED_COMMIT:?Task 5에서 기록한 전체 40자리 SHA를 설정한다}"
test "$(git rev-parse "${VERIFIED_COMMIT}^{commit}")" = "$VERIFIED_COMMIT"
git archive --format=tar.gz --output=.agents/local/wikipulse-live-phase1.tar.gz \
  "$VERIFIED_COMMIT" data-pipeline deploy/live-pipeline
```

Record `$VERIFIED_COMMIT` beside `Get-FileHash .agents/local/wikipulse-live-phase1.tar.gz -Algorithm SHA256`. Do not replace the archive revision with a later `HEAD`. The generated archive lives in the ignored `.agents/local` directory, is a deployment artifact rather than a source edit, and must not be committed.

- [ ] **Step 4: Upload into a new directory only**

Upload the archive to `/home/deploy/infra/pipeline-upload/`, extract it there, then install the tracked files into the newly created `/home/deploy/infra/pipeline`. Do not copy local `.venv`, dumps, test output, or untracked files. Verify file ownership is `ubuntu:ubuntu` before building.

- [ ] **Step 5: Create the protected production environment file**

Set only these values in `/home/deploy/infra/pipeline/.env`, then set mode `0600`. The first line must be `CONTACT_EMAIL=` followed by the exact address obtained in Step 1; do not substitute a sample value or print the completed line.

```dotenv
PIPELINE_APP_DIR=/home/deploy/infra/pipeline/app
PIPELINE_STATE_DIR=/home/deploy/infra/pipeline/state
PIPELINE_IVY_DIR=/home/deploy/infra/pipeline/ivy
RESTART_POLICY=no
SPARK_INFRA_DIR=/home/deploy/infra/spark
DATA_SERVER_IP=192.0.2.10
SPARK_MASTER=spark://192.0.2.10:7077
KAFKA_BOOTSTRAP_SERVERS=192.0.2.10:9092
```

Never display this file with `cat`, `docker compose config`, or `docker inspect` in captured output. Use `docker compose config --quiet` only.

- [ ] **Step 6: Create or verify the Kafka topic without deleting data**

First describe the topic. If it already has non-zero offsets while the HDFS checkpoint does not exist, stop and report before choosing a starting offset; do not silently skip or replay unknown data. If absent, run inside `kafka-kafka-1`:

```bash
/opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:29092 \
  --create --if-not-exists \
  --topic wiki.edits \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=604800000
```

Then describe the topic and verify partition count, replication factor, and retention. If an existing topic disagrees, stop and report; do not alter it implicitly.

- [ ] **Step 7: Start only the Producer and observe for three minutes**

Run from `/home/deploy/infra/pipeline`:

```bash
sudo docker compose --env-file .env config --quiet
sudo docker compose --env-file .env up -d --build producer
```

Poll at intervals no longer than 60 seconds. Verify all of the following before continuing:

- `wikipulse-producer` remains running within 256 MiB.
- logs show an EventStreams connection and roughly expected enwiki publication activity.
- malformed remains zero or is individually explained.
- Kafka latest offset increases.
- `/home/deploy/infra/pipeline/state/last-event-id` exists and changes.
- existing Kafka, Spark, HDFS, backend, PostgreSQL, and Nginx containers remain in their prior healthy/running state.

- [ ] **Step 8: Stop on any failed Producer condition**

If Step 7 fails, stop only `producer`, preserve logs, the cursor, and Kafka data, and write the observed failure into the validation document before proposing a fix.

### Task 7: Start Spark, prove restart recovery, and record evidence

**Files:**
- Create: `docs/validation/2026-09-18-live-pipeline-phase1.md`

**Interfaces:**
- Consumes: healthy Producer, `wiki.edits`, existing two-node Spark/HDFS, and HDFS checkpoint path.
- Produces: a continuously running `edit-stream` and a complete reproducible validation record.

- [ ] **Step 1: Capture baseline state before starting Spark**

Record timestamp, free memory, root disk usage, existing container states, Kafka latest offset, and the absence or prior state of `/wikipulse/checkpoints/edit-windows-v1`. Do not delete an unexpected existing checkpoint; stop and report it.

- [ ] **Step 2: Start only the Spark Driver**

Run:

```bash
sudo docker compose --env-file .env up -d edit-stream
```

Watch logs in bounded chunks. The first start may download the Kafka connector to the persistent ivy directory. Do not restart during dependency download unless the container exits or the five-minute no-progress limit is reached.

- [ ] **Step 3: Verify distributed execution and HDFS state**

Confirm all of the following:

- Spark Master lists one `wikipulse-edit-windows` application.
- both Worker hosts receive executors over several micro-batches, or the scheduler explains why one executor is sufficient under the 2-core cap; no worker repeatedly loses an executor.
- console output contains non-empty `(wiki, title, window_start, edit_count)` rows.
- HDFS `/wikipulse/checkpoints/edit-windows-v1` contains metadata, offsets, commits, and state.
- HDFS `fsck` reports the checkpoint files healthy with replication 2 where block size permits.
- latest Kafka offset and latest Spark checkpoint offset continue advancing.

- [ ] **Step 4: Run the 15-minute canary**

Poll in chunks no longer than 60 seconds and record start/end values for CPU, memory, disk, Producer counts, Kafka offset, Spark batch ID, and checkpoint size. Stop only the new services if a global constraint is crossed.

- [ ] **Step 5: Prove Producer restart recovery**

Record the cursor file checksum/value fingerprint and Kafka latest offset without printing the cursor contents. Restart only `producer`. Verify the first successful connection reports resume behavior, the cursor file advances again, and Kafka offsets continue without a permanent gap. Any replay duplicates are acceptable only because Task 3 deduplicates them.

- [ ] **Step 6: Prove Spark checkpoint recovery**

Record the latest HDFS commit/offset batch IDs, restart only `edit-stream`, and verify the same application resumes from the next checkpoint batch instead of applying `STARTING_OFFSETS=earliest` as a fresh query. Confirm no checkpoint compatibility or concurrent-query error appears.

- [ ] **Step 7: Recheck all existing services and leave only validated services running**

Verify existing Kafka, Spark, HDFS, backend, PostgreSQL, and Nginx containers retain their original running/healthy state. If every gate passed, leave `producer` and `edit-stream` under `restart: unless-stopped`. Otherwise stop only those two and preserve all evidence.

- [ ] **Step 8: Write the validation record without secrets**

Create `docs/validation/2026-09-18-live-pipeline-phase1.md` containing:

- deployed Git commit and producer image ID
- exact start/end timestamps and non-secret commands
- Kafka topic settings and start/end offsets
- Producer receive/publish/skip/malformed counts
- Spark application ID, worker participation, batch progress, and resource use
- HDFS checkpoint path, size, and replication result
- both restart tests and their pass/fail evidence
- pre/post CPU, memory, disk, and all existing container states
- failures, remaining risks, rollback state, and infrastructure handoff notes

- [ ] **Step 9: Run final repository verification and commit evidence**

Run `git diff --check`, the focused tests from Task 5, and `git status --short`. Then commit only the evidence document and any reviewed implementation fixes:

```bash
git add docs/validation/2026-09-18-live-pipeline-phase1.md
git commit -m "docs: record LIVE pipeline phase 1 validation"
```

Do not push or open an MR until the correct Jira issue key and target branch are confirmed.
