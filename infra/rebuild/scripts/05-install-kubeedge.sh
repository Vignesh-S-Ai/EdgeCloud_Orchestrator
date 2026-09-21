#!/bin/bash
# =============================================================================
# 05-install-kubeedge.sh — Install CloudCore + EdgeCore
# =============================================================================
# PURPOSE: Install KubeEdge CloudCore on cloud and EdgeCore on edge
# INPUTS: CLOUD_PUBLIC_IP, EDGE_PUBLIC_IP, KUBEEDGE_VERSION from rebuild.env
# OUTPUTS: CloudCore running on cloud, EdgeCore running on edge
# DESTRUCTIVE: No
# SAFE: Yes (requires SSM access to both nodes)
# REQUIRES_MANUAL_STEP: Yes — must run via SSM on each node
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$SCRIPT_DIR")/rebuild.env"

cat <<'INSTRUCTIONS'
This script provides commands to run on each node via SSM.
Start separate SSM sessions for cloud and edge nodes.
INSTRUCTIONS

echo ""
echo "=========================================="
echo "=== PART A: CloudCore (run on cloud EC2) ==="
echo "=========================================="
echo ""
cat <<EOF
# --- On the cloud EC2 instance (SSM session) ---

# Install keadm
VERSION=${KUBEEDGE_VERSION}
wget https://github.com/kubeedge/kubeedge/releases/download/\${VERSION}/keadm-\${VERSION}-linux-amd64.tar.gz
tar xzf keadm-\${VERSION}-linux-amd64.tar.gz
sudo cp keadm-\${VERSION}-linux-amd64/keadm/keadm /usr/local/bin/

# Initialize CloudCore
sudo keadm init --cloudcore-port=10002 --kube-config=/etc/rancher/k3s/k3s.yaml

# Verify
sudo kubectl get pods -n kubeedge

echo "CloudCore installed and running"
EOF

echo ""
echo "=========================================="
echo "=== PART B: EdgeCore (run on edge EC2) ==="
echo "=========================================="
echo ""
cat <<EOF
# --- On the edge EC2 instance (SSM session) ---

# 1. Install containerd
sudo dnf install -y containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml > /dev/null
sudo systemctl enable containerd
sudo systemctl start containerd

# 2. Install CNI plugins
CNI_VERSION="v1.3.0"
sudo mkdir -p /opt/cni/bin
curl -L "https://github.com/containernetworking/plugins/releases/download/\${CNI_VERSION}/cni-plugins-linux-amd64-\${CNI_VERSION}.tgz" | sudo tar -C /opt/cni/bin -xz

# 3. Install crictl
CRICTL_VERSION="v1.28.0"
curl -L "https://github.com/kubernetes-sigs/cri-tools/releases/download/\${CRICTL_VERSION}/crictl-\${CRICTL_VERSION}-linux-amd64.tar.gz" | sudo tar -C /usr/local/bin -xz

# 4. Install EdgeCore
VERSION=${KUBEEDGE_VERSION}
wget https://github.com/kubeedge/kubeedge/releases/download/\${VERSION}/kubeedge-\${VERSION}-linux-amd64.tar.gz
tar xzf kubeedge-\${VERSION}-linux-amd64.tar.gz
sudo cp kubeedge-\${VERSION}-linux-amd64/edge/edgecore /usr/local/bin/

# 5. Get token from cloud node
# Run this on CLOUD node first:
#   sudo kubectl get secret -n kubeedge tokensecret -o jsonpath='{.data.tokendata}' | base64 -d
# Then paste the token below:

TOKEN="<PASTE_TOKEN_FROM_CLOUD_NODE>"

# 6. Create EdgeCore config
sudo mkdir -p /etc/kubeedge
sudo tee /etc/kubeedge/config/config.yaml > /dev/null <<EDGECONFIG
modules:
  edged:
    hostnameOverride: ${EDGE_NODE_NAME}
    containerRuntime: containerd
  cloudHub:
    servers:
      - url: wss://${CLOUD_PUBLIC_IP}:10000
    token: \${TOKEN}
  deviceTwin:
    enabled: false
  eventBus:
    enabled: false
EDGECONFIG

# 7. Start EdgeCore (background, with log)
nohup sudo edgecore --config /etc/kubeedge/config/config.yaml > /var/log/edgecore.log 2>&1 &

# 8. Verify connection from cloud node
# On CLOUD node: sudo kubectl get nodes
# Edge should appear as edge-ec2-node

echo "EdgeCore started. Verify node registration from cloud."
EOF

echo ""
echo "=========================================="
echo "=== PART C: Approve edge node (run on cloud) ==="
echo "=========================================="
echo ""
cat <<EOF
# --- On the cloud EC2 instance ---

# Uncordon edge node (enable scheduling)
sudo kubectl uncordon ${EDGE_NODE_NAME}

# Verify
sudo kubectl get nodes
# Should show: edge-ec2-node Ready
EOF
