package io.wikipulse.backend.stock;

import org.springframework.data.jpa.repository.JpaRepository;

public interface StockRepository extends JpaRepository<Stock, String> {
    // 기본 findById(ticker) 로 충분하다. 검색·매칭은 파이프라인 몫이다.
}
