FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Configure Poetry: Don't create virtual environment, don't ask for interactive input
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy Poetry files
COPY frontend/pyproject.toml frontend/poetry.lock* ./

# Install dependencies using Poetry (install to system Python, not venv)
RUN poetry install --only main --no-root && rm -rf $POETRY_CACHE_DIR

# Copy frontend code
COPY frontend/ ./

# Ensure .streamlit directory exists
RUN mkdir -p .streamlit

# Expose port
EXPOSE 8501

# Run Streamlit (no need for poetry run since we're using system Python)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

