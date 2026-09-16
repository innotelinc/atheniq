# ==========================================================================
# AthenIQ — operator workflow
# Usage: make <target>   (see `make help`)
# ==========================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help setup up down logs ps \
        openmaic-up openmaic-down convex-up convex-down convex-key \
        check-commits check-compose tutor-quickstart

help: ## Show this help message
	@echo "AthenIQ — operator workflow"
	@echo "Usage: make <target>"
	@grep -E '^[a-zA-Z_:%-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## ---- Bootstrap ------------------------------------------------------------

setup: ## Preflight, install guard hooks, generate .env secrets
	bash scripts/setup.sh

## ---- Compose (this repo's AI services) -----------------------------------

up: ## Start all AthenIQ-managed services (openmaic + convex profiles)
	docker compose --profile openmaic --profile convex up -d

down: ## Stop AthenIQ-managed services (keeps volumes)
	docker compose down

logs: ## Tail logs from AthenIQ-managed services
	docker compose --profile openmaic --profile convex logs -f

ps: ## List service status
	docker compose ps

# No gateway-up/gateway-down: the model gateway is the platform's single
# OmniRoute in Group 2 (`2-voice/`, mesh 10.10.2.1). Reach it at the
# OMNIROUTE_BASE_URL in .env — AthenIQ runs none (see docker-compose.yml).

openmaic-up: ## Start the OpenMAIC persistence Postgres
	docker compose --profile openmaic up -d

openmaic-down: ## Stop the OpenMAIC persistence Postgres
	docker compose --profile openmaic down

## ---- Realtime (Convex) ----------------------------------------------------

convex-up: ## Start the self-hosted Convex backend + dashboard
	docker compose --profile convex up -d

convex-down: ## Stop Convex (keeps its data volume)
	docker compose --profile convex down

convex-key: ## Mint a Convex admin key from the running backend (paste into .env)
	@docker compose --profile convex exec -T convex ./generate_admin_key.sh

## ---- Checks ---------------------------------------------------------------

check-commits: ## Reject generated attribution text in reachable commit messages
	bash scripts/check-commit-messages.sh

check-compose: ## Validate every compose profile parses
	docker compose config --quiet
	docker compose --profile openmaic config --quiet
	docker compose --profile convex config --quiet

## ---- LMS core (Tutor / Open edX) -----------------------------------------

tutor-quickstart: ## First boot of the LMS (interactive Tutor bring-up)
	tutor local quickstart
