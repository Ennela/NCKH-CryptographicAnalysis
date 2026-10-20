#!/usr/bin/env bash
# Build on this workstation, run on a small server (docker-compose.server.yml).
#
# Images go through a registry on this workstation (127.0.0.1:5000). The server
# reaches it through an SSH reverse tunnel opened only while it pulls, so no
# registry, token or open port is needed on the server, and only changed layers
# travel after the first deploy (the registry volume keeps the layers).
#
# Usage (from the repository root):
#   SERVER=user@host SSH_KEY=~/.ssh/server.pem ENV_FILE=.env.server \
#     scripts/deploy_server.sh            # build + push + sync + up
#   SKIP_BUILD=1 ... scripts/deploy_server.sh   # reuse images already built
#
# The script only touches the compose project "${PROJECT}" on the server; it
# never stops, removes or prunes anything else (the server is shared).
set -euo pipefail

: "${SERVER:?set SERVER=user@host}"
: "${SSH_KEY:?set SSH_KEY to the private key file}"
ENV_FILE="${ENV_FILE:-.env.server}"
REMOTE_DIR="${REMOTE_DIR:-nckh}"          # relative to the remote home
PROJECT="${PROJECT:-nckh}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
REGISTRY="localhost:${REGISTRY_PORT}"
CLOUDFLARED_IMAGE="${CLOUDFLARED_IMAGE:-cloudflare/cloudflared:2026.9.1}"
SSH=(ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes)

[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (see docs/deploy.md, section 9)" >&2; exit 1; }

# Local registry; its volume is the layer cache between deploys.
if ! docker ps --format '{{.Names}}' | grep -qx nckh-registry; then
  docker start nckh-registry 2>/dev/null || docker run -d --name nckh-registry \
    --restart unless-stopped -p "127.0.0.1:${REGISTRY_PORT}:5000" \
    -v nckh_registry:/var/lib/registry registry:2.8.3
fi

if [ "${SKIP_BUILD:-0}" != 1 ]; then
  docker compose -p nckh-prod -f docker-compose.prod.yml build celery-worker inference frontend
fi
docker pull -q "$CLOUDFLARED_IMAGE" >/dev/null

# server image name -> local image
declare -A IMAGES=(
  [ingestion]=nckh-prod-celery-worker:latest
  [inference]=nckh-prod-inference:latest
  [frontend]=nckh-prod-frontend:latest
  [postgres]=timescale/timescaledb:latest-pg16
  [redis]=redis:7-alpine
  [mlflow]=ghcr.io/mlflow/mlflow:v2.11.3
  [nginx]=nginx:alpine
  [cloudflared]="$CLOUDFLARED_IMAGE"
)
for name in "${!IMAGES[@]}"; do
  docker tag "${IMAGES[$name]}" "$REGISTRY/nckh/$name:latest"
  docker push -q "$REGISTRY/nckh/$name:latest" >/dev/null
  echo "pushed $name"
done

# Files the compose file mounts, plus the env file (never committed).
"${SSH[@]}" "$SERVER" "mkdir -p '$REMOTE_DIR'"
tar -cf - docker-compose.server.yml infra/nginx/templates infra/postgres/init.sql \
  | "${SSH[@]}" "$SERVER" "tar -xf - -C '$REMOTE_DIR'"
"${SSH[@]}" "$SERVER" "umask 077 && cat > '$REMOTE_DIR/.env'" < "$ENV_FILE"

# Pull through the reverse tunnel, then (re)start only this project. Add
# PROFILE_ARGS="--profile tunnel" to start cloudflared too.
"${SSH[@]}" -o ExitOnForwardFailure=yes -R "127.0.0.1:${REGISTRY_PORT}:127.0.0.1:${REGISTRY_PORT}" "$SERVER" \
  "cd '$REMOTE_DIR' && docker compose -p '$PROJECT' -f docker-compose.server.yml ${PROFILE_ARGS:-} pull -q \
   && docker compose -p '$PROJECT' -f docker-compose.server.yml ${PROFILE_ARGS:-} up -d \
   && docker compose -p '$PROJECT' -f docker-compose.server.yml ps"
