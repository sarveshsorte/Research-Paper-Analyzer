FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend/ ./backend/
COPY query_pipeline/ ./query_pipeline/
COPY document_pipeline/ ./document_pipeline/
COPY database/ ./database/

# Ensure runtime directories exist
RUN mkdir -p storage/bm25 storage/qdrant storage/uploads

# Expose default port
EXPOSE 8000

# Start Uvicorn dynamically binding to $PORT (for Render / Railway / Cloud Run)
CMD sh -c "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
