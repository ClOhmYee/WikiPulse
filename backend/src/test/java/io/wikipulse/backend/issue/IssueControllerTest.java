package io.wikipulse.backend.issue;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.wikipulse.backend.common.NotFoundException;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.issue.dto.IssueDetailResponse;
import io.wikipulse.backend.stock.dto.RelatedStockResponse;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/**
 * API 계약 검증. DB 없이 웹 레이어만 띄우고 서비스는 mock 한다.
 * FE 가 의존하는 JSON 형태가 바뀌면 여기서 걸린다.
 */
@WebMvcTest(IssueController.class)
class IssueControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    IssueService service;

    @Test
    void 피드는_카드_배열을_급등도_필드와_함께_준다() throws Exception {
        when(service.feed(any(), any(), any())).thenReturn(List.of(
                new IssueCardResponse(1L, "Hurricane Milton 상륙", 9.7,
                        "CONFIRMED", Instant.parse("2024-10-10T13:00:00Z"))));

        mvc.perform(get("/api/issues"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[0].label").value("Hurricane Milton 상륙"))
                .andExpect(jsonPath("$[0].pulseScore").value(9.7))
                .andExpect(jsonPath("$[0].status").value("CONFIRMED"));
    }

    @Test
    void 클러스터가_없으면_빈_배열이다() throws Exception {
        when(service.feed(any(), any(), any())).thenReturn(List.of());

        mvc.perform(get("/api/issues"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void 상세는_멤버_요약_관련종목을_담는다() throws Exception {
        when(service.detail(1L)).thenReturn(new IssueDetailResponse(
                1L, "Hurricane Milton 상륙", 9.7, "CONFIRMED", "replay",
                Instant.parse("2024-10-10T13:00:00Z"),
                List.of("Hurricane Milton", "Florida"),
                "플로리다 상륙 이슈 요약",
                List.of(new RelatedStockResponse(
                        "NEE", "NextEra Energy", "NYSE", "BOTH", "REGION",
                        null, 10.5, "플로리다 전력망 운영사"))));

        mvc.perform(get("/api/issues/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.memberTitles.length()").value(2))
                .andExpect(jsonPath("$.relatedStocks[0].ticker").value("NEE"))
                .andExpect(jsonPath("$.relatedStocks[0].tier").value("BOTH"))
                .andExpect(jsonPath("$.relatedStocks[0].gdeltLift").value(10.5))
                .andExpect(jsonPath("$.relatedStocks[0].rationale").value("플로리다 전력망 운영사"));
    }

    @Test
    void 없는_이슈는_404() throws Exception {
        when(service.detail(eq(999L))).thenThrow(new NotFoundException("이슈 999 없음"));

        mvc.perform(get("/api/issues/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.message").value("이슈 999 없음"));
    }
}
