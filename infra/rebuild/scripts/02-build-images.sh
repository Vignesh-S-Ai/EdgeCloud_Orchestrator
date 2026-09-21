#!/bin/bash
# =============================================================================
# 02-build-images.sh — Build all 4 Docker images from Dockerfiles
# =============================================================================
# PURPOSE: Build edge-node, cloud-node, scheduler, orchestrator images
# INPUTS: Repository source code
# OUTPUTS: 4 Docker images tagged locally
# DESTRUCTIVE: No (builds only)
# SAFE: Yes
# REQUIRES_MANUAL_STEP: No
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"

echo "=== Building container images ==="
echo "Repository root: ${REPO_ROOT}"
echo "ECR registry: ${ECR_REGISTRY}"

IMAGES=("edge-node:edge/Dockerfile" "cloud-node:cloud/Dockerfile" "scheduler:scheduler/Dockerfile" "orchestrator:orchestrator/Dockerfile")

for entry in "${IMAGES[@]}"; do
  NAME="${entry%%:*}"
  DOCKERFILE="${entry##*:}"
  IMAGE_TAG="${ECR_REGISTRY}/${PROJECT_NAME}/${NAME}:latest"
  
  echo ""
  echo "--- Building ${NAME} ---"
  echo "Dockerfile: ${REPO_ROOT}/${DOCKERFILE}"
  echo "Tag: ${IMAGE_TAG}"
  
  docker build -f "${REPO_ROOT}/${DOCKERFILE}" -t "${IMAGE_TAG}" "${REPO_ROOT}"
  
  echo "--- ${NAME} built successfully ---"
done

echo ""
echo "=== All images built ==="
docker images --format "  {{.Repository}}:{{.Tag}} {{.Size}}" | grep "${PROJECT_NAME}"
