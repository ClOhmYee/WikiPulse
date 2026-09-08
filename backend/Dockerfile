# Spring Boot 백엔드. 빌드와 실행을 분리해 최종 이미지를 작게 유지한다.

# --- 빌드 ---
FROM eclipse-temurin:17-jdk AS build
WORKDIR /app

# gradle 래퍼와 설정을 먼저 복사해 의존성 레이어를 캐시한다.
# 소스만 바뀌면 의존성을 다시 안 받는다.
COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew dependencies --no-daemon || true

COPY src ./src
RUN ./gradlew bootJar --no-daemon

# --- 실행 ---
FROM eclipse-temurin:17-jre
WORKDIR /app
# 이름이 버전에 안 묶이게 plain 이 아닌 부트 jar 만 집는다.
COPY --from=build /app/build/libs/*-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
