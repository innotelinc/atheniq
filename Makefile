# ==========================================================================
# AthenIQ — operator workflow
# Usage: make <target>   (see `make help`)
# ==========================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help setup up down logs ps \
        openmaic-up openmaic-down convex-up convex-down convex-key \
        onyx-check onyx-buckets onyx-selftest magnate-probe \
        paid-status entitlement-status entitlement-sync \
        check-commits check-compose check-tracks check-courses check-catalog check-syllabus check-images \
        catalog syllabus images course-bundle course-import test tutor-quickstart

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

## ---- Storage on ONYX (classroom media) ------------------------------------

onyx-check: ## Verify the ONYX classroom-media buckets are reachable (read-only)
	python3 scripts/onyx-buckets.py --check

onyx-buckets: ## Create the ONYX classroom-media buckets (idempotent)
	python3 scripts/onyx-buckets.py --create

onyx-selftest: ## Validate the ONYX config + SigV4 signing (no network)
	python3 scripts/onyx-buckets.py --selftest

## ---- Revenue on Magnate (paid courses) ------------------------------------

magnate-probe: ## Check the Magnate entitlement API is reachable + creds accepted
	python3 scripts/magnate-entitlements.py probe

## ---- Workforce tracks -----------------------------------------------------

check-tracks: ## Validate the workforce-tracks catalog
	python3 scripts/check-workforce-tracks.py

## ---- Courses (OLX authoring source) ---------------------------------------

check-courses: ## Validate the OLX course packages under courses/
	python3 scripts/check-course-olx.py

catalog: ## Regenerate the static course catalog page from the config files
	python3 scripts/build-course-catalog.py

check-catalog: ## Fail if the course catalog page is stale
	python3 scripts/build-course-catalog.py --check

syllabus: ## Regenerate the per-course syllabus pages from the OLX outlines
	python3 scripts/build-course-syllabus.py

check-syllabus: ## Fail if a syllabus page is stale
	python3 scripts/build-course-syllabus.py --check

images: ## Render the PNG brand + course-card assets (needs Pillow)
	python3 scripts/build-course-images.py

check-images: ## Fail if a PNG raster is missing or mis-sized
	python3 scripts/build-course-images.py --check

course-bundle: ## Bundle each OLX course into dist/courses/*.tar.gz
	python3 scripts/import-courses.py --bundle

course-import: ## Import the OLX courses into the running LMS (operator action)
	python3 scripts/import-courses.py --execute

## ---- Paid access (enrollment + reconciliation) ----------------------------

paid-status: ## Show the paid-enrollment ledger health (AthenIQ's LMS DB)
	python3 scripts/paid-enrollment.py --status

entitlement-status: ## Show Magnate -> Authentik paid-access reconciliation status
	python3 scripts/entitlement-sync.py --status

entitlement-sync: ## Preview the Magnate -> Authentik reconciliation (dry run)
	python3 scripts/entitlement-sync.py --dry-run

## ---- Tests ----------------------------------------------------------------

test: ## Run the unit tests (stdlib unittest, no dependencies)
	python3 -m unittest discover -s tests -p 'test_*.py' -v

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
