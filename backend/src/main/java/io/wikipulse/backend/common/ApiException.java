package io.wikipulse.backend.common;

import org.springframework.http.HttpStatus;

/**
 * API 명세 v0.2 §1.1 의 오류 코드로 매핑되는 예외.
 *
 * <p>{@code {error: {code, message}}} 로 나간다. message 는 개발자용 영문 —
 * 사용자 한국어 문구는 FE 가 code 로 고른다.
 */
public class ApiException extends RuntimeException {

    public enum Code {
        INVALID_QUERY(HttpStatus.BAD_REQUEST),
        UNAUTHORIZED(HttpStatus.UNAUTHORIZED),
        NOT_FOUND(HttpStatus.NOT_FOUND),
        INTERNAL(HttpStatus.INTERNAL_SERVER_ERROR);

        public final HttpStatus status;

        Code(HttpStatus status) {
            this.status = status;
        }
    }

    private final Code code;

    public ApiException(Code code, String message) {
        super(message);
        this.code = code;
    }

    public Code code() {
        return code;
    }

    public static ApiException notFound(String message) {
        return new ApiException(Code.NOT_FOUND, message);
    }

    public static ApiException invalidQuery(String message) {
        return new ApiException(Code.INVALID_QUERY, message);
    }
}
