# backend — Issue / Stock REST API

Spring Boot 백엔드 (`WP-36`). 데이터 모델 v1 위의 읽기 API 골격이다.

명세: [docs/requirements-v0.2.md](../docs/requirements-v0.2.md) §2, §3.1

## 스택

- Spring Boot **3.5.16**, Java 17, Gradle 8.14 (wrapper 포함)
- Spring Web MVC · Data JPA · Validation · Actuator
- PostgreSQL (스키마는 `db/` 가 소유, 여기는 `ddl-auto=validate`)

Boot 3.5 를 골랐다. Initializr 기본은 4.x(2025-11 GA)지만, 프로젝트 교보재·팀
친숙도가 3.x 기준이라 안정 라인으로 내렸다. 3.5.16 은 3.5 계열 마지막
OSS 패치다(2026-06). LTS 급 지원이 필요하면 상용(HeroDevs 등) 또는 4.x 로.

## 엔드포인트

| 메서드 · 경로 | 설명 |
| --- | --- |
| `GET /api/issues?snapshotTs=&status=&limit=` | 이슈 피드 / 버블맵. snapshotTs 없으면 최근 LIVE, 있으면 그 시점(리플레이) |
| `GET /api/issues/{id}` | 이슈 상세 — 멤버 문서·요약·관련 종목 |
| `GET /api/stocks/{ticker}` | 종목 상세 |
| `GET /api/stocks/{ticker}/issues` | 그 종목이 걸린 이슈들 |
| `GET /actuator/health` | 헬스체크 |

피드와 버블맵은 같은 데이터를 카드/버블로 그릴 뿐이라 한 엔드포인트를 쓴다.

### 응답 형태 (FE 계약)

```
GET /api/issues/1
{
  "id": 1,
  "label": "Hurricane Milton 상륙",     // 확정 전엔 null → FE 가 대표 문서명 사용
  "pulseScore": 9.7,
  "status": "CONFIRMED",                 // DETECTED / VERIFYING / CONFIRMED
  "source": "live",                      // live / replay
  "snapshotTs": "2024-10-10T13:00:00Z",
  "memberTitles": ["Hurricane Milton", "Florida"],
  "summary": "...",
  "relatedStocks": [
    {
      "ticker": "NEE", "name": "NextEra Energy", "exchange": "NYSE",
      "tier": "BOTH",                    // BOTH / GDELT_ONLY / EMBEDDING_ONLY
      "matchPath": "REGION",             // 근거 종류
      "similarity": null, "gdeltLift": 10.5,
      "rationale": "플로리다 전력망 운영사"  // 근거 문장. 상관계수가 아니다 (§9)
    }
  ]
}
```

파이프라인이 아직 안 채운 이슈는 `memberTitles`·`relatedStocks` 가 빈 배열로
나간다. FE 는 빈 배열을 "없음" 으로 처리한다.

## 설계

**스키마를 소유하지 않는다.** `db/migrations` 가 정본이고 JPA 는 `validate` 만
한다 — 엔티티가 실제 테이블과 어긋나면 기동 때 걸린다. 마이그레이션 도구
확정은 `db/` MR 사항이다.

**읽기 전용 테이블은 네이티브 프로젝션으로 읽는다.** `cluster_member` ·
`cluster_stock` · `issue_report` 는 API 가 읽기만 하고 파이프라인이 쓴다.
JPA 엔티티를 각각 두는 대신 `IssueQueryRepository` 가 네이티브 SQL 로 필요한
형태를 바로 뽑는다.

**엔티티는 CRUD 를 열지 않는다.** protected 기본 생성자, getter 만. 이 API 는
읽기 골격이다 — 쓰기는 파이프라인이 직접 DB 에 한다.

## 실행

```bash
export DATABASE_URL=jdbc:postgresql://localhost:5432/wikipulse
export DB_USER=wikipulse DB_PASSWORD=...
./gradlew bootRun
```

`db/` 스키마가 먼저 적재돼 있어야 기동한다(validate).

## 검증

```bash
./gradlew test          # WebMvcTest 슬라이스 7개
```

- **웹 슬라이스 7개** — DB 없이 웹 레이어만 띄우고 서비스는 mock. 각 엔드포인트의
  JSON 형태·404·빈 배열을 검증한다. FE 계약이 바뀌면 여기서 걸린다.
- **네이티브 쿼리 4개** — 진짜 PostgreSQL 에 스키마+시드를 넣고 API 가 쓰는
  네이티브 SQL(멤버·요약·관련종목 조인·종목별 이슈)을 직접 돌려 확인했다
  (2026-09-08). `cluster_stock ⋈ stock` 조인이 tier·lift 를 정확히 반환.
- **엔티티 컬럼** 을 스키마와 대조했다.

⚠️ 앱을 실제로 기동해 `validate` 통과까지 보는 건 로컬 PostgreSQL 이 필요하다.
임베디드 PG(pgserver)는 시간대 데이터가 없어 JDBC 기동이 막힌다 — 실제 PG 에는
없는 제약이다.

## 아직 안 한 것

- **인증** — 회원·관심종목 API 는 인증 스펙 확정 후. 지금은 이슈·종목 읽기만.
- **주가 그래프** `GET /api/stocks/{ticker}/prices` — `WP-10` 에픽.
- **쓰기 경로** — 전부 파이프라인이 DB 에 직접 쓴다. API 는 읽기다.
- **페이지네이션** — 지금은 limit 만. 커서 페이징은 목록이 커지면.
