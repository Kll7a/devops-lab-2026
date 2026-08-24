.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Показать доступные команды
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

host: ## Привести VM к состоянию из Ansible
	cd infra/ansible && ansible-playbook -i inventory.ini site.yml --become --ask-become-pass

verify: ## Проверить стенд
	./scripts/verify.sh

up: ## Поднять локальный стенд
	cd app && podman-compose up -d --build

down: ## Погасить локальный стенд (данные сохраняются)
	cd app && podman-compose down

clean: ## Погасить и удалить данные
	cd app && podman-compose down -v

spec: ## Обновить app/openapi.json из работающего API
	curl -sS localhost:8000/openapi.json | jq -S . > app/openapi.json

api-test: ## Прогнать коллекцию Bruno
	cd api-tests/bruno && bru run --env local

dev-setup: ## Установить окружение для разработки (один раз)
	cd app && uv venv && uv pip install -r requirements.txt && uv pip install ruff pytest

lint: ## Проверить стиль кода
	cd app && uv run ruff check src tests --fix

test: ## Прогнать юнит-тесты
	cd app && uv run pytest -q
