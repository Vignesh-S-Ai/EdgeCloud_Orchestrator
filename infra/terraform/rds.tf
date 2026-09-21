# ---------------------------------------------------------------------------
# RDS PostgreSQL — db.t3.micro, private (no public endpoint), tight security group
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.rds.id, aws_subnet.public.id]

  tags = { Name = "${var.project_name}-db-subnet-group" }
}

resource "aws_db_instance" "main" {
  identifier = "${var.project_name}-db"

  engine         = var.db_engine
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 0
  storage_type          = "gp2"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false # private — reachable only from EC2 inside VPC
  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = var.db_backup_retention
  multi_az                = false

  tags = {
    Name      = "${var.project_name}-db"
    Component = "rds-postgresql"
  }
}
