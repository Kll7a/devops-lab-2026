.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Показать доступные команды
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

host: ## Привести VM к состоянию из Ansible
	cd infra/ansible && ansible-playbook -i inventory.ini site.yml --become --ask-become-pass

verify: ## Проверить стенд
	./scripts/verify.sh
