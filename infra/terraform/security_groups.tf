# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

# ---- EC2 Security Group ----
# Inbound:
#   80  (HTTP)  — Orchestrator public API
#   443 (HTTPS) — future TLS termination
#   22  (SSH)   — only from caller IP (conditional)
# Outbound:
#   All traffic (ECR pull, pip install, model download, RDS access)

resource "aws_security_group" "ec2" {
  name        = "${var.project_name}-ec2-sg"
  description = "Security group for the Edge-Cloud EC2 cloud node"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-ec2-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "ec2_http" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 80
  to_port           = 80
  ip_protocol       = "tcp"
  description       = "Orchestrator public HTTP API"
}

resource "aws_vpc_security_group_ingress_rule" "ec2_https" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "HTTPS (future TLS)"
}

resource "aws_vpc_security_group_ingress_rule" "ec2_orchestrator_nodeport" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "${var.edge_public_ip}/32"
  from_port         = 30083
  to_port           = 30083
  ip_protocol       = "tcp"
  description       = "K8s NodePort orchestrator - edge node only"
}

resource "aws_vpc_security_group_ingress_rule" "ec2_kubeedge_ws" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "${var.edge_public_ip}/32"
  from_port         = 10000
  to_port           = 10000
  ip_protocol       = "tcp"
  description       = "KubeEdge CloudHub WebSocket - edge node only"
}

resource "aws_vpc_security_group_ingress_rule" "ec2_kubeedge_https" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "${var.edge_public_ip}/32"
  from_port         = 10002
  to_port           = 10002
  ip_protocol       = "tcp"
  description       = "KubeEdge CloudHub HTTPS - edge node only"
}

resource "aws_vpc_security_group_egress_rule" "ec2_all" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "All outbound traffic"
}

# ---- RDS Security Group ----
# Inbound:
#   5432 (PostgreSQL) — ONLY from EC2 security group
# Outbound:
#   None needed (RDS is stateful, responses are allowed)

resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS PostgreSQL - only accepts connections from EC2"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-rds-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_ec2" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.ec2.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL from EC2 cloud node only"
}
