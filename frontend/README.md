# WikiPulse 프론트엔드

React 19·Vite 기반 온보딩, 펄스맵, 이슈·종목 탐색, 계정·보관함 화면입니다.

## 실행

```sh
npm ci
npm run dev
```

기본 mock 모드에서는 백엔드 없이 `http://127.0.0.1:5174/#/pulse`에서 화면을 확인할 수 있습니다. API 모드는 `.env.example`을 `.env`로 복사한 뒤 `VITE_DATA_SOURCE=api`로 설정합니다.

회원가입·로그인·로그아웃과 내 정보·이슈 북마크·관심종목은 Spring 세션 API에 연결됩니다. 인증은 HttpOnly 쿠키와 CSRF 토큰을 사용합니다. 토론 UI는 로컬 시연용 프로토타입입니다.

이슈 기록 탐색은 API 모드와 `VITE_ISSUE_HISTORY_ENABLED=true`가 모두 필요합니다. Vite 환경변수는 빌드 시 고정됩니다.

펄스맵은 SVG·d3-force를 사용하며, 온보딩의 입체 그래픽은 지연 로딩한 React Three Fiber·Three.js를 사용합니다.

## 검증

```sh
npm run lint
npm run test:data
npm run build
```

상세 데이터 계약은 [API 명세](../docs/api-v1.md), [데이터 설정](../docs/frontend/DATA_SOURCE.md), [합성 데이터 범위](../docs/frontend/MOCK_HISTORY.md)를 참고하세요.
