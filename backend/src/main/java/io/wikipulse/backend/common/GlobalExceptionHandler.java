package io.wikipulse.backend.common;

import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 예외를 API 명세 v0.3 §1.1 오류 봉투로 바꾼다.
 *
 * <pre>{ "error": { "code": "NOT_FOUND", "message": "…" } }</pre>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<Object> handleApi(ApiException ex) {
        return body(ex.code(), ex.getMessage());
    }

    /** 쿼리 파라미터 타입 불일치(예: limit=abc)는 INVALID_QUERY 400. */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Object> handleTypeMismatch(MethodArgumentTypeMismatchException ex) {
        return body(ApiException.Code.INVALID_QUERY,
                "parameter '%s' has invalid value".formatted(ex.getName()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Object> handleValidation(MethodArgumentNotValidException ex) {
        String detail = ex.getBindingResult().getFieldErrors().stream()
                .findFirst()
                .map(f -> "%s %s".formatted(f.getField(), f.getDefaultMessage()))
                .orElse("invalid request");
        return body(ApiException.Code.INVALID_QUERY, detail);
    }

    /**
     * 매핑되지 않은 경로는 404 다.
     *
     * <p>🔴 ~~아래 마지막 그물이 500 INTERNAL 로 내보냈다~~ (2026-09-18 실측: `/api/v1/nonexistent`
     * -> 500). Spring Boot 3 는 핸들러가 없는 요청을 정적 리소스 조회로 넘기고, 거기서
     * {@link NoResourceFoundException} 이 난다. 그게 Exception 그물에 걸려 서버 오류로 둔갑했다.
     *
     * <p>오타 하나가 500 으로 보이면 FE 는 서버가 고장 난 줄 알고 백엔드 로그부터 뒤진다.
     * 클라이언트 잘못(404)과 서버 잘못(500)은 갈라 줘야 디버깅 방향이 선다.
     */
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<Object> handleNoResource(NoResourceFoundException ex) {
        return body(ApiException.Code.NOT_FOUND, "no endpoint for this path");
    }

    /**
     * 마지막 그물. 스택트레이스를 밖으로 흘리지 않는다.
     *
     * <p>🔴 <b>대신 서버 로그에는 반드시 남긴다.</b> 여태 여기서 아무것도 안 찍어서, 500 이
     * 나도 원인이 로그에 없었다 — 2026-09-18 에 EC2 API 가 전부 500 이었을 때 Hibernate 가
     * 자체적으로 찍은 `permission denied for table cluster_snapshot` 한 줄이 없었으면 원인을
     * 못 찾았을 것이다. 응답은 그대로 "internal error" 만 내보낸다.
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Object> handleUnexpected(Exception ex) {
        log.error("처리되지 않은 예외 — 500 으로 응답한다", ex);
        return body(ApiException.Code.INTERNAL, "internal error");
    }

    private ResponseEntity<Object> body(ApiException.Code code, String message) {
        return ResponseEntity.status(code.status).body(
                Map.of("error", Map.of("code", code.name(), "message", message)));
    }
}
