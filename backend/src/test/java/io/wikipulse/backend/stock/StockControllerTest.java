package io.wikipulse.backend.stock;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.hamcrest.Matchers.nullValue;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.wikipulse.backend.common.ApiException;
import io.wikipulse.backend.common.ApiResponse;
import io.wikipulse.backend.common.PageMeta;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockCardResponse;
import io.wikipulse.backend.stock.dto.StockPriceResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.math.BigDecimal;
import java.time.LocalDate;
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
    void 종목_목록은_data_봉투_issueCount_lastClose_pagination() throws Exception {
        when(service.search(any(), any(), any(), anyBoolean(), any(), any())).thenReturn(
                ApiResponse.of(
                        List.of(
                                new StockCardResponse("NVDA", "NVIDIA Corporation",
                                        "NASDAQ", "Technology", 2, new BigDecimal("201.1500")),
                                new StockCardResponse("ZZZZ", "No Price Inc",
                                        "NASDAQ", null, 0, null)),
                        PageMeta.of(PageMeta.Pagination.of(0, 50, 2, 2))));

        mvc.perform(get("/api/v1/stocks?q=nvid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].ticker").value("NVDA"))
                .andExpect(jsonPath("$.data[0].issueCount").value(2))
                .andExpect(jsonPath("$.data[0].lastClose").value(201.15))
                // 가격 없는 종목은 lastClose 가 null(키는 있고 값은 null)로 내려가야
                // FE 가 "미제공"을 찍는다. StockCardResponse 는 NON_NULL 을 걸지 않아
                // sector 처럼 null 도 직렬화된다.
                .andExpect(jsonPath("$.data[1].lastClose").value(nullValue()))
                .andExpect(jsonPath("$.meta.pagination.total").value(2));
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

    @Test
    void 주가는_거래일_오름차순_data봉투_필드() throws Exception {
        when(service.prices("NVDA", "2026-01-01", "2026-01-05")).thenReturn(
                ApiResponse.of(List.of(
                        new StockPriceResponse(LocalDate.parse("2026-01-02"),
                                new BigDecimal("178.20"), new BigDecimal("181.00"),
                                new BigDecimal("177.40"), new BigDecimal("180.60"), 41203300L),
                        new StockPriceResponse(LocalDate.parse("2026-01-05"),
                                new BigDecimal("181.00"), new BigDecimal("183.50"),
                                new BigDecimal("180.10"), new BigDecimal("182.90"), 38550100L))));

        mvc.perform(get("/api/v1/stocks/NVDA/prices?from=2026-01-01&to=2026-01-05"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(2))
                .andExpect(jsonPath("$.data[0].tradeDate").value("2026-01-02"))
                .andExpect(jsonPath("$.data[0].close").value(180.60))
                .andExpect(jsonPath("$.data[0].volume").value(41203300))
                .andExpect(jsonPath("$.data[1].tradeDate").value("2026-01-05"));

        verify(service).prices("NVDA", "2026-01-01", "2026-01-05");
    }

    @Test
    void 티커는_있으나_구간에_데이터_없으면_200_빈data() throws Exception {
        // 🔴 없는 티커(404)와 구분 — 여기선 티커가 있고 그 구간만 비었다.
        when(service.prices(eq("NVDA"), any(), any())).thenReturn(ApiResponse.of(List.of()));

        mvc.perform(get("/api/v1/stocks/NVDA/prices?from=1990-01-01&to=1990-12-31"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").isArray())
                .andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    void 없는_종목_주가는_404() throws Exception {
        when(service.prices(eq("ZZZZ"), any(), any()))
                .thenThrow(ApiException.notFound("stock ZZZZ not found"));

        mvc.perform(get("/api/v1/stocks/ZZZZ/prices"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }

    @Test
    void 잘못된_날짜_형식은_400() throws Exception {
        when(service.prices(eq("NVDA"), eq("nope"), any()))
                .thenThrow(ApiException.invalidQuery("from must be YYYY-MM-DD"));

        mvc.perform(get("/api/v1/stocks/NVDA/prices?from=nope"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_QUERY"));
    }
}
