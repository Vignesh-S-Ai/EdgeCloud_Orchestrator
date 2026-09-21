# Disaster Recovery Scenarios

## Scenario A: Only Edge EC2 Lost

**WHAT IS LOST:** Edge EC2 instance, EdgeCore, edge pod, edge containerd, edge ECR images
**WHAT SURVIVES:** Cloud EC2, K3s cluster, CloudCore, orchestrator, scheduler, cloud-node, all K8s resources
**REBUILD FROM:** Terraform (edge_node.tf) + manual EdgeCore reinstallation
**EXACT STEPS:**
1. `terraform apply -target=aws_instance.edge_node` (recreates edge EC2)
2. SSM into edge node, install containerd + CNI + EdgeCore (see KUBEEDGE_REBUILD_BLUEPRINT.md)
3. Pull edge image from ECR: `docker pull <ECR_URL>/edge-node:latest`
4. Apply edge-node-deployment-edge.yaml: `kubectl apply -f infra/k3s/edge-node-deployment-edge.yaml -n edgecloud`
5. Wait for edge node Ready: `kubectl get nodes`
6. Verify edge pod Running: `kubectl get pods -n edgecloud`
7. Test ServiceBus path: `kubectl exec -n edgecloud deployment/orchestrator -- curl -sf http://<CLOUD_PRIVATE_IP>:9443/edge-ec2-node/edgecloud/health`
**VALIDATION:** Edge pod Running, RESTARTS=0, /health through ServiceBus returns 200
**ESTIMATED TIME:** 15-20 minutes
**DEPENDENCIES:** Cloud EC2 must be running, ECR must have edge image

## Scenario B: Only Cloud EC2 Lost

**WHAT IS LOST:** Cloud EC2, K3s cluster, CloudCore, all pods, all K8s resources, EIP
**WHAT SURVIVES:** Edge EC2 (but edge pod loses K3s connectivity), ECR images, Terraform state
**REBUILD FROM:** Full Terraform apply + K3s reinstall + KubeEdge reinstall + all K8s manifests
**EXACT STEPS:**
1. `terraform apply` (recreates cloud EC2, EIP)
2. SSH/SSM into cloud node (user_data installs Docker, pulls ECR images, starts docker-compose — this is the non-K3s path)
3. Install K3s: `curl -sfL https://get.k3s.io | K3S_TOKEN=<TOKEN> sh -s - server --write-kubeconfig-mode 644`
4. Install CloudCore: `keadm init --cloudcore-port=10002 --kube-config=/etc/rancher/k3s/k3s.yaml`
5. Create namespace, Rules, RuleEndpoints, deployments, services (apply all manifests in order)
6. Reconfigure edge node EdgeCore to point to new CloudCore
7. Verify all 4 pods Running
8. Test full ServiceBus path
**VALIDATION:** 4 pods Running, RESTARTS=0, edge reachable through ServiceBus
**ESTIMATED TIME:** 45-60 minutes
**DEPENDENCIES:** ECR images must exist, edge node must be reconfigured

## Scenario C: Both EC2 Instances Lost

**WHAT IS LOST:** Everything — all infrastructure, all pods, all K8s state
**WHAT SURVIVES:** ECR images (if ECR not deleted), Terraform code, application code
**REBUILD FROM:** Full rebuild from repository (see MASTER_REBUILD_RUNBOOK.md)
**EXACT STEPS:** Follow phases 0-29 of MASTER_REBUILD_RUNBOOK.md
**VALIDATION:** Full validation checklist (34 gates)
**ESTIMATED TIME:** 2-3 hours
**DEPENDENCIES:** Repository, AWS credentials, Docker, kubectl, Terraform

## Scenario D: Entire VPC Lost

**WHAT IS LOST:** VPC, subnets, EC2 instances, EIP, security groups, all resources inside VPC
**WHAT SURVIVES:** ECR repositories (not VPC-dependent), Secrets Manager, CloudWatch, IAM roles
**REBUILD FROM:** `terraform apply` recreates VPC and all contained resources
**EXACT STEPS:** Same as Scenario C — full rebuild
**VALIDATION:** Full validation checklist
**ESTIMATED TIME:** 2-3 hours

