#!/bin/bash
# =============================================================================
# 08-validate.sh — Full validation of rebuilt system
# =============================================================================
# PURPOSE: Run all validation gates against rebuilt infrastructure
# INPUTS: kubectl access, CLOUD_PUBLIC_IP, EDGE_PUBLIC_IP from rebuild.env
# OUTPUTS: Pass/fail for each validation gate
# DESTRUCTIVE: No (read-only checks)
# SAFE: Yes
# REQUIRES_MANUAL_STEP: No
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"

PASS=0
FAIL=0
TOTAL=0

check() {
  TOTAL=$((TOTAL + 1))
  local name="$1"
  local result="$2"
  if [ "$result" = "PASS" ]; then
    PASS=$((PASS + 1))
    echo "  [PASS] ${name}"
  else
    FAIL=$((FAIL + 1))
    echo "  [FAIL] ${name}: ${result}"
  fi
}

echo "=== Full Validation ==="
echo ""

# --- Level 0: AWS Infrastructure ---
echo "--- Level 0: AWS Infrastructure ---"
if aws ec2 describe-instances --filters Name=tag:Project,Values=edgecloud --query 'Reservations[].Instances[].State.Name' --output text 2>/dev/null | grep -q "running"; then
  check "EC2 instances running" "PASS"
else
  check "EC2 instances running" "No running instances found"
fi

if aws ecr describe-repositories --repository-names "${PROJECT_NAME}/*" --region "${AWS_REGION}" --profile "${AWS_PROFILE}" >/dev/null 2>&1; then
  check "ECR repositories exist" "PASS"
else
  check "ECR repositories exist" "Repositories not found"
fi

# --- Level 1: K3s Cluster ---
echo ""
echo "--- Level 1: K3s Cluster ---"
if kubectl get nodes 2>/dev/null | grep -q "Ready"; then
  check "K3s cluster Ready" "PASS"
else
  check "K3s cluster Ready" "No Ready nodes"
fi

if kubectl get ns "${EDGE_NAMESPACE}" >/dev/null 2>&1; then
  check "Namespace exists" "PASS"
else
  check "Namespace exists" "Namespace not found"
fi

# --- Level 2: KubeEdge ---
echo ""
echo "--- Level 2: KubeEdge ---"
if kubectl get pods -n kubeedge 2>/dev/null | grep -q "Running"; then
  check "CloudCore running" "PASS"
else
  check "CloudCore running" "No CloudCore pod"
fi

RULES_COUNT=$(kubectl get rules -n "${EDGE_NAMESPACE}" --no-headers 2>/dev/null | wc -l)
if [ "$RULES_COUNT" -ge 4 ]; then
  check "4 Rules exist" "PASS"
else
  check "4 Rules exist" "Only ${RULES_COUNT} rules found"
fi

EPS_COUNT=$(kubectl get ruleendpoints -n "${EDGE_NAMESPACE}" --no-headers 2>/dev/null | wc -l)
if [ "$EPS_COUNT" -ge 2 ]; then
  check "2 RuleEndpoints exist" "PASS"
else
  check "2 RuleEndpoints exist" "Only ${EPS_COUNT} ruleendpoints found"
fi

# --- Level 3: Application Pods ---
echo ""
echo "--- Level 3: Application Pods ---"
PODS=$(kubectl get pods -n "${EDGE_NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
for POD in orchestrator scheduler cloud-node edge-node; do
  if echo "$PODS" | grep -q "$POD"; then
    STATUS=$(kubectl get pod -n "${EDGE_NAMESPACE}" -l app="${POD}" -o jsonpath='{.items[0].status.phase}' 2>/dev/null)
    RESTARTS=$(kubectl get pod -n "${EDGE_NAMESPACE}" -l app="${POD}" -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}' 2>/dev/null || echo "0")
    if [ "$STATUS" = "Running" ]; then
      check "${POD} pod Running" "PASS"
    else
      check "${POD} pod Running" "Status: ${STATUS}"
    fi
  else
    check "${POD} pod Running" "Pod not found"
  fi
done

# --- Level 4: Service Health ---
echo ""
echo "--- Level 4: Service Health ---"
ORCH_HEALTH=$(kubectl exec -n "${EDGE_NAMESPACE}" deployment/orchestrator -- curl -sf http://localhost:8003/health 2>/dev/null || echo "FAIL")
if echo "$ORCH_HEALTH" | grep -q "ok"; then
  check "Orchestrator health" "PASS"
else
  check "Orchestrator health" "Health check failed"
fi

SCHED_HEALTH=$(kubectl exec -n "${EDGE_NAMESPACE}" deployment/scheduler -- curl -sf http://localhost:8002/health 2>/dev/null || echo "FAIL")
if echo "$SCHED_HEALTH" | grep -q "ok"; then
  check "Scheduler health" "PASS"
else
  check "Scheduler health" "Health check failed"
fi

CLOUD_HEALTH=$(kubectl exec -n "${EDGE_NAMESPACE}" deployment/cloud-node -- curl -sf http://localhost:8001/health 2>/dev/null || echo "FAIL")
if echo "$CLOUD_HEALTH" | grep -q "ok"; then
  check "Cloud-node health" "PASS"
else
  check "Cloud-node health" "Health check failed"
fi

# --- Level 5: Edge through ServiceBus ---
echo ""
echo "--- Level 5: Edge ServiceBus Path ---"
EDGE_HEALTH=$(kubectl exec -n "${EDGE_NAMESPACE}" deployment/orchestrator -- curl -sf "http://${CLOUD_PRIVATE_IP}:9443/${EDGE_NODE_NAME}/${EDGE_NAMESPACE}/health" 2>/dev/null || echo "FAIL")
if echo "$EDGE_HEALTH" | grep -q "ok"; then
  check "Edge health via ServiceBus" "PASS"
else
  check "Edge health via ServiceBus" "ServiceBus path failed"
fi

# --- Level 6: Scheduler Decision ---
echo ""
echo "--- Level 6: Scheduler Decision ---"
DECISION=$(kubectl exec -n "${EDGE_NAMESPACE}" deployment/orchestrator -- python -c "
import httpx
r = httpx.post('http://scheduler.edgecloud.svc:8002/decision', json={
  'workload': {'workload_id': 'val', 'priority': 'high', 'workload_type': 'object_detection', 'estimated_compute': 0.5, 'estimated_inference_ms': 100, 'latency_requirement_ms': 200},
  'edge_url': 'http://${CLOUD_PRIVATE_IP}:9443/${EDGE_NODE_NAME}/${EDGE_NAMESPACE}',
  'cloud_url': 'http://cloud-node.edgecloud.svc:8001'
}, timeout=30)
print(r.json().get('target', 'UNKNOWN'))
" 2>/dev/null || echo "FAIL")
if [ "$DECISION" != "FAIL" ] && [ -n "$DECISION" ]; then
  check "Scheduler decision (${DECISION})" "PASS"
else
  check "Scheduler decision" "Failed to get decision"
fi

# --- Summary ---
echo ""
echo "==========================================="
echo "=== Validation Summary ==="
echo "==========================================="
echo "Total: ${TOTAL}"
echo "Pass:  ${PASS}"
echo "Fail:  ${FAIL}"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: ALL GATES PASSED"
  exit 0
else
  echo "RESULT: ${FAIL} GATES FAILED"
  exit 1
fi
