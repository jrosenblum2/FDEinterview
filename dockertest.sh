#!/usr/bin/env bash
# =============================================================================
# dockertest.sh — build and run the app in Docker for local testing.
#
# Prerequisites:
#   - Docker Desktop running
#   - Cloud SQL Auth Proxy running on localhost:5432 (same as normal local dev)
#   - gcloud auth application-default login completed
#
# Usage:
#   ./dockertest.sh          # build image and run container
#   ./dockertest.sh --no-build  # skip build, just (re)start the container
# =============================================================================

set -euo pipefail

IMAGE_NAME="reducto-rag-local"
CONTAINER_NAME="reducto-rag-test"
HOST_PORT=8080
GCP_CREDS_FILE="$HOME/.config/gcloud/application_default_credentials.json"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
SKIP_BUILD=false
for arg in "$@"; do
  case $arg in
    --no-build) SKIP_BUILD=true ;;
  esac
done

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found. Copy .env.example and fill in your values."
  exit 1
fi

if [ ! -f "$GCP_CREDS_FILE" ]; then
  echo "ERROR: GCP application default credentials not found at:"
  echo "  $GCP_CREDS_FILE"
  echo "Run: gcloud auth application-default login"
  exit 1
fi

# ---------------------------------------------------------------------------
# Stop and remove any existing container with the same name
# ---------------------------------------------------------------------------
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping and removing existing container: $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME"
fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
if [ "$SKIP_BUILD" = false ]; then
  echo ""
  echo "Building Docker image: $IMAGE_NAME"
  docker build -t "$IMAGE_NAME" .
  echo "Build complete."
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
echo ""
echo "Starting container: $CONTAINER_NAME"
echo "  App:  http://localhost:$HOST_PORT"
echo "  Logs: docker logs -f $CONTAINER_NAME"
echo ""

docker run \
  --name "$CONTAINER_NAME" \
  --rm \
  -p "${HOST_PORT}:8080" \
  \
  `# Load all env vars from .env, then override DB_HOST so the container` \
  `# reaches the Cloud SQL Auth Proxy running on your Mac's localhost.` \
  --env-file .env \
  -e DB_HOST=host.docker.internal \
  \
  `# Mount GCP application default credentials so Vertex AI calls work.` \
  `# In Cloud Run these come automatically from the service account.` \
  -v "${GCP_CREDS_FILE}:/tmp/gcp_creds.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp_creds.json \
  \
  "$IMAGE_NAME"
