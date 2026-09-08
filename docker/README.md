# 로컬 개발 스택 (Docker Compose)

`WP-63`. 팀원마다 파이썬·JDK·PostgreSQL 설치가 달라 생기는 의존성
문제를 컨테이너로 없앤다. `docker compose up` 하나로 전원이 같은 환경.

명세: [docs/requirements-v0.1.md](../docs/requirements-v0.1.md) §7

```
docker compose up -d postgres kafka        # 인프라만 (백엔드·파이썬 로컬 개발)
docker compose up -d                        # postgres + kafka + backend + frontend
docker compose --profile pipeline up -d     # producer·spark 까지
docker compose down                         # 정지 (데이터 유지)
docker compose down -v                       # 정지 + 데이터 삭제 (스키마 재적재)
```

`.env.example` 을 `.env` 로 복사해서 채운다 (`.env` 는 gitignore).

## 서비스

| 서비스 | 포트 | 무엇 | 프로필 |
| --- | --- | --- | --- |
| postgres | 5432 | PostgreSQL 16 + pgvector. 스키마 자동 적재 | 기본 |
| kafka | 9092 | Kafka KRaft 단일 브로커 | 기본 |
| backend | 8080 | Spring Boot. `ddl-auto=validate` | 기본 |
| frontend | 5174 | Vite dev server | 기본 |
| producer | — | EventStreams → Kafka | `pipeline` |
| spark | — | edit_windows 스트리밍 | `pipeline` |

## 왜 이렇게 없애나

- **파이썬 3.11 고정.** PySpark 3.5 는 3.12+ 에서 워커가 죽는다. 컨테이너가
  3.11 을 못박아 팀원이 3.13/3.14 를 깔아도 안 깨진다.
- **PostgreSQL + pgvector 를 각자 안 깐다.** 이미지가 확장까지 들고 온다.
  `db/migrations` 가 최초 기동 때 자동 적재돼 스키마가 항상 최신이다.
- **JDK·Gradle 을 각자 안 깐다.** 백엔드 이미지가 빌드·실행을 다 한다.
- **시간대 문제 없음.** 임베디드 PG(pgserver)에서 겪던 TimeZone 오류가
  실 PostgreSQL 에는 없다. `TZ=UTC` 로 못박았다.

## 검증 (2026-09-08, 이 스택으로 직접 확인)

- postgres·kafka 헬스체크 통과. **스키마 17개 테이블 + pgvector 자동 적재.**
- 백엔드 이미지 빌드(컨테이너 안 gradle bootJar) 후 실 PostgreSQL 에
  `ddl-auto=validate` 로 기동 성공 — 엔티티가 스키마와 정확히 맞는다.
- 실제 HTTP: `/actuator/health` UP, `/api/issues` 빈 배열 → 시드 후 카드,
  `/api/issues/1` 관련종목 조인(NEE tier BOTH lift 10.5), `/api/stocks/NEE/issues`.

## 스키마를 고쳤을 때

`db/migrations` 는 볼륨이 비어 있을 때만(최초 1회) 적재된다. 스키마를 바꿨으면:

```
docker compose down -v      # 데이터 볼륨 삭제
docker compose up -d postgres
```

운영에서는 마이그레이션 도구(Flyway 등)로 증분 적용한다 — 그건 별도 결정
사항이다(`db/` README).

## 운영과 다른 점

이건 **개발용**이다. 전부 단일 인스턴스·복제 1이라 EC2 실물 구성
(`WP-26`·`-29`, 2노드·복제 2)과 다르다. 프론트도 dev server(핫
리로드)라 프로덕션 정적 빌드가 아니다.

⚠️ Docker Desktop(또는 Engine)이 필요하다. 작성 PC 에 Docker 를 설치해
(4.90.0) 이 스택을 실제로 띄워 검증했다.
