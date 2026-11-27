# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

# ---- EC2 Security Group ----
# ZERO public ingress by default (secure dashboard access design, 2026-11 rebuild).
# Inbound:
#   10000 (CloudHub WebSocket) — ONLY from the edge node's Elastic IP
#   10002 (CloudHub HTTPS)     — ONLY from the edge node's Elastic IP
# Explicitly CLOSED (supersedes legacy 80/443/30083 rules):
#   80/443  — no unauthenticated public API
#   30083   — orchestrator reached via SSM Session Manager port forwarding
#             (IAM-authenticated), see docs/SSM_DASHBOARD_ACCESS.md
#   9443    — never in any SG (CloudCore REST internal-only)
# Outbound:
#   All traffic (ECR pull, pip install, model download, SSM, RDS access)

resource "aws_security_group" "ec2" {
  name        = "${var.project_name}-ec2-sg"
  description = "EdgeCloud cloud node - no public ingress; KubeEdge ports edge-EIP only"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.project_name}-ec2-sg" }
}

resource "aws_vpc_security_group_ingress_rule" "ec2_kubeedge_ws" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "${aws_eip.edge.public_ip}/32"
  from_port         = 10000
  to_port           = 10000
  ip_protocol       = "tcp"
  description       = "KubeEdge CloudHub WebSocket - edge node Elastic IP only"
}

resource "aws_vpc_security_group_ingress_rule" "ec2_kubeedge_https" {
  security_group_id = aws_security_group.ec2.id
  cidr_ipv4         = "${aws_eip.edge.public_ip}/32"
  from_port         = 10002
  to_port           = 10002
  ip_protocol       = "tcp"
  description       = "KubeEdge CloudHub HTTPS - edge node Elastic IP only"
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
