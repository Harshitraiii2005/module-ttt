SHELL := /bin/bash

DEFAULT_MODE := git
MODE ?= $(DEFAULT_MODE)

.DEFAULT_GOAL := help

# Written by infra-tdb-platform's configure_llm_provider.sh during DevPod
# setup: "infisical" if the user chose Infisical for secrets, "dotenv" if
# they chose a plain .env file. Defaults to "infisical" if the file is
# missing (e.g. running outside DevPod / before setup has run).
SECRETS_MODE := $(shell cat .secrets_mode 2>/dev/null || echo infisical)

local:
ifeq ($(SECRETS_MODE),dotenv)
	set -a && source .env && set +a && poetry run python -m spacy download en_core_web_md && poetry run python -m debugpy --listen 0.0.0.0:5690 -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --loop uvloop --http httptools --reload --reload-dir ./ --reload-dir ../base-tdb-models --reload-dir ../base-tdb-clients --reload-dir ../base-tdb-helpers --reload-dir ../package-content-elementizer
else
	infisical run --watch -- sh -c '
	poetry run python -m spacy download en_core_web_md &&
	poetry run python -m debugpy --listen 0.0.0.0:5690 -m uvicorn app.main:app \
	--host 0.0.0.0 \
	--port 8090 \
	--loop uvloop \
	--http httptools \
	--reload \
	--reload-dir ./ \
	--reload-dir ../base-tdb-models \
	--reload-dir ../base-tdb-clients \
	--reload-dir ../base-tdb-helpers \
	--reload-dir ../package-content-elementizer
	'
endif

run:
ifeq ($(SECRETS_MODE),dotenv)
	set -a && source .env && set +a && poetry run python -m spacy download en_core_web_md && poetry run python -m uvicorn app.main:app --host 0.0.0.0 --port 8090 --workers 4 --loop uvloop --http httptools
else
	infisical run -- sh -c '
	poetry run python -m spacy download en_core_web_md &&
	poetry run python -m uvicorn app.main:app \
	--host 0.0.0.0 \
	--port 8090 \
	--workers 4 \
	--loop uvloop \
	--http httptools
	'
endif

sync:
	@echo "🔄 Running sync_git_deps.py with mode: $(MODE)"
	python3 sync_git_deps.py --mode "$(MODE)"

sync-dry-run:
	@echo "🔍 Dry-run sync for validation (mode: $(MODE))"
	python3 sync_git_deps.py --mode "$(MODE)" --dry-run

install-hooks:
	@echo "Installing git hooks..."
	@cp -f git-hooks/* .git/hooks/
	@chmod +x .git/hooks/* 2>/dev/null || true
	@echo "Git hooks installed!"

help:
	@echo ""
	@echo "Targets:"
	@echo "  make local   → start local stack"
	@echo "  make sync MODE=<git|local>      → sync git deps (default: git)"
	@echo "  make sync-dry-run MODE=<git|local> → validate deps without changing files"
	@echo "  install-hooks → install git hooks"
	@echo ""
