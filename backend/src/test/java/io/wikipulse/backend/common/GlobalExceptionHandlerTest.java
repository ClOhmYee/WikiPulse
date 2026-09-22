package io.wikipulse.backend.common;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.wikipulse.backend.issue.IssueController;
import io.wikipulse.backend.issue.IssueService;
import io.wikipulse.backend.issue.PulseMapService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 오류 봉투 계약 (API 명세 v0.3 §1.1). DB 없이 웹 레이어만 본다.
 *
 * <p>🔴 매핑 없는 경로가 500 으로 나가던 것을 고정한다 (2026-09-18 실측: 운영에서
 * `/api/v1/nonexistent` 가 500 INTERNAL 이었다). 오타 하나가 서버 오류로 보이면 FE 는
 * 백엔드 로그부터 뒤진다 — 클라이언트 잘못과 서버 잘못은 갈라 줘야 디버깅 방향이 선다.
 */
@org.springframework.context.annotation.Import(io.wikipulse.backend.account.SecurityConfig.class)
@WebMvcTest(IssueController.class)
class GlobalExceptionHandlerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    IssueService service;

    @MockitoBean
    PulseMapService pulseMapService;

    @Test
    void 매핑없는_경로는_404_오류봉투다() throws Exception {
        mvc.perform(get("/api/v1/nonexistent"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }

    @Test
    void 존재하는_접두사_아래_오타도_404다() throws Exception {
        // `/api/v1/pulse/snapshots` 처럼 실제로 없는 경로를 부른 사례가 이 모양이었다.
        mvc.perform(get("/api/v1/issues/snapshots/typo/deeper"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("NOT_FOUND"));
    }
}
