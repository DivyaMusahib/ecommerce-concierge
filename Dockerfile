FROM python:3.12-slim

# Metadata
LABEL maintainer="ShopMate Team"
LABEL description="ShopMate E-Commerce AI Assistant"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite fallback
RUN mkdir -p /app/data

# Expose default port (Render overrides via $PORT env var, defaults to 10000)
EXPOSE 10000

# Health check — uses $PORT at runtime
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT','10000') + '/health')" || exit 1

# Shell form CMD so ${PORT} is expanded at runtime by the shell.
# Render injects PORT=10000; locally falls back to 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info
