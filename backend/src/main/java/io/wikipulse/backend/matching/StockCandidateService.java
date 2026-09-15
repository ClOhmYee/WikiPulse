package io.wikipulse.backend.matching;

import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 이슈 하나의 종목 후보를 생성한다 (명세 §3.2 5번, §6.3 recall — WP-67).
 *
 * <p>흐름: 멤버 제목(급등도순) → 이슈 임베딩 → pgvector 코사인 Top-K(a) ∪ GDELT lift 상위(b)
 * → tier → cluster_stock 에 verified=false 로 멱등 적재. LLM 검증(precision)은 여기 없다 —
 * 이 워커는 후보를 쌓기만 하고, 근거 경로 판정은 명세 §6.3 검증 단계(별도 이슈)가 맡는다.
 */
@Service
public class StockCandidateService {

    private static final Logger log = LoggerFactory.getLogger(StockCandidateService.class);

    private final CandidateRepository repository;
    private final ClusterEmbeddingSource embeddingSource;
    private final CandidateProperties props;

    public StockCandidateService(
            CandidateRepository repository,
            ClusterEmbeddingSource embeddingSource,
            CandidateProperties props) {
        this.repository = repository;
        this.embeddingSource = embeddingSource;
        this.props = props;
    }

    /** 후보 생성 결과 요약. 로그·재실행 판단용. */
    public record Result(long clusterId, int embeddingCandidates, int gdeltCandidates, int stored) {
    }

    /**
     * 클러스터 하나의 후보를 만들어 적재한다. 재실행하면 갱신된다(인수조건 4).
     * 대표 텍스트를 만들 도입부가 하나도 없으면 임베딩 경로는 비고 GDELT 경로만으로 후보를 낸다.
     */
    public Result generateFor(long clusterId) {
        List<String> titles = repository.memberTitlesByPulse(clusterId);

        Map<String, Double> embedding = embeddingSource.embed(titles)
                .map(vector -> repository.embeddingTopK(vector, props.getEmbeddingTopK()))
                .orElseGet(Map::of);
        Map<String, Double> gdelt = repository.gdeltTopK(clusterId, props.getGdeltTopK());

        List<StockCandidate> candidates = CandidateTiering.combine(embedding, gdelt);
        int stored = repository.replaceCandidates(clusterId, candidates);

        log.info("후보 생성 cluster={} 임베딩={} GDELT={} 합집합={} 적재={}",
                clusterId, embedding.size(), gdelt.size(), candidates.size(), stored);
        return new Result(clusterId, embedding.size(), gdelt.size(), stored);
    }
}
