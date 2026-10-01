# ─────────────────────────────────────────────────────────────────────────────
#  Holy Grills — developer shortcuts
#
#  Everything you need, in order:
#
#      make setup      # create .venv, install deps, create .env if missing
#      make check      # is Supabase reachable + are the keys valid?
#      make contract   # does every table/column/RPC the code uses exist?
#      make smoke      # read-only end-to-end against the live project
#      make e2e        # full end-to-end (creates + deletes its own test user)
#      make verify     # check + contract + e2e in one go
#
#  On Windows (no make): run the same commands from the table below by hand,
#  using .venv\Scripts\python instead of .venv/bin/python.
# ─────────────────────────────────────────────────────────────────────────────

PY      ?= python3
VENV    ?= .venv
PORT    ?= 5000
BASE_URL?= http://localhost:$(PORT)

ifeq ($(OS),Windows_NT)
  BIN := $(VENV)/Scripts
else
  BIN := $(VENV)/bin
endif
RUN := $(BIN)/python
# Replit exports PIP_USER=true; pip then refuses to install into a venv
# ("Can not perform a '--user' install"). Scope the override to our commands.
PIP := PIP_USER=false $(BIN)/pip

.DEFAULT_GOAL := help
.PHONY: help setup venv install env check contract selfcheck smoke e2e verify plans server worker clean reset

help:  ## Show this help
	@echo "Holy Grills backend — available targets:"
	@echo
	@echo "  make setup      Create .venv, install dependencies, create .env if missing"
	@echo "  make check      Supabase connection preflight (keys, ref, signatures, tables)"
	@echo "  make contract   Verify every table/column/RPC the code uses exists in the DB"
	@echo "  make audit      RLS/grants/RPC audit (+ duplicate table & function search)"
	@echo "  make selfcheck  Offline: confirm the E2E suite's routes exist in the app"
	@echo "  make smoke      Read-only end-to-end run (no writes at all)"
	@echo "  make e2e        Full end-to-end run (test user created, then deleted)"
	@echo "  make verify     check + contract + e2e"
	@echo "  make plans      List every E2E step without running it"
	@echo "  make server     Start the API on port $(PORT)"
	@echo "  make clean      Remove __pycache__ and .pyc files"
	@echo
	@echo "  Override anything, e.g.:  make e2e ADMIN_TOKEN=<jwt>  |  make smoke BASE_URL=https://api.example.com"

setup: venv env install  ## Bootstrap everything
	@echo
	@echo "Setup complete. Next:  make check"

venv:  ## Create the virtualenv
	@test -d $(VENV) || $(PY) -m venv $(VENV)
	@echo "venv:  $(VENV)"

env:  ## Create .env from the template if it does not exist
	@if [ -f .env ]; then \
		echo ".env:  present (left untouched)"; \
	else \
		cp .env.example .env; \
		echo ".env:  created from .env.example — fill in SUPABASE_URL / keys / JWT secret"; \
	fi

install: venv  ## Install Python dependencies
	@$(PIP) install -q --upgrade pip
	@$(PIP) install -q -r requirements.txt
	@echo "deps:  installed"

check:  ## Supabase connection preflight
	@$(RUN) scripts/check_supabase.py

contract:  ## Code ↔ database contract check
	@$(RUN) scripts/contract_check.py

audit:  ## Database audit: duplicates, RLS/grants, RPC behaviour (needs SUPABASE_DB_URL for the deep pass)
	@$(RUN) scripts/db_audit.py $(ARGS)

selfcheck:  ## Offline route check (no network)
	@$(RUN) scripts/live_test.py --self-check

smoke:  ## Read-only end-to-end run
	@$(RUN) scripts/live_test.py --read-only $(if $(BASE_URL),--base-url $(BASE_URL),)

e2e:  ## Full end-to-end run with automatic cleanup
	@$(RUN) scripts/live_test.py $(if $(BASE_URL),--base-url $(BASE_URL),) \
		$(if $(ADMIN_TOKEN),--admin-token $(ADMIN_TOKEN),) \
		$(if $(LOGIN_EMAIL),--login-email $(LOGIN_EMAIL) --login-password $(LOGIN_PASSWORD),) \
		$(if $(CAMPUS_ID),--campus-id $(CAMPUS_ID),) \
		$(if $(ADMIN_EMAIL),--admin-email $(ADMIN_EMAIL) --admin-password $(ADMIN_PASSWORD),) \
		$(E2E_ARGS)

verify: check contract e2e  ## Run every verification in order

plans:  ## List the E2E plan
	@$(RUN) scripts/live_test.py --list

server:  ## Run the API locally
	@PORT=$(PORT) $(RUN) run.py

worker:  ## Run the Celery worker
	@$(BIN)/celery -A app.tasks.celery_app.celery_app worker --loglevel=info

clean:  ## Remove bytecode caches
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -name '*.pyc' -delete 2>/dev/null || true
	@echo "cleaned"

reset:  ## Nuke the venv (keeps .env) and rebuild from scratch
	@rm -rf $(VENV)
	@$(MAKE) setup
