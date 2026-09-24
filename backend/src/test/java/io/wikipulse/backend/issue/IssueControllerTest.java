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
import io.wikipulse.backend.issue.dto.IssueReportResponse;
import io.wikipulse.backend.issue.dto.IssueHistoryGroupResponse;
import io.wikipulse.backend.issue.dto.IssueHistoryReportResponse;
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
@org.springframework.context.annotation.Import(io.wikipulse.backend.account.SecurityConfig.class)
@WebMvcTest(IssueController.class)
class IssueControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    IssueService service;

    @MockitoBean
    PulseMapService pulseMapService;

    @Test
    void rankingRouteReturnsBothPeriodsWithoutUsingTheDetailRoute() throws Exception {
        var entry = new io.wikipulse.backend.issue.dto.IssueRankingsResponse.Entry(42, "Peak issue", 9.5);
        when(service.rankings()).thenReturn(ApiResponse.of(
                new io.wikipulse.backend.issue.dto.IssueRankingsResponse(
                        "2026-09-22T00:00:00Z", "2026-08-23T00:00:00Z", "2025-09-22T00:00:00Z",
                        List.of(entry), List.of(entry))));
        mvc.perform(get("/api/v1/issues/rankings"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.monthly[0].id").value(42))
                .andExpect(jsonPath("$.data.yearly[0].pulseScore").value(9.5))
                .andExpect(jsonPath("$.data.asOf").value("2026-09-22T00:00:00Z"));
    }

    @Test
    void 대표_문서_목록은_묶음과_기본_리포트_ID를_내려준다() throws Exception {
        var group = new IssueHistoryGroupResponse(42, "The Odyssey (2026 film)",
                "replay", "CONFIRMED", 12.0, "2026-07-18T01:00:00Z",
                "2026-07-17T01:00:00Z", 10, 41L, "저장된 요약", 3, 1);
        when(service.historyGroups(any(), any(), any(), any(), any())).thenReturn(
                ApiResponse.of(List.of(group), PageMeta.of(
                        PageMeta.Pagination.of(0, 20, 1, 1))));

        mvc.perform(get("/api/v1/issues/history/groups?q=Odyssey&offset=0&limit=20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].id").value(42))
                .andExpect(jsonPath("$.data[0].defaultReportId").value(41))
                .andExpect(jsonPath("$.data[0].occurrenceCount").value(10))
                .andExpect(jsonPath("$.meta.pagination.total").value(1));
    }

    @Test
    void 리포트_이력은_시점별_ID와_시각을_내려준다() throws Exception {
        var report = new IssueHistoryReportResponse(41, "2026-07-17T01:00:00Z",
                "CONFIRMED", 11.0);
        when(service.historyReports(eq(42L), any(), any())).thenReturn(
                ApiResponse.of(List.of(report), PageMeta.of(
                        PageMeta.Pagination.of(0, 100, 1, 1))));

        mvc.perform(get("/api/v1/issues/42/history/reports?limit=100"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].id").value(41))
                .andExpect(jsonPath("$.data[0].snapshotTs").value("2026-07-17T01:00:00Z"))
                .andExpect(jsonPath("$.meta.pagination.hasMore").value(false));
    }

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
                "호르무즈 해협", null, 1.0, true, 87, 12043, "complete");
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
                // 🔴 한국어 표시명이 붙어도 영문 원문은 그대로 내려간다 — 위키 링크가 그걸 쓴다.
                .andExpect(jsonPath("$.data.members[0].title").value("Strait of Hormuz"))
                .andExpect(jsonPath("$.data.members[0].titleKo").value("호르무즈 해협"))
                .andExpect(jsonPath("$.data.members[0].editCount").value(87))
                // 판정 시점 고정값의 상태 — null 이 "대기" 인지 "원본 없음" 인지 구분한다
                // (WP-129 5번).
                .andExpect(jsonPath("$.data.members[0].completeness").value("complete"))
                .andExpect(jsonPath("$.data.relatedStocks[0].ticker").value("FANG"))
                .andExpect(jsonPath("$.data.relatedStocks[0].tier").value("BOTH"))
                .andExpect(jsonPath("$.data.summaryModel").value("claude-x"));
    }

    @Test
    void 상세는_리포트가_있으면_report_섹션을_담는다() throws Exception {
        var report = new IssueReportResponse("ready", "claude-x (report_v1)",
                "2026-09-24T05:00:00Z", "2026-07-19T23:00:00Z",
                List.of(new IssueReportResponse.Section("overview", "이슈 개요", "본문",
                        List.of("901"))));
        when(service.detail(43L)).thenReturn(ApiResponse.of(new IssueDetailResponse(
                43, "2026 FIFA World Cup", 12.15, "CONFIRMED", "replay",
                "2026-07-19T23:00:00Z", "요약", "claude-x", List.of(), List.of(), report)));

        mvc.perform(get("/api/v1/issues/43"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.report.status").value("ready"))
                .andExpect(jsonPath("$.data.report.sections[0].id").value("overview"))
                .andExpect(jsonPath("$.data.report.sections[0].evidenceIds[0]").value("901"));
    }

    @Test
    void 상세는_리포트가_없으면_report_필드가_없다() throws Exception {
        // 프론트는 report 가 없을 때 기존 "근거 부족" 상태를 그대로 보인다.
        when(service.detail(44L)).thenReturn(ApiResponse.of(new IssueDetailResponse(
                44, "x", 1.0, "DETECTED", "live", "2026-07-19T23:00:00Z",
                null, null, List.of(), List.of())));

        mvc.perform(get("/api/v1/issues/44"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.report").doesNotExist());
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
