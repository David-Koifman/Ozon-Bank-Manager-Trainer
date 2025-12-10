FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install build dependencies for webrtcvad (C extension)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Configure Poetry: Don't create virtual environment, don't ask for interactive input
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy Poetry files
COPY backend/pyproject.toml backend/poetry.lock* ./

# Install dependencies using Poetry (install to system Python, not venv)
RUN poetry install --only main --no-root && rm -rf $POETRY_CACHE_DIR

# Copy backend code
COPY backend/ ./

# Set working directory to backend for proper imports
WORKDIR /app

# Expose port
EXPOSE 8000

# Run the application (no need for poetry run since we're using system Python)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

