package io.wikipulse.backend.common;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/**
 * 예외를 API 명세 v0.1 §1.1 오류 봉투로 바꾼다.
 *
 * <pre>{ "error": { "code": "NOT_FOUND", "message": "…" } }</pre>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

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

    /** 마지막 그물. 스택트레이스를 밖으로 흘리지 않는다. */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Object> handleUnexpected(Exception ex) {
        return body(ApiException.Code.INTERNAL, "internal error");
    }

    private ResponseEntity<Object> body(ApiException.Code code, String message) {
        return ResponseEntity.status(code.status).body(
                Map.of("error", Map.of("code", code.name(), "message", message)));
    }
}
