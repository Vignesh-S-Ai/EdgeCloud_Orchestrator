# Terraform Rebuild Safety Guide

## SAFE TO APPLY (from clean state)

| Resource | File |
|----------|------|
| aws_vpc.main | vpc.tf |
| aws_subnet.public | vpc.tf |
| aws_subnet.rds | vpc.tf |
| aws_internet_gateway.igw | vpc.tf |
| aws_route_table.public | vpc.tf |
| aws_route_table_association (both) | vpc.tf |
| aws_security_group.ec2 + rules | security_groups.tf |
| aws_security_group.rds + rules | security_groups.tf |
| aws_security_group.edge_node + rules | edge_node.tf |
| aws_ecr_repository (all 4) | ecr.tf |
| aws_ecr_lifecycle_policy | ecr.tf |
| aws_cloudwatch_log_group | cloudwatch.tf |
| aws_cloudwatch_metric_alarm | cloudwatch.tf |

## CONDITIONAL

| Resource | Condition |
|----------|-----------|
| aws_instance.cloud | AMI auto-resolves; safe if var.ami_id is empty |
| aws_instance.edge_node | Same |
| aws_eip.cloud | New EIP may differ from current |
| All IAM roles/policies | Safe if no name conflicts |

## MANUAL ONLY

| Resource | Manual Step |
|----------|-------------|
| aws_instance.cloud user_data | ECR images must exist BEFORE first boot |
| aws_instance.edge_node user_data | Containerd/EdgeCore installed manually via SSM after boot |
| aws_db_instance.main | PROVISIONED ONLY — no app connects |
| aws_secretsmanager_secret | Only read by user_data.sh for docker-compose .env |

## DO NOT BLINDLY APPLY (drift risk)

| Risk | Why |
|------|-----|
| EIP replacement | Changes public IP; SG rules and KubeEdge endpoints break |
| EC2 replacement | Loses Docker images, docker-compose, .env, EdgeCore install |
| SG rule changes | var.edge_public_ip must be correct before apply |
| RDS replacement | Data loss if instance class or engine changes |

## RECOMMENDED APPROACH

1. New account: Apply from scratch (no drift possible)
2. Existing state: Import first, then plan/apply carefully
3. Never apply over partial state without reviewing `terraform plan` output
