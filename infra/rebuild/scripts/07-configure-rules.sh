#!/bin/bash
# =============================================================================
# 07-configure-rules.sh — Create KubeEdge Rules and RuleEndpoints
# =============================================================================
# PURPOSE: Ensure all 4 Rules and 2 RuleEndpoints exist
# INPUTS: kubectl access
# OUTPUTS: 4 Rules, 2 RuleEndpoints in edgecloud namespace
# DESTRUCTIVE: No (creates only, does not delete existing)
# SAFE: Yes
# REQUIRES_MANUAL_STEP: No
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"
MANIFESTS="${REPO_ROOT}/infra/k3s"

echo "=== Configuring KubeEdge Rules and RuleEndpoints ==="

# --- RuleEndpoints ---
echo ""
echo "--- Applying RuleEndpoints ---"
kubectl apply -f "${MANIFESTS}/edgecloud-kubeedge-ruleendpoints.yaml"

# --- Rules ---
echo ""
echo "--- Applying Rules ---"
kubectl apply -f "${MANIFESTS}/edgecloud-kubeedge-rules.yaml"

# --- Verify ---
echo ""
echo "--- Verification ---"
echo "RuleEndpoints:"
kubectl get ruleendpoints -n "${EDGE_NAMESPACE}"
echo ""
echo "Rules:"
kubectl get rules -n "${EDGE_NAMESPACE}"

echo ""
echo "=== Rules and RuleEndpoints configured ==="
