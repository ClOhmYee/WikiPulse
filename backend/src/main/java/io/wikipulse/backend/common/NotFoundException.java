package io.wikipulse.backend.common;

/** 404 로 매핑되는 도메인 예외. GlobalExceptionHandler 가 받는다. */
public class NotFoundException extends RuntimeException {
    public NotFoundException(String message) {
        super(message);
    }
}
