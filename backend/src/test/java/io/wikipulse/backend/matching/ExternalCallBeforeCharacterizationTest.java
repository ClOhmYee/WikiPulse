package io.wikipulse.backend.matching;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

/**
 * BEFORE 특성화 (WP-66, RESULT.md 근거). 현행 = 타임아웃만, 재시도·레이트리밋·
 * 서킷브레이커 없음. 실제 클라이언트를 {@link FakeUpstream} 로 향하게 하고, 단일 스레드 폴러
 * ({@link StockCandidateWorker})가 500·429·hang·크레딧소진에서 어떻게 도는지 계량한다.
 *
 * <p>이 클래스는 순수 {@code new} 조립이라 Spring AOP 가 없다 — resilience4j 어노테이션이
 * 붙어도 프록시가 안 걸려 <b>전송 계층 원거동</b>을 그대로 문서화한다. after(step 5) 어스펙트
 * 검증은 Spring 컨텍스트 테스트로 따로 두고 {@link FakeUpstream} 만 공유한다.
 *
 * <p>🔴 CI 축약 타임아웃: connect 200ms / read 300ms (프로덕션은 GATEWAY 5s/30s·wiki 5s/10s).
 * hang 블록 시간은 이 축약값 기준이며 RESULT.md 에서 프로덕션으로 외삽한다.
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class ExternalCallBeforeCharacterizationTest {

    private static final Duration CONNECT_TIMEOUT = Duration.ofMillis(200);
    private static final Duration READ_TIMEOUT = Duration.ofMillis(300);
    private static final long HANG_MILLIS = 1500; // read 타임아웃보다 길게 → 반드시 타임아웃.
    private static final List<Long> CLUSTERS = List.of(1L, 2L, 3L);

    @Mock
    CandidateRepository repository;
    @Mock
    ClusterIntroRepository introRepository;

    private FakeUpstream gateway;
    private FakeUpstream wiki;
    private StockCandidateWorker worker;

    @BeforeEach
    void setUp() throws Exception {
        gateway = new FakeUpstream(FakeUpstream.GATEWAY_OK_BODY, HANG_MILLIS);
        wiki = new FakeUpstream(FakeUpstream.WIKI_OK_BODY, HANG_MILLIS);

        CandidateProperties props = new CandidateProperties();
        CandidateProperties.Gateway g = props.getGateway();
        g.setBaseUrl("http://127.0.0.1:" + gateway.port());
        g.setApiKey("test-key"); // 키 가드 통과 — 전송 실패를 재현하기 위함.
        g.setConnectTimeout(CONNECT_TIMEOUT);
        g.setReadTimeout(READ_TIMEOUT);
        CandidateProperties.Wikipedia w = props.getWikipedia();
        w.setApiUrl("http://127.0.0.1:" + wiki.port() + "/w/api.php");
        w.setConnectTimeout(CONNECT_TIMEOUT);
        w.setReadTimeout(READ_TIMEOUT);

        GatewayEmbeddingClient gatewayClient = new GatewayEmbeddingClient(props);
        WikipediaExtractClient wikiClient = new WikipediaExtractClient(props);
        ClusterMemberIntros intros = new ClusterMemberIntros(introRepository, wikiClient);
        WikipediaGatewayEmbeddingSource source = new WikipediaGatewayEmbeddingSource(intros, gatewayClient, props);
        StockCandidateService service = new StockCandidateService(repository, source, props);
        worker = new StockCandidateWorker(service, repository, props);

        // 클러스터마다 멤버 1개 → GATEWAY 호출 1회/클러스터(호출 수 = 크레딧-소진 프록시).
        // LIVE 출처라 현재 도입부 경로(prop=extracts)를 탄다 — 이 파일이 재는 건 전송 실패
        // 거동이지 시점 계약이 아니다(WP-129 는 그걸 ClusterMemberIntrosTest 로 본다).
        when(repository.pendingClusterIds(anyInt(), anyInt())).thenReturn(CLUSTERS);
        when(introRepository.context(anyLong())).thenReturn(java.util.Optional.of(
                new ClusterIntroRepository.ClusterContext("live", java.time.OffsetDateTime.now(),
                        List.of(new ClusterIntroRepository.ClusterContext.Member(1L, "Doc")))));
    }

    @AfterEach
    void tearDown() {
        gateway.close();
        wiki.close();
    }

    @Test
    void a_gateway_500_전이성_5xx() {
        wiki.mode(FakeUpstream.Mode.OK);
        gateway.mode(FakeUpstream.Mode.STATUS_500);

        long start = System.nanoTime();
        worker.pollAndGenerate();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        // 현행: 5xx 는 클라이언트가 예외로 던지고 워커가 클러스터 단위로 삼켜 다음으로 진행.
        // 서킷브레이커 없음 → 3개 클러스터가 모두 GATEWAY 를 각각 때린다(빠른 실패 없음).
        System.out.printf("[BEFORE][A 500] gateway호출=%d elapsedMs=%d%n", gateway.requestCount(), elapsedMs);
        assertThat(gateway.requestCount()).isEqualTo(CLUSTERS.size());
    }

    @Test
    void b_gateway_429_레이트리밋_과금후보() {
        wiki.mode(FakeUpstream.Mode.OK);
        gateway.mode(FakeUpstream.Mode.STATUS_429);

        long start = System.nanoTime();
        worker.pollAndGenerate();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        System.out.printf("[BEFORE][B 429] gateway호출=%d elapsedMs=%d%n", gateway.requestCount(), elapsedMs);
        assertThat(gateway.requestCount()).isEqualTo(CLUSTERS.size());
    }

    @Test
    void c_gateway_hang_단일스레드_블록() {
        wiki.mode(FakeUpstream.Mode.OK);
        gateway.mode(FakeUpstream.Mode.HANG);

        long start = System.nanoTime();
        worker.pollAndGenerate();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        // 현행: 클러스터마다 read 타임아웃(300ms)까지 단일 스레드가 직렬로 정지 →
        // 폴 전체가 최소 N × readTimeout 동안 얼어붙는다. 프로덕션(GATEWAY 30s·batch 20)에선 폴당 최대 600s.
        System.out.printf("[BEFORE][C hang] gateway호출=%d elapsedMs=%d (N×readTimeout≈%dms)%n",
                gateway.requestCount(), elapsedMs, CLUSTERS.size() * READ_TIMEOUT.toMillis());
        assertThat(elapsedMs).isGreaterThanOrEqualTo(CLUSTERS.size() * READ_TIMEOUT.toMillis());
    }

    @Test
    void d_gateway_크레딧소진_하드실패() {
        wiki.mode(FakeUpstream.Mode.OK);
        gateway.mode(FakeUpstream.Mode.CREDIT_EXHAUSTED);

        long start = System.nanoTime();
        worker.pollAndGenerate();
        long elapsedMs = (System.nanoTime() - start) / 1_000_000;

        // 현행: 200 이지만 embedding 없음 → IllegalStateException. 전이성 5xx 와 같은 경로로 삼켜지고,
        // 크레딧이 이미 없는 죽은 키를 매 폴 계속 두들긴다(하드 실패인데 빠른 실패가 없다).
        System.out.printf("[BEFORE][D credit] gateway호출=%d elapsedMs=%d%n", gateway.requestCount(), elapsedMs);
        assertThat(gateway.requestCount()).isEqualTo(CLUSTERS.size());
    }

    @Test
    void e_연속폴_죽은_업스트림_재타격() {
        wiki.mode(FakeUpstream.Mode.OK);
        gateway.mode(FakeUpstream.Mode.STATUS_500);

        int polls = 3;
        for (int i = 0; i < polls; i++) {
            worker.pollAndGenerate();
        }

        // 서킷브레이커 없음 → 완료되지 않는 클러스터를 폴마다 다시 집어 GATEWAY 를 계속 때린다.
        // 총 호출 = N × 폴 수. CB 가 있으면 회로 개방 후 급감해야 한다(after 대조).
        System.out.printf("[BEFORE][E re-hit] polls=%d gateway호출총계=%d (기대 N×polls=%d)%n",
                polls, gateway.requestCount(), CLUSTERS.size() * polls);
        assertThat(gateway.requestCount()).isEqualTo(CLUSTERS.size() * polls);
    }
}
