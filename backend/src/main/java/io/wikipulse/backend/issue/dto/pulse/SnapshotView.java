package io.wikipulse.backend.issue.dto.pulse;

/**
 * 선택 가능한 스냅샷 하나. 계약: GET /api/v1/issues/snapshots (WP-74).
 *
 * <p>완료된 스냅샷만, (source, snapshotTs) 로 유일하다. clusterCount=0 인 완료
 * 스냅샷도 포함한다 — 슬라이더가 "완료된 빈 시점"과 "미저장 시점"을 구분한다.
 */
public record SnapshotView(
        String snapshotTs,
        String source,
        long clusterCount) {

    public interface Projection {
        java.time.Instant getSnapshotTs();
        String getSource();
        long getClusterCount();
    }

    public static SnapshotView from(Projection p) {
        return new SnapshotView(p.getSnapshotTs().toString(), p.getSource(), p.getClusterCount());
    }
}
