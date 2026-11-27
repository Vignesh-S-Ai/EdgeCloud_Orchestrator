#!/bin/bash
# =============================================================================
# 06-deploy-k8s.sh — Apply all Kubernetes manifests
# =============================================================================
# PURPOSE: Deploy namespace, deployments, services, rules, ruleendpoints
# INPUTS: kubectl access, ECR_REGISTRY from rebuild.env
# OUTPUTS: 4 pods Running, all services created
# DESTRUCTIVE: No (applies manifests, does not delete)
# SAFE: Yes (requires kubectl access)
# REQUIRES_MANUAL_STEP: No (if kubectl is configured)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"
MANIFESTS="${REPO_ROOT}/infra/k3s"

echo "=== Deploying Kubernetes manifests ==="
echo "Manifests directory: ${MANIFESTS}"
echo "ECR registry: ${ECR_REGISTRY}"
echo "Namespace: ${EDGE_NAMESPACE}"

# --- Step 1: Create namespace ---
echo ""
echo "--- Creating namespace ---"
kubectl apply -f "${MANIFESTS}/namespace.yaml"

# --- Step 2: Create ECR image pull secret ---
echo ""
echo "--- Creating ECR image pull secret ---"
ECR_TOKEN=$(aws ecr get-login-password --region "${AWS_REGION}" --profile "${AWS_PROFILE}")
kubectl create secret docker-registry ecr-registry-secret \
  --docker-server="${ECR_REGISTRY}" \
  --docker-username=AWS \
  --docker-password="${ECR_TOKEN}" \
  -n "${EDGE_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

# --- Step 2b: Normalize placeholder values + label cloud node for placement ---
# The three control-plane pods (orchestrator/scheduler/cloud-node) carry
# nodeSelector "node-role: cloud" (see infra/k3s/*-deployment.yaml); the edge
# pod carries kubernetes.io/hostname=edge-ec2-node. Label MUST exist first.
echo ""
echo "--- Preparing node placement (node-role: cloud) ---"
if [ -z "${CLOUD_PRIVATE_IP:-}" ] || [[ "${CLOUD_PRIVATE_IP}" == \<* ]]; then
  echo "CLOUD_PRIVATE_IP was a placeholder - deriving from AWS..."
  CLOUD_PRIVATE_IP=$(aws ec2 describe-instances --instance-ids "${CLOUD_INSTANCE_ID}" \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text \
    --region "${AWS_REGION}" --profile "${AWS_PROFILE}")
fi
# Derive the real K3s cloud node name from the cluster itself (never from stale docs)
CLOUD_NODE_NAME=$(kubectl get nodes -o name | grep -v edge-ec2-node | head -1 | sed 's|^node/||')
if [ -z "${CLOUD_NODE_NAME}" ]; then
  echo "ERROR: no cloud node found in cluster (kubectl get nodes)" >&2
  exit 1
fi
kubectl label node "${CLOUD_NODE_NAME}" node-role=cloud --overwrite
echo "Labeled cloud node: ${CLOUD_NODE_NAME} -> node-role=cloud"

# --- Step 3: Update image references in manifests ---
echo ""
echo "--- Updating image references for new account ---"
TEMP_DIR=$(mktemp -d)
cp "${MANIFESTS}"/*.yaml "${TEMP_DIR}/"

for f in "${TEMP_DIR}"/*-deployment*.yaml; do
  if [ -f "$f" ]; then
    # Replace old ECR URI with new one
    sed -i "s|325580898273\.dkr\.ecr\.ap-south-1\.amazonaws\.com|${ECR_REGISTRY}|g" "$f"
    # Replace old cloud node IP in orchestrator env
    sed -i "s|10\.0\.1\.113|${CLOUD_PRIVATE_IP:-<CLOUD_PRIVATE_IP>}|g" "$f"
  fi
done

# --- Step 4: Apply manifests ---
echo ""
echo "--- Applying deployments and services ---"
kubectl apply -f "${TEMP_DIR}/cloud-node-deployment.yaml"
kubectl apply -f "${TEMP_DIR}/cloud-node-service.yaml"
kubectl apply -f "${TEMP_DIR}/scheduler-deployment.yaml"
kubectl apply -f "${TEMP_DIR}/scheduler-service.yaml"
kubectl apply -f "${TEMP_DIR}/orchestrator-deployment.yaml"
kubectl apply -f "${TEMP_DIR}/orchestrator-service.yaml"
kubectl apply -f "${TEMP_DIR}/edge-node-deployment-edge.yaml"
kubectl apply -f "${TEMP_DIR}/edge-node-service.yaml"

# --- Step 5: Apply KubeEdge rules and ruleendpoints ---
echo ""
echo "--- Applying KubeEdge Rules and RuleEndpoints ---"
kubectl apply -f "${MANIFESTS}/edgecloud-kubeedge-ruleendpoints.yaml"
kubectl apply -f "${MANIFESTS}/edgecloud-kubeedge-rules.yaml"

# --- Cleanup ---
rm -rf "${TEMP_DIR}"

# --- Step 6: Wait for pods ---
echo ""
echo "--- Waiting for pods to reach Running state ---"
echo "This may take 2-5 minutes (image pull + model download on first run)."
kubectl wait --for=condition=ready pod -l app=cloud-node -n "${EDGE_NAMESPACE}" --timeout=300s 2>/dev/null || echo "Waiting for cloud-node..."
kubectl wait --for=condition=ready pod -l app=scheduler -n "${EDGE_NAMESPACE}" --timeout=300s 2>/dev/null || echo "Waiting for scheduler..."
kubectl wait --for=condition=ready pod -l app=orchestrator -n "${EDGE_NAMESPACE}" --timeout=300s 2>/dev/null || echo "Waiting for orchestrator..."

echo ""
echo "--- Final pod status ---"
kubectl get pods -n "${EDGE_NAMESPACE}" -o wide

echo ""
echo "=== Deployment complete ==="
