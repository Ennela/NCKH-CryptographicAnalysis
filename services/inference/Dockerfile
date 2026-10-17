FROM python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared /app/shared
RUN pip install --no-cache-dir -e /app/shared

# Copy inference service files
COPY services/inference /app/services/inference
# Install requirements with CPU-only torch, as the training image does: the
# default PyPI wheel bundles CUDA libraries (~10 GB image) that inference never uses.
RUN pip install --no-cache-dir -r /app/services/inference/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# `import shared...` resolves from /app (the editable install above exposes no
# top-level `shared` package). docker-compose.yml sets the same for dev.
ENV PYTHONPATH=/app

WORKDIR /app/services/inference

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
