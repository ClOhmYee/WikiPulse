# 외부 호출 신뢰성 계층 — before/after 측정 (WP-66)

Spring 백엔드가 밖으로 거는 HTTP(GATEWAY 게이트웨이 임베딩, Wikipedia 도입부)에 Resilience4j
공통 신뢰성 계층을 얹기 **전/후**를 같은 harness 로 계량한 기록이다. `ai/*/RESULT.md` 관례를 따른다.

- 대상: [`GatewayEmbeddingClient`](GatewayEmbeddingClient.java), [`WikipediaExtractClient`](WikipediaExtractClient.java)
- 호출 경로: [`StockCandidateWorker`](StockCandidateWorker.java)(단일 스레드 `@Scheduled` 폴러, 요청 경로 밖)
  → [`StockCandidateService`](StockCandidateService.java) → [`WikipediaGatewayEmbeddingSource`](WikipediaGatewayEmbeddingSource.java) → 두 클라이언트
- **−66 스코프**: 전송 계층 실패만(타임아웃·5xx·429·연결오류·회로개방). 응답 스키마 검증·
  `attempt_count`·`check_state` 전이는 −68 몫이라 여기서 다루지 않는다.

---

## 측정 조건 (환경·주입)

| 항목 | 값 |
| --- | --- |
| 측정일 | 2026-09-16 |
| OS | Windows 11 (10.0.26200), amd64 |
| JDK | Temurin/Oracle 17.0.12 (빌드 toolchain Java 17). RestClient 는 JDK `HttpURLConnection` (SimpleClientHttpRequestFactory) |
| 가짜 업스트림 | JDK 내장 `com.sun.net.httpserver.HttpServer` (테스트 의존 0). [`FakeUpstream`](../../../../../../test/java/io/wikipulse/backend/matching/FakeUpstream.java) |
| harness | [`ExternalCallBeforeCharacterizationTest`](../../../../../../test/java/io/wikipulse/backend/matching/ExternalCallBeforeCharacterizationTest.java) — 실제 클라이언트를 가짜 서버로 향하게 하고 폴러를 순수 `new` 조립(AOP 없음)해 전송 계층 원거동을 잰다 |
| 클러스터 수(N) | 3 (멤버 1개/클러스터 → GATEWAY 호출 1회/클러스터) |
| batch-size(prod) | 20 (`wikipulse.matching.scheduler.batch-size`) |

### 타임아웃 — CI 축약 ↔ 프로덕션

| | connect | read | 비고 |
| --- | --- | --- | --- |
| **CI 축약(측정)** | 200 ms | 300 ms | hang 케이스를 초 단위로 끝내려 짧게 잡음 |
| **프로덕션(application.yml)** | GATEWAY 5 s / wiki 5 s | **GATEWAY 30 s** / wiki 10 s | 실제 값. 아래 hang 수치는 이 값으로 외삽 |

**hang 외삽**: 단일 스레드가 클러스터마다 read 타임아웃까지 직렬 정지하므로 폴당 블록 ≈ `N × readTimeout`.
- 측정(N=3, read 300 ms): 아래 표 참조
- 프로덕션(batch 20, GATEWAY read 30 s): 폴당 최대 **20 × 30 s = 600 s** 정지 → 이후 모든 폴 지연

### 주입 방식 (전송 계층 실패 4종 + 연속폴)

| 케이스 | 주입 | 현행 예외/거동(가설) |
| --- | --- | --- |
| A 500 | GATEWAY 즉시 HTTP 500 | 전이성 5xx → `RestClientException` 전파 → 워커가 클러스터 단위로 삼키고 진행 |
| B 429 | GATEWAY 즉시 HTTP 429 | 위와 동일. 레이트리밋/과금 신호 구분 없음 |
| C hang | GATEWAY 요청 수신 후 무응답 | read 타임아웃까지 **단일 스레드 정지**, 직렬 누적 |
| D 크레딧소진 | GATEWAY 200 + `insufficient_quota` 바디(embedding 없음) | `IllegalStateException` → 전이성과 같은 경로로 삼켜짐. **하드 실패인데 빠른 실패 없음** |
| E 연속폴 | A(500)를 3폴 반복 | CB 없음 → 미완료 클러스터를 폴마다 재선택 → 죽은 업스트림 **재타격 = N × 폴수** |

---

## BEFORE (현행: 타임아웃만, 재시도·RL·CB 없음)

측정: 2026-09-16, `ExternalCallBeforeCharacterizationTest` (N=3, connect 200 ms / read 300 ms). 5케이스 전부 통과.

| 케이스 | GATEWAY 호출 수 | 폴러 스레드 블록(ms) | 표면 예외(실측) | 관찰 |
| --- | --- | --- | --- | --- |
| A 500 | 3 (=N) | 55 | `HttpServerErrorException$InternalServerError` | 5xx 를 클러스터마다 삼키고 진행. 빠른 실패 없음 |
| B 429 | 3 (=N) | 77 | `HttpClientErrorException$TooManyRequests` | 429 도 A 와 동일 경로. 레이트리밋/과금 신호 구분 안 됨 |
| C hang | 3 (=N) | 971 (≈ N×readTimeout 900) | `RestClientException` ← `SocketTimeoutException: Read timed out` | 클러스터마다 read 타임아웃까지 단일 스레드 직렬 정지 |
| D 크레딧소진 | 3 (=N) | 51 | `IllegalStateException` ("벡터가 없다") | **하드 실패인데 죽은 키를 폴마다 3회 재타격**. 전이성과 동일 취급 |
| E 연속폴(3) | 9 (=N×3) | — | `HttpServerErrorException$InternalServerError` | CB 없음 → 미완료 클러스터를 폴마다 재선택, 호출 선형 증가 |

