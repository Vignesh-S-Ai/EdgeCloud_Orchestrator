# New AWS Account Rebuild

## Step 1: AWS Account Preparation

- Create new AWS account at https://portal.aws.amazon.com
- Enable MFA on root user
- Create IAM admin user with programmatic access
- Configure AWS CLI: `aws configure --profile edgecloud`
- Select region: `export AWS_DEFAULT_REGION=ap-south-1`

## Step 2: Bootstrap IAM

Ensure the IAM user/role has: EC2FullAccess, RDSFullAccess, ECRFullAccess, SecretsManagerFullAccess, IAMFullAccess, VPCFullAccess, CloudWatchFullAccess, SSMFullAccess

## Step 3: Clone Repository

```bash
git clone <REPO_URL> EdgeCloud-Orchestrator
cd EdgeCloud-Orchestrator
```

## Step 4: Terraform Init + ECR (BEFORE EC2)

**CRITICAL: ECR repos and images must exist BEFORE EC2 instances boot.**

```bash
cd infra/terraform
terraform init
terraform apply -target=aws_ecr_repository.cloud_node \
  -target=aws_ecr_repository.scheduler \
  -target=aws_ecr_repository.orchestrator \
  -target=aws_ecr_repository.edge_node
```

## Step 5: Build and Push Images

```bash
cd ../..
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-south-1
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Authenticate
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_BASE}

# Build and push
docker build -f edge/Dockerfile -t ${ECR_BASE}/edgecloud/edge-node:latest . && docker push ${ECR_BASE}/edgecloud/edge-node:latest
docker build -f cloud/Dockerfile -t ${ECR_BASE}/edgecloud/cloud-node:latest . && docker push ${ECR_BASE}/edgecloud/cloud-node:latest
docker build -f scheduler/Dockerfile -t ${ECR_BASE}/edgecloud/scheduler:latest . && docker push ${ECR_BASE}/edgecloud/scheduler:latest
docker build -f orchestrator/Dockerfile -t ${ECR_BASE}/edgecloud/orchestrator:latest . && docker push ${ECR_BASE}/edgecloud/orchestrator:latest
```

## Step 6: Terraform Apply (Full Infrastructure)

```bash
cd infra/terraform
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

This creates: VPC, subnets, IGW, route tables, security groups, 2 EC2 instances, RDS, Secrets Manager, IAM roles, CloudWatch. EC2 user_data.sh pulls the ECR images we just pushed.

## Step 7: Collect Rebuild Values

```bash
cd ../..
bash infra/rebuild/scripts/00-collect-outputs.sh > infra/rebuild/rebuild.env
# Edit rebuild.env to fill in <MANUAL> values
source infra/rebuild/rebuild.env
```

## Step 8: Wait for Cloud EC2 Bootstrap

```bash
aws logs tail /edgecloud/ec2-services --follow --profile edgecloud
# Wait for "EdgeCloud init completed successfully"
```

## Step 9: Install K3s

SSM into cloud EC2:
```bash
aws ssm start-session --target ${CLOUD_INSTANCE_ID} --region ${AWS_REGION} --profile ${AWS_PROFILE}
```
Then:
```bash
curl -sfL https://get.k3s.io | sh -s - server --write-kubeconfig-mode 644
kubectl get nodes
mkdir -p /home/ec2-user/.kube
sudo cp /etc/rancher/k3s/k3s.yaml /home/ec2-user/.kube/config
sudo chown ec2-user:ec2-user /home/ec2-user/.kube/config
```

## Step 10: Install CloudCore

On cloud EC2:
```bash
VERSION=v1.23.1
wget https://github.com/kubeedge/kubeedge/releases/download/${VERSION}/keadm-${VERSION}-linux-amd64.tar.gz
tar xzf keadm-${VERSION}-linux-amd64.tar.gz
sudo cp keadm-${VERSION}-linux-amd64/keadm/keadm /usr/local/bin/
sudo keadm init --cloudcore-port=10002 --kube-config=/etc/rancher/k3s/k3s.yaml
```

## Step 11: Install EdgeCore

SSM into edge EC2:
```bash
# containerd
sudo dnf install -y containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml > /dev/null
sudo systemctl enable containerd && sudo systemctl start containerd

# CNI
CNI_VERSION="v1.3.0"
sudo mkdir -p /opt/cni/bin
curl -L "https://github.com/containernetworking/plugins/releases/download/${CNI_VERSION}/cni-plugins-linux-amd64-${CNI_VERSION}.tgz" | sudo tar -C /opt/cni/bin -xz

# crictl
CRICTL_VERSION="v1.28.0"
curl -L "https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/crictl-${CRICTL_VERSION}-linux-amd64.tar.gz" | sudo tar -C /usr/local/bin -xz

# EdgeCore
VERSION=v1.23.1
wget https://github.com/kubeedge/kubeedge/releases/download/${VERSION}/kubeedge-${VERSION}-linux-amd64.tar.gz
tar xzf kubeedge-${VERSION}-linux-amd64.tar.gz
sudo cp kubeedge-${VERSION}-linux-amd64/edge/edgecore /usr/local/bin/

# Get token from cloud, then:
sudo mkdir -p /etc/kubeedge
sudo tee /etc/kubeedge/config/config.yaml > /dev/null <<EOF
modules:
  edged:
    hostnameOverride: edge-ec2-node
    containerRuntime: containerd
  cloudHub:
    servers:
      - url: wss://${CLOUD_PUBLIC_IP}:10000
    token: ${TOKEN}
  deviceTwin:
    enabled: false
  eventBus:
    enabled: false
EOF

nohup sudo edgecore --config /etc/kubeedge/config/config.yaml > /var/log/edgecore.log 2>&1 &
```

## Step 12: Approve Edge Node

On cloud:
```bash
kubectl uncordon edge-ec2-node
kubectl label node edge-ec2-node kubernetes.io/hostname=edge-ec2-node
```

## Step 13: Deploy Applications

```bash
bash infra/rebuild/scripts/06-deploy-k8s.sh
```

## Step 14: Configure Rules

```bash
bash infra/rebuild/scripts/07-configure-rules.sh
```

## Step 15: Validate

```bash
bash infra/rebuild/scripts/08-validate.sh
```

## Step 16: Benchmark

See MASTER_REBUILD_RUNBOOK.md Phase 16.
