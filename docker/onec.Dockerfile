# Учебная платформа 1С (Linux, толстый клиент) — оси M/P категории B:
# headless-исполнение кандидатов против синтетической базы (harness/execute/onec).
#
# ЛИЦЕНЗИЯ (жёсткое правило проекта): дистрибутив платформы НЕ редистрибутируется —
# ни в git, ни в образах. Скачай учебную версию сам с developer.1c.ru и положи .run
# в tools/1ce-training/ (каталог в .gitignore). Версия НЕ зашита: подойдёт любой
# setup-*.run (8.3.2x). Учебной версии не нужна активация лицензии.
#
# Сборка — командой `make image-onec` (найдёт дистрибутив в tools/ и соберёт образ).
# Вручную (контекст — каталог с .run):
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

# Установка платформы (внутри контейнера мы root → ошибки «нужен суперпользователь» нет).
# Имя и версия дистрибутива НЕ зашиты: берём любой *.run из контекста сборки.
COPY *.run /tmp/dist/
RUN run="$(ls /tmp/dist/*.run | head -1)" \
    && chmod +x "$run" \
    && "$run" --mode unattended --enable-components client_full,ru \
    && rm -rf /tmp/dist

# Бинарь учебного толстого клиента: /opt/1cv8t/x86_64/<версия>/1cv8t. Версия не зашита —
# делаем стабильную ссылку /opt/1cv8t/current → найденная версия, её и кладём в PATH.
RUN ln -s "$(dirname "$(find /opt/1cv8t -type f -name 1cv8t | head -1)")" /opt/1cv8t/current
ENV PATH="/opt/1cv8t/current:${PATH}"

# Обёртка: запуск 1cv8t под виртуальным дисплеем (headless batch).
RUN printf '#!/bin/bash\nexport DISPLAY=:99\nXvfb :99 -screen 0 1280x900x24 >/dev/null 2>&1 &\nsleep 1\nexec "$@"\n' \
    > /usr/local/bin/xvfb-run-1c && chmod +x /usr/local/bin/xvfb-run-1c
WORKDIR /prism
