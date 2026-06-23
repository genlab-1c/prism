# PRISM — установка и разработка. `make` без аргументов — список целей.
#
# ДВА ИНСТРУМЕНТА, НЕ ПУТАТЬ:
#   • make  — ПОСТАВИТЬ и РАЗРАБАТЫВАТЬ (окружение, инструменты осей, тесты, линт).
#   • prism — ПОЛЬЗОВАТЬСЯ бенчмарком (prism leaderboard / score / check / generate).
#             У prism свой --help и флаги; make флаги НЕ принимает. `prism` без аргументов
#             печатает шпаргалку. Совет: `source .venv/bin/activate` → зовите prism напрямую.
#
# Окружение управляет uv (https://docs.astral.sh/uv/): `uv sync` собирает .venv из
# pyproject.toml, `uv run <cmd>` запускает в нём. Нет uv? → curl -LsSf https://astral.sh/uv/install.sh | sh
#
# Готовые рецепты установки (по умолчанию код исполняется в Docker — песочница):
#   make setup-all     — ВСЁ в Docker: окружение + образы инструментов (A) + учебная 1С (B)
#   make setup-docker  — окружение + docker-образы инструментов A (без учебной 1С B)
#   make setup         — хостовый dev-режим: инструменты осей на ХОСТ (зови с --runner/--bsl local)

UV    ?= uv
VENV  ?= .venv
# Адрес dev-сервера документации (make docs-serve). Порт 8000 часто занят другим
# приложением — переопредели: make docs-serve DOCS_ADDR=127.0.0.1:8001
DOCS_ADDR ?= 127.0.0.1:8000

