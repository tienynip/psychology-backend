
FROM python:3.12-slim

# Python environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy migration files
COPY alembic.ini .
COPY alembic ./alembic

# Copy application source
COPY app ./app

# Application port
EXPOSE 8000

# Run migrations and start FastAPI
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
