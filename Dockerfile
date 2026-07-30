# ── Deal Manager Dockerfile ─────────────────────────────
# Build:  docker build -t deal-manager .
# Run:    docker run -p 8000:8000 -v $PWD/data:/app/data deal-manager

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Data directory for SQLite (if not using PostgreSQL)
RUN mkdir -p /app/data

EXPOSE 8000

ENV ENV=prod
ENV DATABASE_URL=sqlite:////app/data/deals.db
ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["sh", "-c", "uvicorn main:app --host $HOST --port $PORT"]
