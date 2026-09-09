package io.wikipulse.backend.stock;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockCardResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(StockController.class)
class StockControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    StockService service;

    @Test
    void 종목_목록은_data_봉투_issueCount_pagination() throws Exception {
        when(service.search(any(), any(), any(), anyBoolean(), any(), any())).thenReturn(
                ApiResponse.of(
                        List.of(new StockCardResponse("NVDA", "NVIDIA Corporation",
                                "NASDAQ", "Technology", 2)),
                        PageMeta.of(PageMeta.Pagination.of(0, 50, 1, 1))));

        mvc.perform(get("/api/v1/stocks?q=nvid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].ticker").value("NVDA"))
                .andExpect(jsonPath("$.data[0].issueCount").value(2))
                .andExpect(jsonPath("$.meta.pagination.total").value(1));
    }

    @Test
    void 종목_상세는_cik_포함_봉투() throws Exception {
        when(service.get("NVDA")).thenReturn(ApiResponse.of(new StockResponse(
                "NVDA", "NVIDIA Corporation", "NASDAQ", "0001045810",
                "Technology", "설명")));

        mvc.perform(get("/api/v1/stocks/NVDA"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.ticker").value("NVDA"))
                .andExpect(jsonPath("$.data.cik").value("0001045810"));
    }

    @Test
    void 종목이_걸린_이슈_목록() throws Exception {
        when(service.issuesFor("NEE")).thenReturn(ApiResponse.of(List.of(
                new IssueCardResponse(1, "Milton", 9.7, "CONFIRMED", "live",
                        "2024-10-10T13:00:00Z", 2, 1))));

        mvc.perform(get("/api/v1/stocks/NEE/issues"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].id").value(1))
                .andExpect(jsonPath("$.data[0].label").value("Milton"));
    }

    @Test
    void 없는_종목은_404_오류봉투() throws Exception {
        when(service.get("ZZZZ")).thenThrow(ApiException.notFound("stock ZZZZ not found"));

        mvc.perform(get("/api/v1/stocks/ZZZZ"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }
}
