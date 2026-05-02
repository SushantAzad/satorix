FROM python:3.11-slim

WORKDIR /app

# System deps for asyncpg, psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Layer 4 source
COPY . /app

# Copy Layer 3 source for ObjectDataFunnel import
COPY ../layer3_ontology /app/layer3_ontology

ENV PYTHONPATH=/app:/app/layer3_ontology

EXPOSE 8004

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "4"]
