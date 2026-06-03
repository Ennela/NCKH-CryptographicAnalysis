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

# Copy training service files
COPY services/training /app/services/training

# Install requirements (using CPU-only torch to keep image size reasonable)
RUN pip install --no-cache-dir -r /app/services/training/requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

WORKDIR /app/services/training

# Keep container alive or run train.py by default
CMD ["python", "train.py", "--help"]
