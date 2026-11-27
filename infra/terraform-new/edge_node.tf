# ---------------------------------------------------------------------------
# Dedicated Edge EC2 Node (KubeEdge EdgeCore-only)
# ---------------------------------------------------------------------------
# Migration target for the unstable WSL2 edge runtime. NEW, purely ADDITIVE
# resource set. EdgeCore-ONLY: NO K3s server, NO Kubernetes kubelet, and exactly
# one containerd (installed in a later gate via SSM, not here).
#
# The EdgeCore node initiates an OUTBOUND KubeEdge WebSocket connection to
# CloudCore at the cloud node's Elastic IP:10000. It therefore needs internet
# egress only; it does NOT need inbound KubeEdge ports, so this security group
# is egress-only (deny inbound by default). No Kubernetes API (6443) or
# kubelet (10250) ports are exposed because this is not a k3s/node.
# ---------------------------------------------------------------------------

variable "edge_instance_type" {
  description = "EC2 instance type for the dedicated KubeEdge edge node"
  type        = string
  default     = "t3.medium"
}

variable "edge_root_volume_size" {
  description = "Root EBS volume size in GB for the dedicated edge node"
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# Security group — egress-only (deny inbound by default)
# ---------------------------------------------------------------------------

resource "aws_security_group" "edge_node" {
  name        = "${var.project_name}-edge-node-sg"
  description = "Security group for the dedicated KubeEdge edge node (egress-only)"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-edge-node-sg" }
}

resource "aws_vpc_security_group_egress_rule" "edge_all" {
  security_group_id = aws_security_group.edge_node.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All outbound (ECR pull, model download, KubeEdge WebSocket to CloudCore)"
}

# ---------------------------------------------------------------------------
# IAM role + instance profile — least privilege
#   - SSM Session Manager (managed policy)
#   - ECR pull (reuses the existing least-privilege ecr_pull policy document)
#   No secrets/RDS access: the edge node does not need them.
# ---------------------------------------------------------------------------

resource "aws_iam_role" "edge_node" {
  name               = "${var.project_name}-edge-node-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = { Component = "edge-node-instance" }
}

resource "aws_iam_role_policy" "edge_node_ecr_pull" {
  name   = "${var.project_name}-edge-node-ecr-pull"
  role   = aws_iam_role.edge_node.id
  policy = data.aws_iam_policy_document.ecr_pull.json
}

resource "aws_iam_role_policy_attachment" "edge_node_ssm" {
  role       = aws_iam_role.edge_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "edge_node" {
  name = "${var.project_name}-edge-node-profile"
  role = aws_iam_role.edge_node.name

  tags = { Component = "edge-node-instance" }
}

# ---------------------------------------------------------------------------
# EC2 instance — same VPC/public subnet as the cloud node
# ---------------------------------------------------------------------------

resource "aws_instance" "edge_node" {
  ami                         = local.ami
  instance_type               = var.edge_instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.edge_node.id]
  iam_instance_profile        = aws_iam_instance_profile.edge_node.name
  associate_public_ip_address = true

  root_block_device {
    volume_size = var.edge_root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  # Infrastructure-only bootstrap: containerd/CNI/EdgeCore are installed in
  # later migration gates via SSM, NOT here (gate-scoped per the plan).
  user_data = base64encode(templatefile("${path.module}/edge_user_data.sh", {
    region = var.aws_region
  }))

  tags = {
    Name      = "${var.project_name}-edge-node"
    Component = "edge-node"
  }
}

# ---------------------------------------------------------------------------
# Elastic IP for the edge node — stable public IP so the cloud SG rules for
# KubeEdge ports 10000/10002 (cidr = this EIP/32) survive stop/start.
# Mirrors aws_eip.cloud on the cloud node.
# ---------------------------------------------------------------------------

resource "aws_eip" "edge" {
  domain = "vpc"

  tags = {
    Name      = "${var.project_name}-edge-eip"
    Component = "edge-node"
  }
}

resource "aws_eip_association" "edge" {
  instance_id   = aws_instance.edge_node.id
  allocation_id = aws_eip.edge.id
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "edge_node_instance_id" {
  description = "Dedicated edge EC2 instance ID"
  value       = aws_instance.edge_node.id
}

output "edge_node_public_ip" {
  description = "Dedicated edge EC2 Elastic IP (internet egress / outbound KubeEdge only)"
  value       = aws_eip.edge.public_ip
}

output "edge_node_private_ip" {
  description = "Dedicated edge EC2 private IP (stable source for future SG tightening)"
  value       = aws_instance.edge_node.private_ip
}

output "edge_node_security_group_id" {
  description = "Security group ID for the dedicated edge node"
  value       = aws_security_group.edge_node.id
}
