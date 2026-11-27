#!/bin/bash
# =============================================================================
# 04-install-k3s.sh — Install K3s on cloud node
# =============================================================================
# PURPOSE: Install K3s server on cloud EC2 instance
# INPUTS: CLOUD_PUBLIC_IP, CLOUD_INSTANCE_ID from rebuild.env
# OUTPUTS: K3s cluster running, kubectl configured
# DESTRUCTIVE: No (fresh install only)
# SAFE: Yes (requires SSM access to cloud node)
# REQUIRES_MANUAL_STEP: Yes — must run via SSM Session Manager
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"

cat <<'INSTRUCTIONS'
This script must be run INSIDE an SSM Session Manager session on the cloud EC2 instance.

To start an SSM session:
  aws ssm start-session --target <CLOUD_INSTANCE_ID> --region <AWS_REGION> --profile <AWS_PROFILE>

Then paste the commands below.
INSTRUCTIONS

echo ""
echo "=== K3s Installation Commands (run on cloud EC2 via SSM) ==="
echo ""
cat <<EOF
# --- On the cloud EC2 instance ---

# Install K3s (node name = instance hostname / PrivateDnsName, matching
# runbook Phase 7 — do NOT override --node-name, or it diverges from the
# AWS PrivateDnsName used in rebuild.env and validation gates)
curl -sfL https://get.k3s.io | K3S_TOKEN=\$(head -c 32 /dev/urandom | base64) sh -s - server \\
  --write-kubeconfig-mode 644

# Wait for node to be Ready
sudo kubectl get nodes

# Copy kubeconfig to ec2-user
mkdir -p /home/ec2-user/.kube
sudo cp /etc/rancher/k3s/k3s.yaml /home/ec2-user/.kube/config
sudo chown ec2-user:ec2-user /home/ec2-user/.kube/config

echo "K3s installed. kubeconfig at /home/ec2-user/.kube/config"
EOF

echo ""
echo "=== After running the above, copy kubeconfig to your local machine ==="
echo "scp ec2-user@${CLOUD_PUBLIC_IP}:/home/ec2-user/.kube/config ~/.kube/config"
echo "Then edit the server URL in ~/.kube/config to use ${CLOUD_PUBLIC_IP}"
