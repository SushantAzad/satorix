FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
RUN pip install --no-cache-dir \
    asyncpg==0.29.0 \
    neo4j==5.14.0 \
    xgboost==2.0.3 \
    shap==0.44.0 \
    scikit-learn==1.4.0 \
    scipy==1.12.0 \
    sentence-transformers==2.3.1 \
    anthropic==0.25.0 \
    aioredis==2.0.1 \
    httpx==0.25.2 \
    kafka-python==2.0.2 \
    minio==7.2.0

COPY layer5_analytics_ai/ /app/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8005

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8005", "--workers", "2"]
