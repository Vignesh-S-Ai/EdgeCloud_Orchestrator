# Rebuild Version Matrix

## Exact Versions (from evidence)

| Component | Version | Source |
|-----------|---------|--------|
| AWS Region | ap-south-1 (Mumbai) | Terraform variables.tf |
| AWS Provider | ~> 5.0 | providers.tf |
| Terraform | >= 1.0 | providers.tf |
| K3s (cloud CP) | v1.32.13+k3s1 | kubectl output (current cluster) |
| K3s (edge) | v1.32.10-kubeedge-v1.23.1-dirty | kubectl output (current cluster) |
| KubeEdge | v1.23.1-dirty | kubectl describe node |
| CloudCore | bundled with KubeEdge v1.23.1 | KubeEdge helm chart |
| EdgeCore | bundled with KubeEdge v1.23.1 | KubeEdge helm chart |
| Python | 3.11 | Dockerfiles (FROM python:3.11-slim) |
| FastAPI | >= 0.115, < 1.0 | requirements.txt (all modules) |
| Pydantic | >= 2.7, < 3.0 | requirements.txt (all modules) |
| Ultralytics | >= 8.3, < 9.0 | edge/requirements.txt, cloud/requirements.txt |
| PyTorch | >= 2.3, < 3.0 (CPU-only) | requirements.txt + Dockerfiles |
| OpenCV | >= 4.10, < 5.0 (headless) | requirements.txt + Dockerfiles |
| psutil | >= 5.9, < 7.0 | edge/requirements.txt, cloud/requirements.txt |
| httpx | >= 0.24, < 1.0 | orchestrator/scheduler requirements.txt |
| anyio | >= 4.0, < 5.0 | scheduler/requirements.txt |
| YOLO model | yolov8n.pt (~6MB) | Lazy-downloaded at runtime |
| Amazon Linux | 2023 (AL2023) | ec2.tf AMI filter |
| Container runtime | containerd (K3s bundled) | K3s installation |
| Docker (cloud EC2) | latest via dnf | user_data.sh |
| Docker Compose | latest standalone binary | user_data.sh |

## Unknown / Must Verify During Rebuild

| Component | Status |
|-----------|--------|
| Exact AL2023 AMI ID | Changes by region/date — use Terraform data source auto-resolve |
| Exact K3s install script URL | Use `https://get.k3s.io` (latest stable) |
| Exact CloudCore Helm chart version | Must match KubeEdge v1.23.1 release |
| containerd version on edge | Installed via K3s or manual — verify during rebuild |
| CNI plugin version | Installed by K3s — verify during rebuild |
| Kubernetes API version | Determined by K3s version |

## Image References (new account)

ECR URIs are ACCOUNT-SPECIFIC. For a new account, generate URIs dynamically:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
# Images: ${ECR_BASE}/edgecloud/edge-node:latest
#         ${ECR_BASE}/edgecloud/cloud-node:latest
#         ${ECR_BASE}/edgecloud/scheduler:latest
#         ${ECR_BASE}/edgecloud/orchestrator:latest
```

The rebuild script `06-deploy-k8s.sh` automatically updates image references in K8s manifests using `sed` replacement of the old account ID with the new one.

**Current account image digests (for reference only — do not use in new account):**

| Image | Current Digest |
|-------|---------------|
| scheduler | sha256:d1aabd2415380d1013eeb1f212983d457566f7ce8c6a24a23b1cce1ca7ba037e |
| edge-node | REBUILD-GENERATED |
| cloud-node | REBUILD-GENERATED |
| orchestrator | REBUILD-GENERATED |
