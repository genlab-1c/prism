#!/usr/bin/env bash
# Установка BSL Language Server (инструмент осей S и O, категория A) в tools/.
# Jar в git не коммитится (tools/ в .gitignore) — скрипт ставит пиновую версию
# с официального релиза. Нужен Java 21+ (jar собран под Java 21). Запуск:
#   ./tools/get-bsl-ls.sh
set -euo pipefail

VERSION="0.29.0"
ASSET="bsl-language-server-${VERSION}-exec.jar"
URL="https://github.com/1c-syntax/bsl-language-server/releases/download/v${VERSION}/${ASSET}"

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/$ASSET"

if [ -f "$DEST" ]; then
    echo "уже установлен: $ASSET"
    exit 0
fi

echo "скачиваю $ASSET (~115 МБ) …"
curl -fL --retry 3 -o "$DEST" "$URL"
echo "готово: $DEST"
echo "java 21+ требуется; при нестандартном пути задайте PRISM_JAVA=/путь/к/java"
