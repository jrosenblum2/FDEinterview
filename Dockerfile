# =============================================================================
# Stage 1: Build the React frontend
# =============================================================================
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# Install dependencies first (cached layer — only re-runs when package.json changes)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

# Copy the rest of the frontend source and build to static files
COPY frontend/ ./
RUN npm run build

# The static output lands in /app/frontend/dist


# =============================================================================
# Stage 2: Python backend
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install uv for fast, reproducible Python dependency management
RUN pip install --no-cache-dir uv

# Copy dependency manifest first so Docker caches the install layer separately.
# This means the expensive `uv sync` step only re-runs when pyproject.toml changes.
COPY pyproject.toml ./

# Install all Python dependencies declared in pyproject.toml.
# --no-install-project skips building/installing the reducto-rag package itself
# (the backend source isn't copied yet at this layer), so only the third-party
# dependencies are installed here. The project code is added in the next COPY step.
RUN uv sync --no-dev --no-install-project

# Copy the backend source code
COPY backend/ ./backend/

# Copy the React static build output from Stage 1 into the location that
# main.py looks for: /app/backend/static
COPY --from=frontend-builder /app/frontend/dist ./backend/static/

# Cloud Run injects all secrets and configuration as environment variables at
# runtime — no secrets should live in this image.

EXPOSE 8080

# Single process: Uvicorn serving the FastAPI app, which also serves the
# compiled React SPA as static files.
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
