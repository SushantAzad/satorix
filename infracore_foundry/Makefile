.PHONY: setup dev dev-local dev-cloud test test-connectors lint reset-db logs stop clean \
        ollama-start ollama-pull ollama-pull-small ollama-models ollama-test

setup:
	docker compose up -d postgres minio redis
	sleep 5
	python -m layer1_ingestion.core.database
	docker compose up -d minio-init

dev:
	docker compose up -d
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
	docker compose down -v
	docker compose up -d postgres
	sleep 3
	python -m layer1_ingestion.core.database

logs:
	docker compose logs -f layer1-api

stop:
	docker compose down

clean:
	docker compose down -v
	docker system prune -f

# ── Ollama / LLM targets ─────────────────────────────────────────────────────

ollama-start:
	docker compose up -d ollama

ollama-pull:
	docker exec satorix-ollama ollama pull qwen3:8b

ollama-pull-small:
	docker exec satorix-ollama ollama pull phi4-mini:3.8b

ollama-models:
	docker exec satorix-ollama ollama list

ollama-test:
	curl -s http://localhost:11434/v1/chat/completions \
	  -H "Content-Type: application/json" \
	  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"What is CIRP in Indian corporate law?"}],"max_tokens":100}' \
	  | python3 -m json.tool

dev-local:
	LLM_PROVIDER=ollama docker compose up -d

dev-cloud:
	LLM_PROVIDER=anthropic docker compose up -d
