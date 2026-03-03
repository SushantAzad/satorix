.PHONY: setup dev test test-connectors lint reset-db logs stop clean

setup:
	docker-compose up -d postgres minio redis
	timeout /t 5
	python -m layer1_ingestion.core.database
	docker-compose up -d minio-init

dev:
	docker-compose up -d
	uvicorn layer1_ingestion.api.main:app --reload --port 8001

test:
	pytest tests/ -v --tb=short

test-connectors:
	pytest tests/layer1/ -v --tb=short -k "connector"

lint:
	python -m py_compile layer1_ingestion/core/config.py
	python -m py_compile layer1_ingestion/core/encryption.py
	python -m py_compile layer1_ingestion/core/storage.py
	python -m py_compile layer1_ingestion/core/database.py

reset-db:
	docker-compose down -v
	docker-compose up -d postgres
	timeout /t 3
	python -m layer1_ingestion.core.database

logs:
	docker-compose logs -f layer1-api

stop:
	docker-compose down

clean:
	docker-compose down -v
	docker system prune -f
