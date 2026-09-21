# Master Rebuild Runbook

## Architecture Decision: Docker Compose vs Kubernetes

The current validated architecture uses **two deployment layers on the same cloud EC2**:

1. **Docker Compose (BOOTSTRAP):** Terraform user_data.sh installs Docker, builds a docker-compose stack with cloud-node, scheduler, and orchestrator. This is the infrastructure that Terraform creates.

2. **K3s + KubeEdge (RUNTIME):** K3s is installed manually on the cloud EC2 via SSM. K3s manages the same services as Kubernetes deployments. KubeEdge provides edge-cloud communication.

**For a new rebuild, follow this order:**
- Terraform creates EC2 + ECR + Docker Compose (bootstrap)
- Then install K3s + KubeEdge manually via SSM (runtime)

Both coexist: Docker Compose runs on the host, K3s runs the same services in pods.

---

## PHASE 0: Prerequisites

**PURPOSE:** Ensure all tools are available
**PREREQUISITES:** None
**COMMAND:**
```bash
terraform --version   # >= 1.0
docker --version      # any recent
kubectl version --client  # >= 1.28
aws --version         # any recent
ssm-plugin --version  # SSM Session Manager plugin
```
**PASS CRITERIA:** All commands return version output

---

## PHASE 1: AWS Account Preparation

**PURPOSE:** Configure AWS CLI profile
**PREREQUISITES:** AWS account with IAM user
**COMMAND:**
```bash
aws configure --profile edgecloud
# Enter: Access Key ID, Secret Access Key, Region (ap-south-1), Output (json)
aws sts get-caller-identity --profile edgecloud
```
**PASS CRITERIA:** Account ID returned. Record this — it is your AWS_ACCOUNT_ID.

---

## PHASE 2: Terraform Init + ECR Repos

**PURPOSE:** Initialize Terraform and create ECR repositories (images must exist before EC2 bootstraps)
**PREREQUISITES:** Phase 1 complete
**COMMAND:**
```bash
cd infra/terraform
terraform init
# Apply only ECR first (safe, no EC2 dependency)
terraform apply -target=aws_ecr_repository.cloud_node \
  -target=aws_ecr_repository.scheduler \
  -target=aws_ecr_repository.orchestrator \
  -target=aws_ecr_repository.edge_node \
  -target=aws_ecr_lifecycle_policy.untagged_clean
```
**PASS CRITERIA:** 4 ECR repositories created
**NOTE:** ECR repos must exist BEFORE images are built and pushed. Terraform creates them here.

---

## PHASE 3: Build and Push Images

**PURPOSE:** Build all 4 container images and push to ECR
**PREREQUISITES:** Phase 2 complete (ECR repos exist)
**COMMAND:**
```bash
source infra/rebuild/rebuild.env  # or set manually
bash infra/rebuild/scripts/01-ecr-login.sh
bash infra/rebuild/scripts/02-build-images.sh
bash infra/rebuild/scripts/03-push-images.sh
```
**PASS CRITERIA:** All 4 images visible in ECR
**NOTE:** Images MUST be in ECR before EC2 instances boot, because user_data.sh pulls them on first boot.

---

## PHASE 4: Terraform Apply (Full)

**PURPOSE:** Create all remaining AWS infrastructure
**PREREQUISITES:** Phase 3 complete (images in ECR)
**COMMAND:**
```bash
cd infra/terraform
# If edge_public_ip is unknown, leave empty for now
cat > terraform.tfvars <<EOF
aws_profile    = "edgecloud"
aws_region     = "ap-south-1"
project_name   = "edgecloud"
environment    = "development"
edge_public_ip = ""
EOF
terraform plan -out=tfplan
terraform apply tfplan
```
**PASS CRITERIA:** 49 resources created
**NOTE:** EC2 user_data.sh runs on first boot and pulls the ECR images we just pushed.

---

## PHASE 5: Collect Rebuild Outputs

**PURPOSE:** Gather all dynamic values for later steps
**PREREQUISITES:** Phase 4 complete
**COMMAND:**
```bash
bash infra/rebuild/scripts/00-collect-outputs.sh > infra/rebuild/rebuild.env
# Edit rebuild.env to fill in <MANUAL> values
```
**PASS CRITERIA:** rebuild.env has all values filled

---

