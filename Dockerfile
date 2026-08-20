
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer-cached until requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY app/       ./app/
COPY knowledge/ ./knowledge/

EXPOSE 8000

# --workers 1 is required: the knowledge graph store is in-memory and not
# shared across processes (see app/store.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
