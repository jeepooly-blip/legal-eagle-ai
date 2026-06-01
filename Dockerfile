# Dockerfile for Railway (and any Docker host). Used as a fallback if
# Nixpacks auto-detection has issues installing the legal_eagle package.
#
# Build:  docker build -t legal-eagle-ai .
# Run:    docker run -p 8000:8000 legal-eagle-ai

FROM python:3.11-slim

WORKDIR /app

# System deps (curl is useful for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Install this project as an editable package so `import legal_eagle` works
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

# Copy the rest of the source (tests etc. — kept small; not run in the container)
COPY . .

# Railway injects $PORT at runtime. Do NOT hardcode PORT in ENV — that
# shadows the platform-injected value and causes the healthcheck to fail.
# Use shell-form CMD so $PORT is expanded at runtime, with a sane default.
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn legal_eagle.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]