## Scenario E: Entire AWS Account Lost

**WHAT IS LOST:** Everything — all AWS resources, all accounts, all IAM
**WHAT SURVIVES:** Repository code only
**REBUILD FROM:** New AWS account + full rebuild (see NEW_AWS_ACCOUNT_REBUILD.md)
**EXACT STEPS:** Follow NEW_AWS_ACCOUNT_REBUILD.md
**VALIDATION:** Full validation checklist
**ESTIMATED TIME:** 3-4 hours

## Scenario F: New AWS Account and New Region

**WHAT IS LOST:** All region-specific resources
**WHAT SURVIVES:** Repository code
**REBUILD FROM:** Same as Scenario E
**EXACT STEPS:** Follow NEW_AWS_ACCOUNT_REBUILD.md with new region
**NOTES:** Update var.aws_region in variables.tf. All resource names will be new. ECR URIs change (new account ID). All K8s manifests need updated image URIs.
**VALIDATION:** Full validation checklist
**ESTIMATED TIME:** 3-4 hours

## Scenario G: ECR Repositories Lost

**WHAT IS LOST:** Container images
**WHAT SURVIVES:** All infrastructure, all running pods (until restart)
**REBUILD FROM:** Rebuild images from Dockerfiles, push to new ECR repos
**EXACT STEPS:**
1. Create new ECR repos: `aws ecr create-repository --repository-name edgecloud/edge-node ...`
2. Build images: `docker build -f edge/Dockerfile -t <NEW_ECR>/edge-node:latest .`
3. Push: `docker push <NEW_ECR>/edge-node:latest`
4. Update all K8s deployment manifests with new image URIs
5. Apply updated manifests
**VALIDATION:** All pods Running with new images
**ESTIMATED TIME:** 30-45 minutes

## Scenario H: Kubernetes Cluster Lost (AWS Infrastructure Remains)

**WHAT IS LOST:** K3s cluster, all K8s resources, CloudCore, all pods
**WHAT SURVIVES:** EC2 instances, ECR images, docker-compose stack (cloud-node, scheduler, orchestrator on cloud EC2)
**REBUILD FROM:** Reinstall K3s + CloudCore + apply manifests
**EXACT STEPS:**
1. Uninstall K3s: `/usr/local/bin/k3s-uninstall.sh` on cloud, `/usr/local/bin/k3s-agent-uninstall.sh` on edge
2. Reinstall K3s (see Scenario B steps 3-4)
3. Apply all manifests in order
**VALIDATION:** 4 pods Running, ServiceBus path works
**ESTIMATED TIME:** 30-45 minutes

## Scenario I: KubeEdge Registration Lost

**WHAT IS LOST:** EdgeCore-CloudCore connection, ServiceBus routing
**WHAT SURVIVES:** K3s cluster, all pods, edge pod running (but unreachable from cloud)
**REBUILD FROM:** Re-register edge node with CloudCore
**EXACT STEPS:**
1. On edge: restart EdgeCore (it reconnects automatically if config is valid)
2. If token expired: `keadm gettoken` on cloud, update EdgeCore config, restart
3. Verify: `kubectl get nodes` shows edge node Ready
4. Test ServiceBus path
**VALIDATION:** Edge node Ready, ServiceBus returns 200
**ESTIMATED TIME:** 5-10 minutes

## Scenario J: Container Images Lost

**WHAT IS LOST:** Running pods may crash if images are evicted
**WHAT SURVIVES:** Infrastructure, K8s resources, ECR (if not deleted)
**REBUILD FROM:** Rebuild images from Dockerfiles, push to ECR, restart pods
**EXACT STEPS:**
1. Build: `docker build -f <module>/Dockerfile -t <ECR>/<name>:latest .`
2. Push: `docker push <ECR>/<name>:latest`
3. Restart: `kubectl rollout restart deployment/<name> -n edgecloud`
**VALIDATION:** Pods Running, RESTARTS=0
**ESTIMATED TIME:** 15-20 minutes
