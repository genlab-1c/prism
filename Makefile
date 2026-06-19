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
# Готовые рецепты установки:
#   make setup         — окружение + инструменты осей на ХОСТ          (прогон prism в режиме local)
#   make setup-docker  — окружение + docker-образы инструментов        (prism ... --runner docker)

UV    ?= uv
VENV  ?= .venv

ONESCRIPT_IMAGE := prism-onescript:2.0.1
BSL_LS_IMAGE    := prism-bsl-ls:0.29.0

# MODE=docker — тумблер песочниц для `make test` (интеграция в контейнерах вместо хоста).
# Для самих прогонов prism песочница выбирается флагом: prism ... --runner/--bsl docker.
ifdef MODE
export PRISM_RUNNER := $(MODE)
export PRISM_BSL    := $(MODE)
endif

.DEFAULT_GOAL := help
.PHONY: help setup setup-docker venv tools images image-onescript image-bsl-ls test test-fast lint docs clean

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
setup: venv tools  ## окружение (uv) + инструменты осей на ХОСТ → прогон prism в режиме local
setup-docker: venv images  ## окружение (uv) + docker-образы инструментов → prism ... --runner docker

##@ Инструменты осей
tools:  ## OneScript + BSL LS на ХОСТ (bootstrap-скрипты)
	./tools/get-onescript.sh
	./tools/get-bsl-ls.sh
images: image-onescript image-bsl-ls  ## собрать оба docker-образа инструментов
image-onescript:  ## образ песочницы M (OneScript)
	docker build -t $(ONESCRIPT_IMAGE) -f docker/onescript.Dockerfile .
image-bsl-ls:  ## образ инструмента S/O (BSL LS на JRE 21)
	docker build -t $(BSL_LS_IMAGE) -f docker/bsl-ls.Dockerfile .

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
clean:  ## убрать venv, рабочие и build-артефакты (данные results/ не трогает)
	rm -rf $(VENV) site build *.egg-info .pytest_cache .ruff_cache work
