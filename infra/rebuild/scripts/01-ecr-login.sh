#!/bin/bash
# =============================================================================
# 01-ecr-login.sh — Authenticate Docker to ECR
# =============================================================================
# PURPOSE: Get ECR login token and authenticate Docker daemon
# INPUTS: AWS_REGION, AWS_PROFILE from rebuild.env
# OUTPUTS: Docker authenticated to ECR
# DESTRUCTIVE: No
# SAFE: Yes
# REQUIRES_MANUAL_STEP: No
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"

echo "=== Authenticating Docker to ECR ==="
echo "Registry: ${ECR_REGISTRY}"

aws ecr get-login-password --region "${AWS_REGION}" --profile "${AWS_PROFILE}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "=== ECR authentication successful ==="
