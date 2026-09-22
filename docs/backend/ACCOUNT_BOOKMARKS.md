# 이메일 계정과 보관함

WP-211. 기존 로그인 UI MR !174가 병합된 develop에서 구현했다.

## 인증 계약

같은 출처의 `/api/v1` 프록시를 사용한다. Bearer 토큰은 반환하거나 브라우저 저장소에 저장하지 않는다.

| 요청 | 성공 응답의 data |
| --- | --- |
| GET /auth/csrf | `{token, headerName}` |
| POST /auth/signup | `{id, email, displayName}`, HTTP 201 |
| POST /auth/login | `{member: {id, email, displayName}}` |
| POST /auth/logout | HTTP 204 |
| GET /me | `{id, email, displayName}` |
| GET /me/saved-state | `{issueIds: string[], tickers: string[]}` |
| GET /me/bookmarks | 이슈 카드 배열: id, label, summary, pulseScore, status, source, snapshotTs, memberCount, stockCount, addedAt |
| GET /me/watchlist | 종목 카드 배열: ticker, name, exchange, sector, issueCount, addedAt |
| PUT / DELETE /me/bookmarks/{clusterId} | HTTP 204 |
| PUT / DELETE /me/watchlist/{ticker} | HTTP 204 |

회원가입 본문은 `{email,password,displayName}`, 로그인은 `{email,password}`다.
이메일은 trim/lowercase, 닉네임은 trim 후 1~40자다. 이메일 최대 254자,
비밀번호는 8자 이상·UTF-8 72바이트 이하이고 BCrypt cost 12로 저장한다.
비밀번호를 자르지 않으며 기존 password_hash가 NULL인 회원은 로그인할 수 없다.

변경 요청 전 `/auth/csrf`를 호출해 반환된 headerName/token을 헤더로 보낸다.
로그인 시 세션 ID 및 CSRF 토큰이 교체되므로 이전 토큰을 재사용하지 않는다.
인증 오류 401, CSRF 오류 403, 잘못된 입력 400, 이메일 중복 409, 없는 저장 대상 404다.
오류 응답은 기존 `{error:{code,message}}` 형식이며 리다이렉트/HTML을 반환하지 않는다.

목록은 `q`(최대 200자, 대소문자 무시 부분 일치), `offset`(기본 0),
`limit`(기본 20, 최대 100)을 받는다. `meta.pagination`은 기존 계약을 따른다.
저장 시각 내림차순, 동일 시각에는 ID/티커 오름차순이다.
이슈 검색은 제목·요약, 종목 검색은 티커·회사명을 사용한다.

## 세션·데이터

- `WIKIPULSE_SESSION`: HttpOnly, SameSite=Lax, host-only, Path=/.
- 운영 `SESSION_COOKIE_SECURE=true`, 로컬 HTTP 실행은 명시적으로 false.
- `SESSION_TIMEOUT=24h`: 마지막 요청부터 24시간. 인증된 요청에 쿠키 만료도 갱신한다.
- Spring Session JDBC가 세션을 PostgreSQL에 저장한다. JVM 재시작 후에도 복원되며 만료 세션은 주기적으로 정리한다.
- 사용자 ID는 서버 SecurityContext에서만 추출한다. 세션에는 비밀번호·해시가 들어가지 않는다.
- 이슈 북마크는 저장한 clusterId를 참조한다. 같은 사건의 최신 스냅샷으로 교체하거나 보고서 본문을 복제하지 않는다.
- member/대상 FK 삭제 시 저장 연결도 삭제된다. 중복 저장·반복 해제는 멱등이다.
- 예전 localStorage 항목은 읽어오거나 이전·삭제하지 않는다. 예시 데이터는 실계정에 저장하지 않는다.
- 로그인 팝업 취소 시 저장 의도를 버린다. 가입 화면을 거쳐 로그인하면 원래 추가 요청을 한 번 수행한다.
- 회원 변경·로그아웃 시 요청을 취소하고 개인 화면/저장 캐시를 비운다. 다른 탭의 계정 변경도 BroadcastChannel로 통지한다.

## 적용 순서

1. V15 이전에 `SELECT lower(btrim(email)), count(*) FROM member GROUP BY 1 HAVING count(*) > 1`로 중복을 확인한다. 충돌은 계정 소유자를 확인해 해결하고 임의 병합하지 않는다. V15 자체도 충돌 시 원자적으로 실패한다.
2. 기존 `db/apply_migrations.py --grant-role <앱 역할>` 절차로 V15를 적용한다. 새 테이블·시퀀스 DML 권한도 확인한다. `spring.session.jdbc.initialize-schema=never`를 유지한다.
3. 백엔드와 프론트엔드를 함께 배포한다. 같은 출처의 HTTPS 프록시와 Secure 쿠키를 확인한다. 로컬 Docker compose만 기본 false다.
4. 로그인·저장·로그아웃 후 `/me` 401과 health를 점검한다. 이전 클라이언트의 Bearer 계약과 호환되지 않으므로 클라이언트 새로고침이 필요하다.

자동 병합·운영 배포는 하지 않는다. 롤백 시 V15 테이블을 삭제하지 말고 앱 버전만 되돌린다.
이메일 인증, 재설정, 소셜 로그인, 회원정보 수정·탈퇴는 별도 범위다.

## 재현 검증

```sh
cd backend && ./gradlew test bootJar && cd ..
cd frontend && npm ci && npx playwright install chromium && cd ..
uv run --with pgserver --with 'psycopg[binary]' python tools/test_account_e2e.py --browser
```

Java 17이 필요하다. Windows에서는 `gradlew.bat`, `npm.cmd`를 사용한다.
테스트는 외부 DATABASE_URL을 사용하지 않고 새 임시 PostgreSQL을 생성한다.
workers는 모두 false다. 신규/업그레이드 스키마, 이메일 충돌, CSRF, 계정 격리,
동시 저장, 서버·브라우저 재시작, 짧은 세션의 갱신·만료, 운영 쿠키 속성을 검증한다.
쓰기 실패 화면만 HTTP 500을 주입하며 나머지 계정 브라우저 흐름은 실제 API다.
일반 `e2e/auth.spec.js`는 별도의 인터셉트 UI 회귀 검사다. 운영 실데이터 검증을 의미하지 않는다.

기술 근거: [Spring Session JDBC](https://docs.spring.io/spring-session/reference/configuration/jdbc.html),
[Spring Security 세션 관리](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html).
