FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt .
RUN pip install --no-cache-dir fastapi uvicorn[standard] psycopg[binary] pydantic httpx

COPY backend/ backend/
COPY config/ config/

ENV PYTHONPATH=/app
ENV DATABASE_URL=postgresql://flood_user:flood_local_dev_only@db:5432/flood_aware
ENV ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
