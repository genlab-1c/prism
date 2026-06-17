# Парадная дверь PRISM. `make` без аргументов — список целей.
#
# ДВЕ НЕЗАВИСИМЫЕ ОСИ:
#   1) ХАРНЕСС — всегда через pip/venv (make venv). Сам харнесс не докеризуется.
#   2) ИНСТРУМЕНТЫ осей — ЛИБО на хост (make tools), ЛИБО в docker (make images).
#      Это АЛЬТЕРНАТИВЫ, не шаги по порядку. Что использовать — выбирается на прогоне.
#
# Готовые рецепты установки:
#   make setup         — харнесс + инструменты на ХОСТ          (прогон в режиме local)
#   make setup-docker  — харнесс + docker-образы инструментов   (прогон в режиме docker)
#
# Прогон: режим инструментов задаёт MODE (или env PRISM_RUNNER / PRISM_BSL напрямую):
#   make check              — local (по умолчанию)
#   make score MODE=docker  — инструменты крутятся в контейнерах

VENV  ?= .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip
PRISM := $(VENV)/bin/prism

ONESCRIPT_IMAGE := prism-onescript:2.0.1
BSL_LS_IMAGE    := prism-bsl-ls:0.29.0

# MODE=docker — короткий тумблер обоих режимов сразу. Не задан → берётся env (или local).
ifdef MODE
export PRISM_RUNNER := $(MODE)
export PRISM_BSL    := $(MODE)
endif

.DEFAULT_GOAL := help
.PHONY: help setup setup-docker venv tools images image-onescript image-bsl-ls check score test lint clean tasks-index

help:  ## показать этот список
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: venv tools  ## харнесс (pip) + инструменты на ХОСТ → прогон local

setup-docker: venv images  ## харнесс (pip) + docker-образы инструментов → прогон MODE=docker

venv: $(VENV)  ## python-окружение (.venv) с пакетом и dev-зависимостями

$(VENV): pyproject.toml
	python3 -m venv $(VENV)
	$(PIP) install -q -e ".[dev]"
	@touch $(VENV)

tools:  ## инструменты осей на ХОСТ (OneScript + BSL LS) — те же bootstrap-скрипты
	./tools/get-onescript.sh
	./tools/get-bsl-ls.sh

images: image-onescript image-bsl-ls  ## собрать оба docker-образа инструментов

image-onescript:  ## образ песочницы M (OneScript)
	docker build -t $(ONESCRIPT_IMAGE) -f docker/onescript.Dockerfile .

image-bsl-ls:  ## образ инструмента S/O (BSL LS на JRE 21)
	docker build -t $(BSL_LS_IMAGE) -f docker/bsl-ls.Dockerfile .

check: venv  ## целостность: контракты, задания, эталоны, инструменты (MODE=docker — в контейнерах)
	$(PRISM) check

tasks-index: venv  ## пересобрать видимый банк задач (tasks/README.md) из task.yaml
	$(PRISM) tasks

score: venv  ## авто-оценка L1 (MODE=docker; EXP=<файл> и/или EDITION=<имя> — опционально)
	$(PRISM) score $(if $(EXP),--experiment $(EXP)) $(if $(EDITION),--edition $(EDITION))

test: venv  ## тесты (интеграционные сами скипнутся без инструментов)
	$(PY) -m pytest -q

lint: venv  ## ruff + pre-commit (как в CI)
	$(VENV)/bin/ruff check .
	$(VENV)/bin/pre-commit run --all-files

clean:  ## убрать venv, рабочие и build-артефакты (данные results/ не трогает)
	rm -rf $(VENV) site build *.egg-info .pytest_cache .ruff_cache work
