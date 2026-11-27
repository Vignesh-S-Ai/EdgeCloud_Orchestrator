# ---------------------------------------------------------------------------
# Secrets Manager — DB credentials (auto-generated password)
# ---------------------------------------------------------------------------

resource "random_password" "db" {
  length           = var.db_password_length
  special          = true
  override_special = "!#$%&*()-_=+[]{}|:?"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${var.project_name}/db-credentials"
  description = "EdgeCloudOrchestrator PostgreSQL master credentials"
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id = aws_secretsmanager_secret.db_credentials.id

  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db.result
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.db_name
    engine   = "postgres"
  })
}
