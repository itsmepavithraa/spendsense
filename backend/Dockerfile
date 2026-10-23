FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Install dependencies first: Docker caches this layer, so editing code
# doesn't reinstall every package.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Production start:
#   1. apply any pending database migrations
#   2. if SEED_DEMO_DATA=true, load the demo account (skipped when it already exists)
#   3. serve the API on $PORT (cloud hosts set it; default 8000)
# docker-compose overrides this with a --reload command for local development.
CMD ["sh", "-c", "alembic upgrade head && if [ \"$SEED_DEMO_DATA\" = \"true\" ]; then python -m scripts.seed --if-empty; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
