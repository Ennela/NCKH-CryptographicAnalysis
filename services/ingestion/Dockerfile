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

# Copy ingestion service files
COPY services/ingestion /app/services/ingestion
RUN pip install --no-cache-dir -r /app/services/ingestion/requirements.txt

# vnstock is optional (quarantined on PyPI, see requirements-vnstock.txt).
# Build with `--build-arg INSTALL_VNSTOCK=true` to try installing it.
ARG INSTALL_VNSTOCK=false
RUN if [ "$INSTALL_VNSTOCK" = "true" ]; then \
        pip install --no-cache-dir -r /app/services/ingestion/requirements-vnstock.txt; \
    fi

WORKDIR /app/services/ingestion

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