### before 요약 (after 에서 뒤집을 것)

1. **모든 실패 모드가 폴당 N회 업스트림을 때린다.** 빠른 실패가 없어 GATEWAY 는 실패 유형과 무관하게
   폴마다 N번 크레딧 소진을 시도한다. D(크레딧 소진)는 이미 죽은 키를 폴마다 재타격한다.
2. **hang 이 단일 폴러 스레드를 직렬로 정지시킨다** — 측정 971 ms(N=3). 프로덕션 외삽(batch 20,
   GATEWAY read 30 s): **폴당 최대 600 s 정지** → 이후 모든 폴 지연. timelimiter/CB 로 끊어야 한다.
3. **서킷브레이커 부재** → 죽은 업스트림 재타격이 폴 수에 선형(3폴=9호출). 방치하면 무한 증가.
4. **하드 실패(D)와 전이성(A·B·C)이 워커에게 구분되지 않는다** — 넷 다 `RuntimeException` 으로
   삼켜져 다음 폴에 재시도된다. 이것이 실패 taxonomy(전이성 vs 하드) + CB 로 죽은 GATEWAY 를 빠르게
   차단해야 하는 근거다. (스키마 검증·`attempt_count` 는 −68 몫이라 −66 범위 밖.)

---

## AFTER (Resilience4j 적용 후)

측정: 2026-09-16, [`ExternalCallResilienceTest`](../../../../../../test/java/io/wikipulse/backend/matching/ExternalCallResilienceTest.java) ·
[`GatewayRateLimiterTest`](../../../../../../test/java/io/wikipulse/backend/matching/GatewayRateLimiterTest.java)
(Spring 컨텍스트, 애스펙트 발동. CB 창 4·min-calls 4·retry wait 20ms 로 축약). 5케이스 전부 통과.

named instance `gateway`: `@RateLimiter` → `@CircuitBreaker` → `@Retry`(fallback). Wikipedia 는 동일 골격, 429 만 전이성.

| 케이스 | before | after | 확인 목표 |
| --- | --- | --- | --- |
| 전이성 500 재시도 | 재시도 0(폴당 실패 즉시 스킵) | **업스트림 2회**(초기+재시도 1) 후 `UpstreamUnavailableException` | ①저하하며 계속 |
| 하드 429 | 전이성과 뭉뚱그려 재시도 대상 취급 가능 | **업스트림 1회**(재시도 0) 후 폴백 신호 | ②크레딧 안 태움 — 죽은 예산에 재시도 안 얹음 |
| 회로 개방 | CB 없음 → 폴마다 재타격(3폴=9호출, 선형↑) | **호출 4회에서 개방 후 정체**(개방 후 업스트림 0). state=OPEN | ②죽은 GATEWAY 폴마다 안 두들김 |
| hang→개방 | 폴당 N×readTimeout 정지, 매 폴 반복 | 개방 후 embed **4 ms** 즉시 실패(read 300 ms·프로덕션 30 s 무시) | ③스레드 안 얼음 |
| RL 처리량 캡 | 상한 없음 | limit 3 초과 시 **초과 2회는 업스트림 0**(3만 통과) | ②공유 예산 폭주 상한 |
| 폴백 | 없음(예외 raw 전파) | 🔴 가짜 벡터/빈 문자열 아님 — `UpstreamUnavailableException` 던져 클러스터 PENDING 유지 | −68 로 신호 위임 |

### after 요약

- **크레딧**: 전이성만 재시도(최대 1회 추가), 429·키만료·쿼터는 재시도 0. 죽은 GATEWAY 는 회로가 열려
  이후 폴이 업스트림을 0회 때린다(before 선형 증가 → after 정체). RL 이 폭주 상한을 건다.
- **스레드**: hang 이 회로를 열면 이후 호출이 4 ms 에 실패한다(소켓 대기 없음). 프로덕션 외삽 =
  첫 개방까지 몇 콜만 read-timeout 을 물고(≤ min-calls), 그 뒤 폴은 즉시 실패 → **폴당 600 s 정지 소멸**.
- **−68 경계 유지**: 폴백은 "호출 못 함" 단일 신호만 던진다. `attempt_count`·`check_state` 전이,
  200 본문 스키마 검증은 건드리지 않았다(기존 `IllegalStateException` 경로 그대로).

### 설계 노트

- **@TimeLimiter 미적용**: resilience4j TimeLimiter 는 `CompletableFuture` 반환에만 동작하는데 두
  클라이언트는 동기 반환이다. 동기 메서드에 붙여도 무효다. hang 상한은 read-timeout 이 이미 잡고,
  반복 hang 은 CB 가 개방해 막는다(위 hang→개방 행이 실측 근거). 비동기화는 단일 폴러에 스레드풀을
  더해 스코프·절약 원칙에 어긋나 채택 안 함.
- **애스펙트 순서**: resilience4j 기본(Retry 바깥 → CB → RL 안쪽). fallback 은 **Retry** 에 둔다 —
  CB 에 두면 CB 가 예외를 폴백으로 변환해 바깥 Retry 가 전이성을 못 보고 재시도가 죽는다.
- **CB record 대상**: `UpstreamTransportException`(전이성+하드)만. RL 거부·키 부재·200 스키마 오류는
  회로에 안 센다 — 게이트웨이 건강 신호가 아니다.
- **before 표의 "표면 예외"** 는 −66 적용 *전* 클라이언트 기준 실측이다. 적용 후에는 전송 예외가
  `Transient/HardUpstreamException` 으로 번역된다. before 특성화 테스트는 순수 `new`(AOP 없음)라
  재시도·개방 없이 전송 baseline 만 문서화한다.
