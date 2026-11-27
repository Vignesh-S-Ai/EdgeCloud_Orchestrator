# ---------------------------------------------------------------------------
# Outputs — useful values after terraform apply
# ---------------------------------------------------------------------------

output "vpc_id" {
  description = "Project VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "Public subnet ID (EC2)"
  value       = aws_subnet.public.id
}

output "rds_subnet_id" {
  description = "RDS subnet ID"
  value       = aws_subnet.rds.id
}

output "ec2_public_ip" {
  description = "EC2 public IP (orchestrator endpoint)"
  value       = aws_eip.cloud.public_ip
}

output "ec2_eip" {
  description = "Elastic IP allocation ID"
  value       = aws_eip.cloud.id
}

output "ec2_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.cloud.id
}

output "ec2_security_group_id" {
  description = "EC2 security group ID"
  value       = aws_security_group.ec2.id
}

output "rds_endpoint" {
  description = "RDS endpoint (host:port)"
  value       = "${aws_db_instance.main.address}:${aws_db_instance.main.port}"
}

output "rds_address" {
  description = "RDS hostname"
  value       = aws_db_instance.main.address
}

output "rds_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.rds.id
}

output "ecr_cloud_node_url" {
  description = "ECR repository URL for cloud-node"
  value       = aws_ecr_repository.cloud_node.repository_url
}

output "ecr_scheduler_url" {
  description = "ECR repository URL for scheduler"
  value       = aws_ecr_repository.scheduler.repository_url
}

output "ecr_orchestrator_url" {
  description = "ECR repository URL for orchestrator"
  value       = aws_ecr_repository.orchestrator.repository_url
}

output "db_secret_arn" {
  description = "ARN of the DB credentials secret"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "orchestrator_url" {
  description = "Public orchestrator endpoint"
  value       = "http://${aws_eip.cloud.public_ip}"
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.edgecloud.name
}
