FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# libsndfile1: required runtime library for soundfile package
# No build-essential needed: torch and soundfile have pre-built wheels
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy Poetry files
COPY tts_service/pyproject.toml tts_service/poetry.lock* ./

# Install dependencies using Poetry
RUN poetry install --only main --no-root && rm -rf $POETRY_CACHE_DIR

# Copy service code
COPY tts_service/ ./

# Expose port
EXPOSE 8002

# Run the service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]

