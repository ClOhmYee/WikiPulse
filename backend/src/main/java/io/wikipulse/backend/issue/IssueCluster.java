package io.wikipulse.backend.issue;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * issue_cluster 테이블. 한 시점의 이슈 클러스터 = 버블맵의 버블 하나.
 *
 * <p>클러스터는 시점의 함수다. 같은 사건이라도 snapshotTs 마다 구성·급등도가
 * 다르다. LIVE 화면은 가장 최근 snapshotTs 를, 리플레이는 고른 시점을 읽는다.
 * 스키마: db/migrations/V1__initial_schema.sql
 */
@Entity
@Table(name = "issue_cluster")
public class IssueCluster {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "snapshot_ts", nullable = false)
    private Instant snapshotTs;

    @Column(name = "label")
    private String label;

    @Column(name = "pulse_score", nullable = false)
    private double pulseScore;

    /** DETECTED / VERIFYING / CONFIRMED / DISCARDED. 피드 3단계 노출용. */
    @Column(name = "status", nullable = false)
    private String status;

    /** live / replay. 실시간 산출물과 덤프 재계산 산출물 구분. */
    @Column(name = "source", nullable = false)
    private String source;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected IssueCluster() {
    }

    public Long getId() {
        return id;
    }

    public Instant getSnapshotTs() {
        return snapshotTs;
    }

    public String getLabel() {
        return label;
    }

    public double getPulseScore() {
        return pulseScore;
    }

    public String getStatus() {
        return status;
    }

    public String getSource() {
        return source;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
