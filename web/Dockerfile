# By Heart web trainer — Cloud Run image.
# Build from the REPO ROOT so the web/ service can install the sibling `by-heart`
# package it depends on:   docker build -f web/Dockerfile -t by-heart-web .
FROM python:3.13-slim

# uv for fast, lockfile-faithful installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /src
COPY . .

# Install the workspace (root `by-heart` + the `web` member) into the system env.
RUN uv sync --frozen --package by-heart-web --no-dev

# Cloud Run sends traffic to $PORT (default 8080); bind 0.0.0.0.
ENV PORT=8080
EXPOSE 8080

# No .env in the image — secrets/config come from Cloud Run env / Secret Manager.
# Flip to Vertex AI with GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT +
# GOOGLE_CLOUD_LOCATION (no app code change). Locally, GOOGLE_API_KEY is used instead.
CMD ["sh", "-c", "uv run uvicorn by_heart_web.server:app --host 0.0.0.0 --port ${PORT}"]
