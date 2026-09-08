package io.wikipulse.backend.stock;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.wikipulse.backend.common.NotFoundException;
import io.wikipulse.backend.issue.dto.IssueCardResponse;
import io.wikipulse.backend.stock.dto.StockResponse;
import java.time.Instant;
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
    void 종목_상세를_준다() throws Exception {
        when(service.get("NEE")).thenReturn(new StockResponse(
                "NEE", "NextEra Energy", "NYSE", "Utilities", "플로리다 전력·재생에너지"));

        mvc.perform(get("/api/stocks/NEE"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.ticker").value("NEE"))
                .andExpect(jsonPath("$.exchange").value("NYSE"))
                .andExpect(jsonPath("$.sector").value("Utilities"));
    }

    @Test
    void 종목이_걸린_이슈_목록을_준다() throws Exception {
        when(service.issuesFor("NEE")).thenReturn(List.of(
                new IssueCardResponse(1L, "Hurricane Milton 상륙", 9.7,
                        "CONFIRMED", Instant.parse("2024-10-10T13:00:00Z"))));

        mvc.perform(get("/api/stocks/NEE/issues"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[0].label").value("Hurricane Milton 상륙"));
    }

    @Test
    void 없는_종목은_404() throws Exception {
        when(service.get("ZZZZ")).thenThrow(new NotFoundException("종목 ZZZZ 없음"));

        mvc.perform(get("/api/stocks/ZZZZ"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }
}
