package io.wikipulse.backend.matching;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/**
 * 재사용 harness — WP-66 신뢰성 계층 측정용 가짜 업스트림.
 *
 * <p>JDK 내장 {@link HttpServer} (테스트 의존 0). 실제 GATEWAY·Wikipedia 를 때리지 않고
 * 전송 계층 실패(500·429·hang·크레딧 소진)를 로컬 소켓에서 재현한다. MockRestServiceServer 는
 * RestClient 레이어에서 가로채 실제 소켓 타임아웃·hang 을 못 태우므로 진짜 서버가 필요하다.
 *
 * <p>before(현행, AOP 없음)와 after(step 5, resilience4j 적용) 측정이 이 harness 를 공유한다.
 * 요청 수를 세어 "폴당 업스트림 호출 수"(GATEWAY 크레딧-소진 프록시)를, {@link Mode#HANG} 로
 * 단일 스레드 블록 시간을 잰다.
 */
final class FakeUpstream implements AutoCloseable {

    /** GATEWAY OK 응답 — data[0].embedding 존재(현행 파서 통과). */
    static final String GATEWAY_OK_BODY = "{\"data\":[{\"embedding\":[0.1,0.2,0.3]}]}";
    /** Wikipedia OK 응답 — extract 존재(도입부 있음). */
    static final String WIKI_OK_BODY = "{\"query\":{\"pages\":{\"1\":{\"extract\":\"A test intro sentence.\"}}}}";
    /**
     * 크레딧 소진/키 만료 재현 바디. HTTP 200 이지만 embedding 없음 →
     * 현행 {@link GatewayEmbeddingClient} 는 IllegalStateException 을 던진다(전이성 아님).
     */
    static final String GATEWAY_CREDIT_EXHAUSTED_BODY =
            "{\"error\":{\"message\":\"insufficient_quota\",\"type\":\"insufficient_quota\"}}";

    enum Mode {
        /** 정상 200 + 유효 바디. */
        OK,
        /** 즉시 500(전이성 5xx). */
        STATUS_500,
        /** 즉시 429(레이트리밋/과금 후보). */
        STATUS_429,
        /** 요청 수신 후 무응답 — read 타임아웃 유발(단일 스레드 정지). */
        HANG,
        /** 200 + 에러 바디(embedding 없음) — 크레딧 소진/키 만료(하드 실패). */
        CREDIT_EXHAUSTED
    }

    private final HttpServer server;
    private final ExecutorService executor;
    private final AtomicInteger requests = new AtomicInteger();
    /** 마지막 요청 본문. 요청이 무엇을 실어 보냈는지 검사하는 테스트용 (WP-150). */
    private final AtomicReference<String> lastRequestBody = new AtomicReference<>("");
    /** 🔴 가변이다 — 공급자별 응답 모양을 테스트마다 바꿔야 한다(WP-172). */
    private volatile String okBody;
    private final long hangMillis;
    private volatile Mode mode = Mode.OK;

    /** OK 응답 본문을 바꾼다. Anthropic/OpenAI 모양 전환용. */
    void okBody(String body) {
        this.okBody = body;
    }

    FakeUpstream(String okBody, long hangMillis) throws IOException {
        this.okBody = okBody;
        this.hangMillis = hangMillis;
        this.server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        this.server.createContext("/", this::handle);
        // 🔴 데몬 스레드 — server.stop() 은 setExecutor 로 넣은 풀을 안 내린다(JDK 계약). HANG 핸들러가
        // 1.5s 스레드를 물고 있어, 비-데몬이면 테스트 종료 후에도 최대 keepalive 만큼 JVM 정리를 지연시킨다.
        this.executor = Executors.newCachedThreadPool(r -> {
            Thread t = new Thread(r, "fake-upstream");
            t.setDaemon(true);
            return t;
        });
        this.server.setExecutor(executor);
        this.server.start();
    }

    int port() {
        return server.getAddress().getPort();
    }

    void mode(Mode m) {
        this.mode = m;
    }

    int requestCount() {
        return requests.get();
    }

    void resetCount() {
        requests.set(0);
        lastRequestBody.set("");
    }

    /** 마지막으로 받은 요청 본문 (WP-150). 아직 없으면 빈 문자열. */
    String lastRequestBody() {
        return lastRequestBody.get();
    }

    private void handle(HttpExchange ex) throws IOException {
        requests.incrementAndGet();
        // 본문을 먼저 비워 읽는다 — HANG 모드에서도 클라이언트가 쓰기를 마치게 한다.
        lastRequestBody.set(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
        try {
            switch (mode) {
                case OK -> respond(ex, 200, okBody);
                case STATUS_500 -> respond(ex, 500, "{\"error\":\"internal\"}");
                case STATUS_429 -> respond(ex, 429, "{\"error\":\"rate_limited\"}");
                case CREDIT_EXHAUSTED -> respond(ex, 200, GATEWAY_CREDIT_EXHAUSTED_BODY);
                case HANG -> {
                    try {
                        Thread.sleep(hangMillis); // 클라이언트가 read 타임아웃으로 먼저 끊는다.
                    } catch (InterruptedException ignored) {
                        Thread.currentThread().interrupt();
                    }
                    try {
                        respond(ex, 200, okBody); // 이미 끊겼으면 무시.
                    } catch (IOException ignored) {
                        // 클라이언트가 이미 소켓을 닫음.
                    }
                }
            }
        } finally {
            ex.close();
        }
    }

    private static void respond(HttpExchange ex, int status, String body) throws IOException {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().add("Content-Type", "application/json");
        ex.sendResponseHeaders(status, b.length);
        try (OutputStream os = ex.getResponseBody()) {
            os.write(b);
        }
    }

    @Override
    public void close() {
        server.stop(0);
        executor.shutdownNow(); // stop() 은 커스텀 executor 를 안 내린다 — 직접 종료.
    }
}
