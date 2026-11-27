# ---------------------------------------------------------------------------
# EC2 Cloud Node — Amazon Linux 2023, t3.small
# ---------------------------------------------------------------------------

# Resolve latest Amazon Linux 2023 AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  ami = var.ami_id != "" ? var.ami_id : data.aws_ami.al2023.id
}

# Dynamic account ID — user_data ECR login works in ANY AWS account
data "aws_caller_identity" "current" {}

resource "aws_instance" "cloud" {
  ami                         = local.ami
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.ec2.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  associate_public_ip_address = true

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh", {
    account_id         = data.aws_caller_identity.current.account_id
    cloud_node_repo    = aws_ecr_repository.cloud_node.repository_url
    scheduler_repo     = aws_ecr_repository.scheduler.repository_url
    orchestrator_repo  = aws_ecr_repository.orchestrator.repository_url
    region             = var.aws_region
    db_secret_arn      = aws_secretsmanager_secret.db_credentials.arn
    db_host            = aws_db_instance.main.address
    db_port            = aws_db_instance.main.port
    db_name            = var.db_name
    docker_compose_b64 = base64encode(file("${path.module}/docker-compose.yml"))
  }))

  tags = {
    Name      = "${var.project_name}-cloud-node"
    Component = "cloud-node"
  }
}
