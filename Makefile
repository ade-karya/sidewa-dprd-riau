.DEFAULT_GOAL := help
PYTHON ?= python
APP := app.main:app
HOST ?= 127.0.0.1
PORT ?= 8000
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help install install-dev init seed run run-prod test lint fmt cov docker-build docker-up docker-down clean

help: ## Tampilkan daftar perintah
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Pasang dependensi produksi
	$(PYTHON) -m pip install -r requirements.txt

install-dev: ## Pasang dependensi pengembangan
	$(PYTHON) -m pip install -r requirements-dev.txt

init: ## Buat tabel database dan direktori media
	$(PYTHON) -m app.cli init-db

seed: ## Isi database dengan data demo (hapus data lama)
	$(PYTHON) -m app.cli seed --force

run: ## Jalankan server pengembangan dengan reload
	$(PYTHON) -m uvicorn $(APP) --reload --host $(HOST) --port $(PORT)

run-prod: ## Jalankan server produksi (tanpa reload, multi-worker)
	$(PYTHON) -m uvicorn $(APP) --host 0.0.0.0 --port $(PORT) --workers 4 --proxy-headers

test: ## Jalankan seluruh pengujian
	$(PYTEST) -q

cov: ## Jalankan pengujian dengan laporan cakupan
	$(PYTEST) --cov=app --cov-report=term-missing --cov-report=html

lint: ## Periksa gaya kode
	$(PYTHON) -m ruff check app tests scripts

fmt: ## Rapikan format kode
	$(PYTHON) -m ruff format app tests scripts

stats: ## Tampilkan ringkasan data
	$(PYTHON) -m app.cli stats

docker-build: ## Bangun image Docker
	docker compose build

docker-up: ## Jalankan stack Docker
	docker compose up -d

docker-down: ## Hentikan stack Docker
	docker compose down

clean: ## Bersihkan cache pengembangan
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
