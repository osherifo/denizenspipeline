IMAGE       := fmriflow
TAG         := latest
TARGET      := runtime
PORT        := 8421
DATA_DIR    := $(CURDIR)

# Directories mounted into the container
EXPERIMENTS := $(DATA_DIR)/experiments
RESULTS     := $(DATA_DIR)/results
DERIVATIVES := $(DATA_DIR)/derivatives

DOCKER_RUN  := docker run --rm \
	-v $(EXPERIMENTS):/data/experiments \
	-v $(RESULTS):/data/results \
	-v $(DERIVATIVES):/data/derivatives

# ── Build ────────────────────────────────────────────────────────────────

.PHONY: build build-full

build:  ## Build the runtime image (web UI + analysis pipeline)
	docker build --target runtime -t $(IMAGE):$(TAG) .

build-full:  ## Build the full image (adds dcm2niix + autoflatten)
	docker build --target full -t $(IMAGE)-full:$(TAG) .

# ── Run ──────────────────────────────────────────────────────────────────

.PHONY: serve stop logs

serve:  ## Start the web UI (docker compose)
	docker compose up -d
	@echo ""
	@echo "  fMRIflow running at http://localhost:$(PORT)"
	@echo "  Stop with: make stop"
	@echo ""

stop:  ## Stop the web UI
	docker compose down

logs:  ## Tail container logs
	docker compose logs -f

# ── CLI commands ─────────────────────────────────────────────────────────

.PHONY: shell run validate preproc

shell:  ## Open a shell inside the container
	$(DOCKER_RUN) -it $(IMAGE):$(TAG) bash

run:  ## Run a pipeline config: make run CONFIG=experiments/my_config.yaml
ifndef CONFIG
	@echo "Usage: make run CONFIG=experiments/my_config.yaml"
	@exit 1
endif
	$(DOCKER_RUN) $(IMAGE):$(TAG) run /data/experiments/$(notdir $(CONFIG))

validate:  ## Validate a config: make validate CONFIG=experiments/my_config.yaml
ifndef CONFIG
	@echo "Usage: make validate CONFIG=experiments/my_config.yaml"
	@exit 1
endif
	$(DOCKER_RUN) $(IMAGE):$(TAG) validate /data/experiments/$(notdir $(CONFIG))

preproc:  ## Run preprocessing: make preproc ARGS="--backend fmriprep --subject sub01 ..."
	$(DOCKER_RUN) $(IMAGE):$(TAG) preproc run $(ARGS)

# ── Development ──────────────────────────────────────────────────────────

.PHONY: dev test lint

dev:  ## Start with live frontend (Vite dev server + backend)
	cd frontend && npm run dev &
	fmriflow serve --port $(PORT)

test:  ## Run tests (host, not Docker)
	python -m pytest tests/ -v

lint:  ## Type-check frontend
	cd frontend && npx tsc --noEmit

# ── Cleanup ──────────────────────────────────────────────────────────────

.PHONY: clean

clean:  ## Remove Docker images
	docker rmi $(IMAGE):$(TAG) 2>/dev/null || true
	docker rmi $(IMAGE)-full:$(TAG) 2>/dev/null || true

# ── Help ─────────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
