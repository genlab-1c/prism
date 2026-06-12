# Инструмент осей S·O: BSL Language Server поверх JRE 21 (пиновая версия).
# JRE здесь — базовый слой образа (BSL LS это Java-приложение), а не отдельный контейнер.
# Сборка:   docker build -t prism-bsl-ls:0.29.0 -f docker/bsl-ls.Dockerfile .
# Запуск (так его зовёт DockerBSL — только статический парс, без сети, код read-only):
#   docker run --rm --network=none -v <src>:/src:ro -v <out>:/out \
#     prism-bsl-ls:0.29.0 analyze --silent --srcDir /src --outputDir /out --reporter json
FROM eclipse-temurin:21-jre-jammy

ARG BSL_LS_VERSION=0.29.0
ADD https://github.com/1c-syntax/bsl-language-server/releases/download/v${BSL_LS_VERSION}/bsl-language-server-${BSL_LS_VERSION}-exec.jar \
    /opt/bsl-language-server.jar

ENV HOME=/tmp
USER 10001
ENTRYPOINT ["java", "-jar", "/opt/bsl-language-server.jar"]
