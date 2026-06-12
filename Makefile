# Парадная дверь PRISM. `make` без аргументов — список целей.
#
# Две дороги до инструментов осей:
#   make tools   — поставить на ХОСТ (bootstrap-скрипты tools/*.sh) → режим local
#   make images  — собрать DOCKER-образы инструментов            → режим docker
# Режим выбирается на прогоне через env:
#   PRISM_RUNNER=local|docker  (ось M, OneScript)
#   PRISM_BSL=local|docker     (оси S/O, BSL LS)

VENV  ?= .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip
PRISM := $(VENV)/bin/prism

ONESCRIPT_IMAGE := prism-onescript:2.0.1
BSL_LS_IMAGE    := prism-bsl-ls:0.29.0

.DEFAULT_GOAL := help
.PHONY: help setup venv tools images image-onescript image-bsl-ls check score test lint clean

help:  ## показать этот список
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: venv tools  ## всё для локальной разработки: окружение + инструменты на хост

venv: $(VENV)  ## python-окружение (.venv) с пакетом и dev-зависимостями

$(VENV): pyproject.toml
	python3 -m venv $(VENV)
	$(PIP) install -q -e ".[dev]"
	@touch $(VENV)

tools:  ## поставить инструменты осей на хост (OneScript + BSL LS) — те же bootstrap-скрипты
	./tools/get-onescript.sh
	./tools/get-bsl-ls.sh

images: image-onescript image-bsl-ls  ## собрать оба docker-образа инструментов

image-onescript:  ## образ песочницы M (OneScript)
	docker build -t $(ONESCRIPT_IMAGE) -f docker/onescript.Dockerfile .

image-bsl-ls:  ## образ инструмента S/O (BSL LS на JRE 21)
	docker build -t $(BSL_LS_IMAGE) -f docker/bsl-ls.Dockerfile .

check: venv  ## целостность: контракты, задания, эталоны, инструменты
	$(PRISM) check

score: venv  ## авто-оценка L1 (EXP=<файл> и/или EDITION=<имя> — опционально)
	$(PRISM) score $(if $(EXP),--experiment $(EXP)) $(if $(EDITION),--edition $(EDITION))

test: venv  ## тесты (интеграционные сами скипнутся без инструментов)
	$(PY) -m pytest -q

lint: venv  ## ruff + pre-commit (как в CI)
	$(VENV)/bin/ruff check .
	$(VENV)/bin/pre-commit run --all-files

clean:  ## убрать venv, рабочие и build-артефакты (данные results/ не трогает)
	rm -rf $(VENV) site build *.egg-info .pytest_cache .ruff_cache work
