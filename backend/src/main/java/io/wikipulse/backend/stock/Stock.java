package io.wikipulse.backend.stock;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * stock 테이블. 미국 3대 거래소 보통주 약 5,400종목.
 *
 * <p>embedding(vector) 컬럼은 JPA 로 매핑하지 않는다 — 매칭·검색은 파이프라인이
 * 네이티브 SQL 로 다루고, API 는 티커·이름·거래소·설명만 노출한다.
 * 스키마: db/migrations/V1__initial_schema.sql
 */
@Entity
@Table(name = "stock")
public class Stock {

    @Id
    @Column(name = "ticker")
    private String ticker;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "exchange", nullable = false)
    private String exchange;

    @Column(name = "sector")
    private String sector;

    @Column(name = "business_summary")
    private String businessSummary;

    protected Stock() {
    }

    public String getTicker() {
        return ticker;
    }

    public String getName() {
        return name;
    }

    public String getExchange() {
        return exchange;
    }

    public String getSector() {
        return sector;
    }

    public String getBusinessSummary() {
        return businessSummary;
    }
}
