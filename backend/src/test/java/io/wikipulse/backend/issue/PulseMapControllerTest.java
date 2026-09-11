package io.wikipulse.backend.issue;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.hamcrest.Matchers.nullValue;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.issue.dto.pulse.PulseMap;
import io.wikipulse.backend.issue.dto.pulse.SnapshotView;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 펄스맵 조회 API 계약 검증 (WP-74). DB 없이 웹 레이어만.
 * pulse-openapi.json 의 봉투·필드·오류·null 처리가 맞는지 본다.
 */
@WebMvcTest(IssueController.class)
class PulseMapControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    IssueService service;

    @MockitoBean
    PulseMapService pulseMapService;

    @Test
    void 스냅샷_목록은_data_배열이고_meta가_없다() throws Exception {
        when(pulseMapService.snapshots(any(), any(), any())).thenReturn(
                ApiResponse.of(List.of(
                        new SnapshotView("2026-09-08T04:00:00Z", "live", 3),
                        new SnapshotView("2026-09-08T03:00:00Z", "live", 0))));  // 완료된 빈 스냅샷

        mvc.perform(get("/api/v1/issues/snapshots?source=live"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].snapshotTs").value("2026-09-08T04:00:00Z"))
                .andExpect(jsonPath("$.data[0].clusterCount").value(3))
                .andExpect(jsonPath("$.data[1].clusterCount").value(0))
                .andExpect(jsonPath("$.meta").doesNotExist());
    }

    @Test
    void 지도는_클러스터_노드_간선과_meta를_담는다() throws Exception {
        var node = new PulseMap.Node("901", "enwiki", "Strait of Hormuz", true,
                47, 91000, 3.2, 390.0, 9.7, 0.66, "complete",
                "2025-06-12T00:00:00Z", "2025-06-12T04:00:00Z");
        var edge = new PulseMap.Edge("5", "901", "902", "clickstream", true, 383.0,
                new PulseMap.Evidence("Clickstream 2025-05", "2025-05", null));
        var cluster = new PulseMap.Cluster("42", "live:enwiki:Strait of Hormuz",
                "Strait of Hormuz tension", null, "world", "2025-06-12T00:00:00Z",
                true, 9.7, "DETECTED", 2, List.of(node), List.of(edge));
        var meta = new PulseMap.Meta("2025-06-12T05:00:00Z", "live", null,
                "v1", 24.0, 1, 2, 1, false);

        when(pulseMapService.map(any(), any()))
                .thenReturn(ApiResponse.of(new PulseMap.Data(List.of(cluster)), meta));

        mvc.perform(get("/api/v1/issues/map?snapshotTs=2025-06-12T05:00:00Z&source=live"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.clusters[0].id").value("42"))
                .andExpect(jsonPath("$.data.clusters[0].issueKey").value("live:enwiki:Strait of Hormuz"))
                .andExpect(jsonPath("$.data.clusters[0].hot").value(true))
                .andExpect(jsonPath("$.data.clusters[0].nodes[0].pageId").value("901"))
                .andExpect(jsonPath("$.data.clusters[0].nodes[0].sizeScore").value(0.66))
                .andExpect(jsonPath("$.data.clusters[0].edges[0].kind").value("clickstream"))
                .andExpect(jsonPath("$.data.clusters[0].edges[0].evidence.month").value("2025-05"))
                .andExpect(jsonPath("$.meta.scoreVersion").value("v1"))
                .andExpect(jsonPath("$.meta.nodeCount").value(2))
                .andExpect(jsonPath("$.meta.truncated").value(false));
    }

    @Test
    void ID는_불투명_문자열이다() throws Exception {
        var meta = new PulseMap.Meta("2025-06-12T05:00:00Z", "live", null, "v1", 24.0, 0, 0, 0, false);
        when(pulseMapService.map(any(), any()))
                .thenReturn(ApiResponse.of(new PulseMap.Data(List.of()), meta));

        mvc.perform(get("/api/v1/issues/map"))
                .andExpect(status().isOk())
                // 숫자가 아니라 문자열이어야 BIGINT 정밀도가 안 깨진다
                .andExpect(jsonPath("$.meta.snapshotTs").value("2025-06-12T05:00:00Z"));
    }

    @Test
    void nullable_지표는_null로_나온다() throws Exception {
        // 비-씨드 노드: 지표가 전부 null 이어도 필드가 present 여야 한다(계약)
        var node = new PulseMap.Node("902", "enwiki", "Sibling", false,
                null, null, null, null, null, null, "unavailable",
                "2025-06-12T00:00:00Z", "2025-06-12T04:00:00Z");
        var cluster = new PulseMap.Cluster("42", "k", "label", null, "other", null,
                false, 1.0, "DETECTED", 1, List.of(node), List.of());
        var meta = new PulseMap.Meta("2025-06-12T05:00:00Z", "live", null, "v1", 24.0, 1, 1, 0, false);
        when(pulseMapService.map(any(), any()))
                .thenReturn(ApiResponse.of(new PulseMap.Data(List.of(cluster)), meta));

        mvc.perform(get("/api/v1/issues/map"))
                .andExpect(status().isOk())
                // required+nullable — 필드는 present 하되 값이 null 이어야 한다(계약)
                .andExpect(jsonPath("$.data.clusters[0].nodes[0].spikeScore").value(nullValue()))
                .andExpect(jsonPath("$.data.clusters[0].nodes[0].sizeScore").value(nullValue()))
                .andExpect(jsonPath("$.data.clusters[0].nodes[0].editCount").value(nullValue()))
                .andExpect(jsonPath("$.data.clusters[0].nodes[0].completeness").value("unavailable"))
                .andExpect(jsonPath("$.data.clusters[0].summary").value(nullValue()))
                .andExpect(jsonPath("$.data.clusters[0].firstDetectedAt").value(nullValue()));
    }

    @Test
    void 없는_스냅샷은_404_오류봉투() throws Exception {
        when(pulseMapService.map(any(), any()))
                .thenThrow(ApiException.notFound("snapshot 2020-01-01T00:00:00Z (live) not found"));

        mvc.perform(get("/api/v1/issues/map?snapshotTs=2020-01-01T00:00:00Z"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }
}