## PHASE 6: Wait for Cloud EC2 Bootstrap

**PURPOSE:** user_data.sh installs Docker, pulls ECR images, starts docker-compose
**PREREQUISITES:** Phase 4 complete (EC2 running, images in ECR)
**COMMAND:**
```bash
CLOUD_IP=$(terraform output -raw ec2_public_ip)
ssh ec2-user@${CLOUD_IP} "sudo tail -f /var/log/edgecloud-init.log"
# OR monitor via CloudWatch:
aws logs tail /edgecloud/ec2-services --follow --profile edgecloud
```
**PASS CRITERIA:** Logs show "EdgeCloud init completed successfully"

---

## PHASE 7: Install K3s on Cloud Node

**PURPOSE:** Create Kubernetes cluster on cloud EC2
**PREREQUISITES:** Phase 6 complete (cloud EC2 running)
**COMMAND:** SSM into cloud EC2:
```bash
aws ssm start-session --target $(terraform output -raw ec2_instance_id) --region ap-south-1 --profile edgecloud
```
Then on the cloud EC2:
```bash
# Install K3s
curl -sfL https://get.k3s.io | sh -s - server --write-kubeconfig-mode 644

# Wait for node Ready
kubectl get nodes

# Copy kubeconfig
mkdir -p /home/ec2-user/.kube
sudo cp /etc/rancher/k3s/k3s.yaml /home/ec2-user/.kube/config
sudo chown ec2-user:ec2-user /home/ec2-user/.kube/config
```
**PASS CRITERIA:** `kubectl get nodes` shows cloud node Ready
**NOTE:** Get the node name from `kubectl get nodes` — use it as CLOUD_NODE_NAME in rebuild.env.

---

## PHASE 8: Configure kubectl Locally

**PURPOSE:** Local kubectl access
**PREREQUISITES:** Phase 7 complete
**COMMAND:**
```bash
CLOUD_IP=$(terraform output -raw ec2_public_ip)
scp ec2-user@${CLOUD_IP}:/home/ec2-user/.kube/config ~/.kube/config
# Edit ~/.kube/config: replace server URL IP with ${CLOUD_IP}
```
**PASS CRITERIA:** `kubectl get nodes` returns from local machine

---

## PHASE 9: Install CloudCore

**PURPOSE:** KubeEdge cloud-side agent
**PREREQUISITES:** Phase 7 complete (K3s running)
**COMMAND:** On cloud EC2 via SSM:
```bash
VERSION=v1.23.1
wget https://github.com/kubeedge/kubeedge/releases/download/${VERSION}/keadm-${VERSION}-linux-amd64.tar.gz
tar xzf keadm-${VERSION}-linux-amd64.tar.gz
sudo cp keadm-${VERSION}-linux-amd64/keadm/keadm /usr/local/bin/
sudo keadm init --cloudcore-port=10002 --kube-config=/etc/rancher/k3s/k3s.yaml
```
**PASS CRITERIA:** `kubectl get pods -n kubeedge` shows cloudcore Running

---

## PHASE 10: Prepare Edge Node

**PURPOSE:** Install containerd, CNI, crictl, EdgeCore on edge EC2
**PREREQUISITES:** Phase 4 complete (edge EC2 running)
**COMMAND:** SSM into edge EC2:
```bash
# Install containerd
sudo dnf install -y containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml > /dev/null
sudo systemctl enable containerd && sudo systemctl start containerd

# Install CNI plugins
CNI_VERSION="v1.3.0"
sudo mkdir -p /opt/cni/bin
curl -L "https://github.com/containernetworking/plugins/releases/download/${CNI_VERSION}/cni-plugins-linux-amd64-${CNI_VERSION}.tgz" | sudo tar -C /opt/cni/bin -xz

# Install crictl
CRICTL_VERSION="v1.28.0"
curl -L "https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz" | sudo tar -C /usr/local/bin -xz

# Install EdgeCore
VERSION=v1.23.1
wget https://github.com/kubeedge/kubeedge/releases/download/${VERSION}/kubeedge-${VERSION}-linux-amd64.tar.gz
tar xzf kubeedge-${VERSION}-linux-amd64.tar.gz
sudo cp kubeedge-${VERSION}-linux-amd64/edge/edgecore /usr/local/bin/
```
**PASS CRITERIA:** `containerd --version`, `crictl --version`, `edgecore --version` all return

