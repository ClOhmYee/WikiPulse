# CORE_ONLY clustering preview

실제 WikiPulse 서비스(백엔드 + 프론트)를 그대로 띄우고 **DB 만** 바꿔서, PoC 5 의
CORE_ONLY 클러스터링 결과를 화면에서 직접 본다. 애플리케이션 코드·UI 는 고치지 않았다.

## 정본 규칙 (이 preview 에 들어간 것)

```
spike 후보
  ↓  1. ROOT SELECTION   views DESC · 시점당 20 · 24h 쿨다운
20 roots / snapshot
  ↓  2. CORE GROUPING    strict as-of direct link → component → focus τ=0.005 → D2
root-only issue cluster
```

전체 1,104 snapshot · root 22,080 · component 19,432 (singleton 17,569 / 2: 1,461 /
3~4: 322 / 5~7: 57 / 8~12: 20 / 13+: 3 / max 16 / 20+ giant 0).

🔴 **현재 `public` 스키마는 production driver 가 직접 적재한 것이다** (2026-09-22,
`python -m cluster.driver --source replay`). ~~CSV 를 옮겨 넣은 것~~ 이 아니다.

🔴 **body-only common-neighbor expansion(PoC 7 B1~B4)은 들어 있지 않다.** precision
미달로 채택하지 않았다. citation/body 분리 코드는 PoC 쪽 자산으로만 남는다.

## 무엇을 건드리지 않았나

- `localhost:5434`(`wikipulse-actual-replay-137-pg`) · `localhost:5435`
  (`wikipulse-actual-replay-latest-pg`) — **컨테이너를 기동조차 하지 않았다.**
  preview 데이터는 5434 의 **볼륨을 통째로 복사**해서 만들었다(`:ro` 마운트 복사).
- PoC 알고리즘, detector(급증 판정), 기존 PoC 캐시. `spike` 행은 한 줄도 안 바뀐다.
- 백엔드·프론트엔드 소스. 바뀐 것은 `DATABASE_URL` 과 포트뿐이다.

## 구성

| | |
| --- | --- |
| preview DB | `localhost:5436` · 컨테이너 `wikipulse-cluster-preview-pg` · 볼륨 `wikipulse-cluster-preview-pgdata` |
| DB 이름 | `wikipulse_cluster_preview` (5434 볼륨 복사본을 rename) |
| 계정 | `replay` / `<local-db-password>` |
| `public` 스키마 | **production driver 산출물** (ROOT SELECTION + CORE) — 서비스가 읽는 곳 |
| `baseline` 스키마 | 교체 전 원본 4개 테이블 그대로 (root 1건 = 클러스터 1건, 22,080개) |
| 백엔드 | http://localhost:18080 |
| 프론트 | http://localhost:5176 |

## 실행

```bash
docker compose -f tools/cluster-preview/compose.preview.yml up -d
```

DB 는 이 compose 가 만들지 않는다. 이미 떠 있는 `wikipulse-cluster-preview-pg` 에
`wikipulse-preview-net` 으로 붙는다.

## 전체 회귀 검증 (WP-186) — ROOT SELECTION + CORE

production 코드가 두 단계를 관통해 PoC 5 결과를 그대로 내는지 매번 대조한다.
root 집합 exact match 와 분포 11개 항목·대표 사건 8건을 전부 본다. 어긋나면 종료 코드가 0이 아니다.

```bash
python tools/cluster-preview/seed_asof_link_cache.py   # PoC 캐시 → V11 (1회)
python tools/cluster-preview/verify_core_regression.py
```

**production 경로만 쓴다.** root 는 `spike` 에서 `cluster.root_selection` 이 고르고,
클러스터는 `cluster.driver.build_snapshot_at` 이 만든다. PoC frozen root set
(`baseline.cluster_member`)은 **selector 가 같은 root 를 골랐는지 대조하는 oracle 로만**
쓴다 — PoC 산출물을 결과로 읽어 통과시키지 않는다.

