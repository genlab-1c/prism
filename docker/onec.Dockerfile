# Учебная платформа 1С 8.3.27 (Linux, толстый клиент) — оси M/P категории B:
# headless-исполнение кандидатов против синтетической базы (harness/execute/onec).
#
# ЛИЦЕНЗИЯ (жёсткое правило проекта): дистрибутив платформы НЕ редистрибутируется —
# ни в git, ни в образах. Скачай учебную версию сам с developer.1c.ru и положи
# setup-training-8.3.27.1508-x86_64.run в tools/1ce-training/ (каталог в .gitignore).
# Учебной версии не нужна активация лицензии (отличие от dev-дистрибутива).
#
# Сборка (контекст — каталог с .run):
#   docker build -f docker/onec.Dockerfile -t prism-onec tools/1ce-training
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
# Зависимости толстого клиента 1С (GUI-библиотеки нужны даже для batch под Xvfb) + Xvfb + локаль
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 fontconfig libgsf-1-114 libglib2.0-0 libkrb5-3 libgomp1 \
    libx11-6 libxext6 libxrender1 libxtst6 libxi6 libxinerama1 libxrandr2 \
    libatk1.0-0 libgtk-3-0 libwebkit2gtk-4.0-37 libglu1-mesa \
    locales xvfb \
    && sed -i 's/# ru_RU.UTF-8/ru_RU.UTF-8/' /etc/locale.gen && locale-gen \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=ru_RU.UTF-8 LC_ALL=ru_RU.UTF-8

# Установка платформы (внутри контейнера мы root → ошибки «нужен суперпользователь» нет)
COPY setup-training-8.3.27.1508-x86_64.run /tmp/setup.run
RUN chmod +x /tmp/setup.run \
    && /tmp/setup.run --mode unattended --enable-components client_full,ru \
    && rm /tmp/setup.run

# Бинарь учебного толстого клиента: /opt/1cv8t/x86_64/<версия>/1cv8t
ENV ONEC_VER=8.3.27.1508
ENV PATH="/opt/1cv8t/x86_64/${ONEC_VER}:${PATH}"

# Обёртка: запуск 1cv8t под виртуальным дисплеем (headless batch).
RUN printf '#!/bin/bash\nexport DISPLAY=:99\nXvfb :99 -screen 0 1280x900x24 >/dev/null 2>&1 &\nsleep 1\nexec "$@"\n' \
    > /usr/local/bin/xvfb-run-1c && chmod +x /usr/local/bin/xvfb-run-1c
WORKDIR /prism