---

## PHASE 11: Configure and Start EdgeCore

**PURPOSE:** Connect edge to cloud via KubeEdge
**PREREQUISITES:** Phase 9 + Phase 10 complete
**COMMAND:**
```bash
# On CLOUD node, get token:
TOKEN=$(kubectl get secret -n kubeedge tokensecret -o jsonpath='{.data.tokendata}' | base64 -d)
echo "Token: ${TOKEN}"

# On EDGE node, create config:
sudo mkdir -p /etc/kubeedge
sudo tee /etc/kubeedge/config/config.yaml > /dev/null <<EOF
modules:
  edged:
    hostnameOverride: edge-ec2-node
    containerRuntime: containerd
  cloudHub:
    servers:
      - url: wss://<CLOUD_PUBLIC_IP>:10000
    token: ${TOKEN}
  deviceTwin:
    enabled: false
  eventBus:
    enabled: false
EOF

# Start EdgeCore
nohup sudo edgecore --config /etc/kubeedge/config/config.yaml > /var/log/edgecore.log 2>&1 &

# Verify from CLOUD node:
kubectl get nodes
```
**PASS CRITERIA:** `kubectl get nodes` shows edge-ec2-node

---

## PHASE 12: Approve Edge Node

**PURPOSE:** Enable scheduling on edge node
**PREREQUISITES:** Phase 11 complete
**COMMAND:**
```bash
kubectl uncordon edge-ec2-node
kubectl label node edge-ec2-node kubernetes.io/hostname=edge-ec2-node
```
**PASS CRITERIA:** Edge node shows as Ready (not SchedulingDisabled)

---

## PHASE 13: Deploy Kubernetes Manifests

**PURPOSE:** Deploy all application workloads
**PREREQUISITES:** Phase 12 complete
**COMMAND:**
```bash
source infra/rebuild/rebuild.env
bash infra/rebuild/scripts/06-deploy-k8s.sh
```
**PASS CRITERIA:** 4 pods in Running state, RESTARTS=0

---

## PHASE 14: Configure KubeEdge Rules

**PURPOSE:** Set up ServiceBus routing
**PREREQUISITES:** Phase 13 complete
**COMMAND:**
```bash
bash infra/rebuild/scripts/07-configure-rules.sh
```
**PASS CRITERIA:** 4 Rules, 2 RuleEndpoints exist

---

## PHASE 15: Validate

**PURPOSE:** Confirm system works
**PREREQUISITES:** Phase 14 complete
**COMMAND:**
```bash
bash infra/rebuild/scripts/08-validate.sh
```
**PASS CRITERIA:** All validation gates pass

---

## PHASE 16: Benchmark

**PURPOSE:** Confirm performance is in expected order of magnitude
**PREREQUISITES:** Phase 15 complete
**COMMAND:**
```bash
kubectl exec -n edgecloud deployment/orchestrator -- python -c "
import httpx, time
async def bench():
    async with httpx.AsyncClient() as c:
        # Warm up cache
        for _ in range(3):
            await c.post('http://scheduler.edgecloud.svc:8002/decision', json={
                'workload': {'workload_id': 'w', 'priority': 'high', 'workload_type': 'object_detection', 'estimated_compute': 0.5, 'estimated_inference_ms': 100, 'latency_requirement_ms': 200},
                'edge_url': 'http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud',
                'cloud_url': 'http://cloud-node.edgecloud.svc:8001'
            }, timeout=30)
        # Measure
        t0 = time.time()
        r = await c.post('http://scheduler.edgecloud.svc:8002/decision', json={
            'workload': {'workload_id': 'bench', 'priority': 'high', 'workload_type': 'object_detection', 'estimated_compute': 0.5, 'estimated_inference_ms': 100, 'latency_requirement_ms': 200},
            'edge_url': 'http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud',
            'cloud_url': 'http://cloud-node.edgecloud.svc:8001'
        }, timeout=30)
        ms = (time.time() - t0) * 1000
        print(f'Cached /decision: {ms:.0f}ms (target: ~66ms order)')
import anyio
anyio.run(bench)
"
```
**PASS CRITERIA:** Cached C1 in ~66ms order of magnitude
**NOTE:** Replace `<CLOUD_PRIVATE_IP>` with actual value from rebuild.env.
