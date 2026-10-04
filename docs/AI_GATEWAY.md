# AI 게이트웨이 설정

외부 AI 워커는 기본 꺼짐입니다. 화면 mock 모드는 게이트웨이 없이 실행됩니다.

## 백엔드

로컬 .env에서 LLM_GATEWAY_BASE_URL을 자신의 게이트웨이 루트로, LLM_GATEWAY_KEY를 해당 게이트웨이의 인증 키로 설정합니다. 예시 도메인은 실제 서비스가 아닙니다.

클라이언트가 기대하는 전달 경로는 다음과 같습니다.

- /api.openai.com/v1/embeddings
- /api.openai.com/v1/chat/completions
- /api.anthropic.com/v1/messages

OpenAI 경로는 Authorization: Bearer <key>, Anthropic 경로는 x-api-key: <key>와 anthropic-version 헤더를 사용합니다. 이 경로를 제공하는 프록시가 필요합니다. 제공사 API를 직접 호출하려면 클라이언트의 경로·인증 처리를 해당 제공사의 계약에 맞게 변경해야 합니다.

워커의 enabled 설정과 호출 예산은 .env.example을 참고하세요.

## Python 도구

종목 임베딩 도구는 LLM_GATEWAY_API_KEY와 LLM_GATEWAY_BASE_URL을 사용합니다. 이때 BASE_URL에는 /api.openai.com/v1까지 포함합니다. 백엔드와 Python을 함께 실행한다면 별도 셸이나 실행 환경에서 각 경로를 설정하세요.

ai/ 실험과 tools/의 일부 일회성 스크립트는 각 파일에 게이트웨이 경로가 명시되어 있습니다. 실행 전 자신의 게이트웨이와 모델로 설정하고 입력 데이터·예산을 확인하세요. 예시 주소와 과거 실험 기록만으로는 AI 요청이 실행되지 않습니다.

키와 .env는 Git에 커밋하지 않습니다.
