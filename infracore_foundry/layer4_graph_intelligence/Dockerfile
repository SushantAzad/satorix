FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY layer4_graph_intelligence/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Shared LLM provider abstraction
COPY shared/ /app/shared/

# Layer 3 ontology (needed for ObjectDataFunnel and schema imports)
COPY layer3_ontology/ /app/layer3_ontology/

# Layer 4 source directly into /app so `api.main` resolves correctly
COPY layer4_graph_intelligence/ /app/

ENV PYTHONPATH=/app:/app/layer3_ontology
ENV PYTHONUNBUFFERED=1

EXPOSE 8004

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "4"]
