# 프론트엔드 개발 서버 (Vite). 핫 리로드로 개발용.
#
# 프로덕션 정적 빌드가 필요하면 별도 스테이지를 추가한다. 지금은 개발 스택이라
# vite dev server 로 띄운다. --host 0.0.0.0 으로 컨테이너 밖에서 접근되게 한다
# (package.json 기본은 127.0.0.1 이라 컨테이너에선 안 열린다).
FROM node:20-alpine
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
