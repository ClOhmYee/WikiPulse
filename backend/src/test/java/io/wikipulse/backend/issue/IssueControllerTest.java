package io.wikipulse.backend.issue;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueDetailResponse;
import io.wikipulse.backend.issue.dto.IssueMemberResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/**
 * API 계약 검증. DB 없이 웹 레이어만. 봉투·오류·필드가 명세 v0.1 과 맞는지 본다.
 */
@WebMvcTest(IssueController.class)
class IssueControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    IssueService service;

    @MockitoBean
    PulseMapService pulseMapService;

    @Test
    void 피드는_data_봉투와_pagination_meta로_준다() throws Exception {
        var card = new IssueCardResponse(42, "Strait of Hormuz tension", 8.4,
                "CONFIRMED", "live", "2026-09-08T04:00:00Z", 5, 3);
        when(service.feed(any(), any(), any(), any(), any())).thenReturn(
                ApiResponse.of(List.of(card), new PageMeta(
                        PageMeta.Pagination.of(0, 50, 1, 1), "2026-09-08T04:00:00Z")));

        mvc.perform(get("/api/v1/issues"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].id").value(42))
                .andExpect(jsonPath("$.data[0].pulseScore").value(8.4))
                .andExpect(jsonPath("$.data[0].memberCount").value(5))
                .andExpect(jsonPath("$.data[0].stockCount").value(3))
                .andExpect(jsonPath("$.meta.pagination.total").value(1))
                .andExpect(jsonPath("$.meta.pagination.hasMore").value(false))
                .andExpect(jsonPath("$.meta.snapshotTs").value("2026-09-08T04:00:00Z"));
    }

    @Test
    void 클러스터가_없으면_data가_빈_배열이다() throws Exception {
        when(service.feed(any(), any(), any(), any(), any())).thenReturn(
                ApiResponse.of(List.of(), PageMeta.of(PageMeta.Pagination.of(0, 50, 0, 0))));

        mvc.perform(get("/api/v1/issues"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").isArray())
                .andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    void 상세는_members와_relatedStocks를_담는다() throws Exception {
        var member = new IssueMemberResponse(901, "enwiki", "Strait of Hormuz",
                1.0, true, 87, 12043);
        var stock = new RelatedStockResponse("FANG", "Diamondback Energy", "NASDAQ",
                "Energy", "BOTH", "SUPPLY_CHAIN", 0.28, 6.1, "호르무즈 …");
        when(service.detail(42L)).thenReturn(ApiResponse.of(new IssueDetailResponse(
                42, "Strait of Hormuz tension", 8.4, "CONFIRMED", "live",
                "2026-09-08T04:00:00Z", "요약", "claude-x",
                List.of(member), List.of(stock))));

        mvc.perform(get("/api/v1/issues/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.members[0].pageId").value(901))
                .andExpect(jsonPath("$.data.members[0].isSeed").value(true))
                .andExpect(jsonPath("$.data.members[0].editCount").value(87))
                .andExpect(jsonPath("$.data.relatedStocks[0].ticker").value("FANG"))
                .andExpect(jsonPath("$.data.relatedStocks[0].tier").value("BOTH"))
                .andExpect(jsonPath("$.data.summaryModel").value("claude-x"));
    }

    @Test
    void 없는_이슈는_404_오류봉투() throws Exception {
        when(service.detail(eq(999L)))
                .thenThrow(ApiException.notFound("issue 999 not found"));

        mvc.perform(get("/api/v1/issues/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"))
                .andExpect(jsonPath("$.error.message").value("issue 999 not found"));
    }

    @Test
    void 잘못된_limit은_400_INVALID_QUERY() throws Exception {
        when(service.feed(any(), any(), any(), any(), eq(0)))
                .thenThrow(ApiException.invalidQuery("limit must be 1..100"));

        mvc.perform(get("/api/v1/issues?limit=0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_QUERY"));
    }

    @Test
    void limit이_숫자가_아니면_400() throws Exception {
        mvc.perform(get("/api/v1/issues?limit=abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_QUERY"));
    }
}
