# Песочница исполнения категории A: OneScript (пиновая версия) поверх slim-образа.
# Сборка:   docker build -t prism-onescript:2.0.1 -f docker/onescript.Dockerfile .
# Запуск (так его зовёт DockerRunner — без сети, с лимитами, код read-only):
#   docker run --rm --network=none --memory=256m --cpus=1 \
#     -v <dir>:/sandbox:ro prism-onescript:2.0.1 oscript /sandbox/<file>.os
FROM debian:bookworm-slim

ARG ONESCRIPT_VERSION=2.0.1

# libicu обязателен: OneScript = .NET self-contained, без ICU рантайм падает (FailFast)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates libicu72 \
    && curl -fL --retry 3 -o /tmp/os.zip \
       "https://github.com/EvilBeaver/OneScript/releases/download/v${ONESCRIPT_VERSION}/OneScript-${ONESCRIPT_VERSION}-linux-x64.zip" \
    && mkdir -p /opt/onescript \
    && unzip -q /tmp/os.zip -d /opt/onescript \
    && chmod +x /opt/onescript/bin/oscript \
    && ln -s /opt/onescript/bin/oscript /usr/local/bin/oscript \
    && rm /tmp/os.zip \
    && apt-get purge -y curl unzip && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# непривилегированный пользователь — кандидатский код не должен бегать под root
RUN useradd -m -u 10001 sandbox
USER sandbox
WORKDIR /sandbox
