# Recovery Secrets and Credentials Guide

**NEVER store actual secrets in git or documentation.**

## AWS Access

- **PURPOSE:** Bootstrap all infrastructure
- **WHERE USED:** Terraform, AWS CLI, ECR login, SSM
- **HOW TO GENERATE:** Create IAM user/role with AdminAccess for bootstrap; use least-privilege for runtime
- **WHERE STORED:** Local AWS CLI profile (`~/.aws/credentials`)
- **INJECT:** `aws configure --profile edgecloud` or set `AWS_PROFILE=edgecloud`

## ECR Authentication

- **PURPOSE:** Pull container images on EC2 instances
- **WHERE USED:** Docker daemon on cloud and edge EC2
- **HOW TO GENERATE:** `aws ecr get-login-password --region <REGION>`
- **INJECT:** `docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com`
- **NOTE:** In a new account, ECR URIs change (new account ID). Update all deployment manifests.

## KubeEdge Token

- **PURPOSE:** EdgeCore registration with CloudCore
- **WHERE USED:** EdgeCore configuration (/etc/kubeedge/config)
- **HOW TO GENERATE:** `kubectl get secret -n kubeedge tokensecret -o jsonpath='{.data.tokendata}' | base64 -d`
- **WHERE STORED:** EdgeCore config file on edge EC2
- **INJECT:** Write to EdgeCore config during KubeEdge setup
- **REGENERATE:** Re-run `keadm gettoken` on cloud node

## KubeEdge Certificates

- **PURPOSE:** CloudHub TLS (port 10002) and WebSocket authentication
- **WHERE USED:** CloudCore and EdgeCore
- **HOW TO GENERATE:** `keadm cert` or from KubeEdge default cert generation
- **WHERE STORED:** /etc/kubeedge/certs/ on both cloud and edge
- **INJECT:** During KubeEdge installation via keadm

## K3s Kubeconfig

- **PURPOSE:** kubectl access to K3s cluster
- **WHERE USED:** Local machine for kubectl commands
- **HOW TO GENERATE:** Copy from /etc/rancher/k3s/k3s.yaml on cloud CP node
- **WHERE STORED:** ~/.kube/config on local machine (or SSM session)
- **INJECT:** `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml`

## ECR ImagePull Secret

- **PURPOSE:** Kubernetes pods pull images from private ECR
- **WHERE USED:** imagePullSecrets in all deployments
- **HOW TO GENERATE:** `kubectl create secret docker-registry ecr-registry-secret --docker-server=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com --docker-username=AWS --docker-password=<ECR_TOKEN> -n edgecloud`
- **REGENERATE:** ECR tokens expire after 12 hours; regenerate before deploying

## Database Credentials (PROVISIONED ONLY)

- **PURPOSE:** RDS PostgreSQL access (not used by application)
- **WHERE USED:** Terraform creates and stores in Secrets Manager
- **HOW TO GENERATE:** Terraform auto-generates via random_password
- **WHERE STORED:** AWS Secrets Manager (edgecloud/db-credentials)
- **NOTE:** No application code reads this. Provisioned for future use.

## SSH Key Pair (OPTIONAL)

- **PURPOSE:** Direct SSH access to EC2 (SSM preferred)
- **WHERE USED:** EC2 instance key pair
- **HOW TO GENERATE:** `aws ec2 create-key-pair` or import existing
- **NOTE:** SSM Session Manager is the recommended access method. SSH is optional.

## Placeholder Values for New Account

- `<REPLACE_WITH_NEW_AWS_ACCOUNT_ID>` — 12-digit account ID
- `<REPLACE_WITH_NEW_ECR_REGION>` — target region
- `<REPLACE_WITH_NEW_EIP>` — public IP after Terraform apply
- `<REPLACE_WITH_NEW_VPC_ID>` — VPC ID after Terraform apply
- `<GENERATE_NEW_KUBEEDGE_TOKEN>` — keadm gettoken on new cloud node
- `<GENERATE_NEW_KUBEEDGE_CERTS>` — keadm cert on new cloud node
- `<GENERATE_NEW_ECR_LOGIN>` — aws ecr get-login-password
