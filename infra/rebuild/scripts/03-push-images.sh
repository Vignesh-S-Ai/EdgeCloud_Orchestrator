#!/bin/bash
# =============================================================================
# 03-push-images.sh — Push all 4 images to ECR
# =============================================================================
# PURPOSE: Push built images to ECR repositories
# INPUTS: ECR_REGISTRY, PROJECT_NAME from rebuild.env, images from 02-build-images.sh
# OUTPUTS: 4 images in ECR
# DESTRUCTIVE: No (pushes only, overwrites :latest tags)
# SAFE: Yes
# REQUIRES_MANUAL_STEP: No
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"

echo "=== Pushing images to ECR ==="
echo "Registry: ${ECR_REGISTRY}"

# Ensure ECR repositories exist
for NAME in edge-node cloud-node scheduler orchestrator; do
  REPO_URL="${ECR_REGISTRY}/${PROJECT_NAME}/${NAME}"
  if ! aws ecr describe-repositories --repository-names "${PROJECT_NAME}/${NAME}" --region "${AWS_REGION}" --profile "${AWS_PROFILE}" >/dev/null 2>&1; then
    echo "Creating ECR repository: ${PROJECT_NAME}/${NAME}"
    aws ecr create-repository \
      --repository-name "${PROJECT_NAME}/${NAME}" \
      --region "${AWS_REGION}" \
      --profile "${AWS_PROFILE}" \
      --image-tag-mutability MUTABLE
  fi
done

# Push each image
for NAME in edge-node cloud-node scheduler orchestrator; do
  IMAGE_TAG="${ECR_REGISTRY}/${PROJECT_NAME}/${NAME}:latest"
  echo ""
  echo "--- Pushing ${NAME} ---"
  docker push "${IMAGE_TAG}"
  echo "--- ${NAME} pushed ---"
done

echo ""
echo "=== All images pushed ==="
echo "Verify: aws ecr describe-repositories --repository-names ${PROJECT_NAME}/* --region ${AWS_REGION}"
