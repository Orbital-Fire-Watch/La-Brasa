# Build context is the repository root (docker-compose.yml): POST /api/sync runs pipeline/sync_data.py, which
# fetches FIRMS, runs the harmonisation and loads the database, so the image keeps the repository layout
# (/app/backend, /app/pipeline, /app/harmonisation) and data/ is mounted at /app/data.
FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
COPY pipeline/requirements.txt pipeline/requirements.txt
COPY harmonisation/requirements.txt harmonisation/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r pipeline/requirements.txt -r harmonisation/requirements.txt
COPY backend backend
COPY pipeline pipeline
COPY harmonisation harmonisation
# One Python with every package; the harmonisation does not need its own .venv here
ENV HARMONISATION_PYTHON=python
WORKDIR /app/backend
EXPOSE 8000
# One worker: the sync status lives in the process (services/sync.py)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