~~root 집합이 두 벌이라 driver 를 그대로 돌리면 19,432 가 안 나온다~~ → 해소됐다
(2026-09-22). ROOT SELECTION(20 / 24h)이 `(snapshot_ts, page_id)` 22,080 쌍을 frozen set
과 **정확히** 재현한다.

## 적재 스크립트

```bash
python tools/cluster-preview/import_core_clusters.py
```

입력은 PoC 5 가 이미 만들어 둔 `poc5-core-components-1104.csv`(이 폴더에 복사해 뒀다).
스크립트는 클러스터링을 **다시 계산하지 않는다** — component 목록을 DB contract 로
옮기기만 한다. DSN 에 5434·5435 가 들어오면 거부한다.

### 유도한 값 세 가지 (여러 root 를 하나로 합칠 때만)

| 컬럼 | 규칙 |
| --- | --- |
| `pulse_score` | 구성 root 들의 `spike_score` 최댓값. singleton 이면 원래 값과 정확히 같다 |
| `issue_key` | `spike_score` 가 가장 큰 root 의 **기존** issue_key 를 물려받는다 (새로 만들지 않음) |
| `first_detected_at` | 구성 root 들의 최솟값 |

`label`·`category`·`status`·`source`·`score_version` 은 baseline 값 그대로다.
`issue_report`·`cluster_stock`·`page_intro` 는 원본이 0행이고, **채우지 않았다** —
뉴스·AI 요약·종목은 화면에서 비어 있는 것이 정상이다.

### 멤버·간선

- 멤버 = component 의 **root 만**. `cluster_member` 행을 컬럼째 복사한다.
  CORE_ONLY 가 실제로 내놓는 것이 root component 라 이게 기본값이다 (22,080행).
- `cluster_edge` = 기존 clickstream 간선 중 **양 끝이 모두 같은 새 클러스터의 멤버인 것만**
  옮겼다(41건). 새로 만들지 않았다.
  ⚠️ CORE 의 근거인 **direct-link 간선은 저장하지 않는다** — `cluster_edge.kind` 가
  `clickstream|wikidata` 로 제한돼 있어 넣으려면 스키마·백엔드·프론트 계약을 모두 바꿔야 한다.
  그래서 화면의 클러스터 내부 선은 대부분 "소속" 표현이고 문서 쌍 근거가 아니다.

🔴 **`--keep-clickstream-members` 를 켜면 펄스맵이 통째로 안 그려진다.** clickstream 확장
멤버는 `window_start`·`window_end` 가 NULL 인데 프론트 계약(`contract.js` 의 `metric window`)이
노드마다 두 값을 요구한다. baseline 원본도 같은 이유로 **5,120개 클러스터**가 렌더 대상에서
탈락한다 — 이번 적재가 만든 문제가 아니라 replay 데이터셋이 원래 그렇다.

## 화면에서 걸리는 것

- `issue_report`·`cluster_stock` 이 원본에 0행이라 요약·연관 종목은 비어 있다. 정상이다.
- ~~`label` 이 전부 NULL 이라 이슈 목록이 "제목 미제공"~~ → 해소됐다 (2026-09-22).
  production driver 가 `label` 에 lead root 제목을 채운다(19,432/19,432). 그래서 펄스맵
  버블 이름이 CSV 적재본과 다르다 — 같은 클러스터인데 제목 출처가 노드 폴백에서
  `label` 로 바뀐 것이다 (Dolly: `Coat of Many Colors (song)` → `Stella Parton`).

## baseline 과 비교

```bash
PREVIEW_SCHEMA=baseline docker compose -f tools/cluster-preview/compose.preview.yml up -d
```

같은 snapshot 을 열면 CORE 가 묶기 전(root 1건 = 버블 1개, 스냅샷당 20개)이 나온다.