ONESCRIPT_IMAGE := prism-onescript:2.0.1
BSL_LS_IMAGE    := prism-bsl-ls:0.29.0
# Учебная 1С для категории B (оси M/P). Дистрибутив приносится свой (НЕ коммитится,
# НЕ редистрибутируется): tools/ в .gitignore. Имя образа = onec.DOCKER_IMAGE.
# Версия НЕ зашита: ищем .run любой версии — в tools/1ce-training/ или прямо в корне tools/.
ONEC_IMAGE := prism-onec:latest
ONEC_DIST  := $(firstword $(wildcard tools/1ce-training/setup-*.run) $(wildcard tools/setup-*.run) $(wildcard tools/1ce-training/*.run) $(wildcard tools/*.run))

# MODE=docker — тумблер песочниц для `make test` (интеграция в контейнерах вместо хоста).
# Для самих прогонов prism песочница выбирается флагом: prism ... --runner/--bsl docker.
ifdef MODE
export PRISM_RUNNER := $(MODE)
export PRISM_BSL    := $(MODE)
endif

.DEFAULT_GOAL := help
.PHONY: help setup setup-all setup-docker venv tools images image-onescript image-bsl-ls image-onec onec-guide test test-fast lint docs docs-serve docs-build clean

help:  ## показать этот список
	@echo "Пользоваться бенчмарком — командой prism (свой --help и флаги):"
	@echo "    prism                       шпаргалка: что делать"
	@echo "    prism leaderboard           посмотреть результаты (мгновенно)"
	@echo "    prism score | check | generate    оценить / проверить / сгенерировать"
	@echo "    prism <команда> --help      все флаги команды"
	@echo ""
	@echo "make — установка и разработка (флаги make НЕ принимает; параметр как VAR=значение):"
	@awk 'BEGIN{FS=":.*?## "} \
		/^##@/{printf "\n  \033[1m%s\033[0m\n", substr($$0,5); next} \
		/^[a-zA-Z_-]+:.*?## /{printf "    \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Установка
setup-all: venv images  ## ВСЁ в Docker (дефолт): окружение + образы инструментов A + учебная 1С B
	@if [ -n "$(ONEC_DIST)" ]; then \
		$(MAKE) --no-print-directory image-onec; \
	else \
		$(MAKE) --no-print-directory onec-guide; \
		printf '  Категория A готова (Docker). Для B выполни шаги выше, затем: make image-onec\n\n'; \
	fi
setup-docker: venv images  ## окружение (uv) + docker-образы инструментов A (без учебной 1С B)
setup: venv tools  ## хостовый dev-режим: инструменты осей на ХОСТ (зови с --runner/--bsl local)

##@ Инструменты осей
tools:  ## OneScript + BSL LS на ХОСТ (bootstrap-скрипты)
	./tools/get-onescript.sh
	./tools/get-bsl-ls.sh
images: image-onescript image-bsl-ls  ## собрать оба docker-образа инструментов
image-onescript:  ## образ песочницы M (OneScript)
	docker build -t $(ONESCRIPT_IMAGE) -f docker/onescript.Dockerfile .
image-bsl-ls:  ## образ инструмента S/O (BSL LS на JRE 21)
	docker build -t $(BSL_LS_IMAGE) -f docker/bsl-ls.Dockerfile .
image-onec:  ## образ учебной 1С для категории B (дистрибутив любой версии в tools/ — см. onec-guide)
	@dist="$(ONEC_DIST)"; \
	if [ -z "$$dist" ]; then $(MAKE) --no-print-directory onec-guide; exit 1; fi; \
	mkdir -p tools/1ce-training; \
	if [ "$$(cd "$$(dirname "$$dist")" && pwd)" != "$$(cd tools/1ce-training && pwd)" ]; then \
		echo "→ переношу дистрибутив в tools/1ce-training/: $$(basename "$$dist")"; \
		mv "$$dist" tools/1ce-training/; \
	fi; \
	echo "→ сборка $(ONEC_IMAGE) из $$(ls tools/1ce-training/*.run | head -1)"; \
	docker build -t $(ONEC_IMAGE) -f docker/onec.Dockerfile tools/1ce-training
onec-guide:  ## как добыть дистрибутив учебной 1С для категории B
	@printf '\n  Категория B исполняется в учебной 1С (Docker) — нужен свой дистрибутив платформы:\n'
	@printf '    1. Скачай учебную версию (Linux, файл .run) — https://developer.1c.ru\n'
	@printf '       (учебной версии не нужна активация лицензии; подойдёт любая версия 8.3.2x)\n'
	@printf '    2. Положи .run в tools/1ce-training/ (или прямо в tools/ — make его найдёт и перенесёт)\n'
	@printf '    3. Собери образ:  make image-onec\n'
	@printf '  Дистрибутив не коммитится и не редистрибутируется (tools/ в .gitignore).\n\n'

##@ Разработка
venv: $(VENV)  ## python-окружение (.venv) — uv sync
$(VENV): pyproject.toml
	$(UV) sync
	@touch $(VENV)
test: venv  ## все тесты параллельно -n auto (интеграция с реальной 1С/OneScript — минуты; MODE=docker)
	$(UV) run pytest -q -n auto
test-fast: venv  ## экспресс: только быстрые тесты, без реальной песочницы (секунды)
	$(UV) run pytest -q -m "not slow"
lint: venv  ## ruff (check + format) + pre-commit (как в CI)
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run pre-commit run --all-files
docs: venv  ## регенерировать таблицы лидерборда и бейджи в README/status (алиас prism docs)
	$(UV) run prism docs
docs-serve: venv  ## локальный предпросмотр документации (MkDocs); порт сменить: DOCS_ADDR=127.0.0.1:8001
	$(UV) sync --group docs
	$(UV) run mkdocs serve -a $(DOCS_ADDR)
docs-build: venv  ## собрать статический сайт документации в site/ (MkDocs)
	$(UV) sync --group docs
	$(UV) run mkdocs build
clean:  ## убрать venv, рабочие и build-артефакты (данные results/ не трогает)
	rm -rf $(VENV) site build *.egg-info .pytest_cache .ruff_cache work
