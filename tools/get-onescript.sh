#!/usr/bin/env bash
# Установка OneScript (движок исполнения категории A, ось M) в tools/onescript/.
# Бинари в git не коммитятся (tools/ в .gitignore) — этот скрипт ставит пиновую
# версию с официального релиза. Запуск:  ./tools/get-onescript.sh
set -euo pipefail

VERSION="2.0.1"
ASSET="OneScript-${VERSION}-linux-x64.zip"
URL="https://github.com/EvilBeaver/OneScript/releases/download/v${VERSION}/${ASSET}"

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/onescript"

if [ -x "$DEST/bin/oscript" ]; then
    echo "уже установлен: $("$DEST/bin/oscript" --version 2>/dev/null | head -1)"
    exit 0
fi

echo "скачиваю $ASSET …"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fL --retry 3 -o "$TMP/$ASSET" "$URL"

echo "распаковываю в $DEST …"
mkdir -p "$DEST"
unzip -q "$TMP/$ASSET" -d "$DEST"
# в архиве bin/ лежит в корне либо во вложенной папке — нормализуем
if [ ! -d "$DEST/bin" ]; then
    INNER="$(find "$DEST" -maxdepth 2 -type d -name bin | head -1)"
    [ -n "$INNER" ] && mv "$(dirname "$INNER")"/* "$DEST/" || true
fi
chmod +x "$DEST/bin/oscript"

echo "готово: $("$DEST/bin/oscript" --version 2>/dev/null | head -1)"
