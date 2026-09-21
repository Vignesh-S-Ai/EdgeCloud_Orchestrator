# ---------------------------------------------------------------------------
# IAM Role + Instance Profile for the EC2 cloud node
# Least-privilege: ECR pull, Secrets Manager read, CloudWatch logs
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${var.project_name}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json

  tags = { Component = "ec2-instance" }
}

# --- ECR pull permissions ---

data "aws_iam_policy_document" "ecr_pull" {
  statement {
    sid    = "ECRPull"
    effect = "Allow"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:DescribeRepositories",
      "ecr:ListImages",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ecr_pull" {
  name   = "${var.project_name}-ecr-pull"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ecr_pull.json
}

# --- Secrets Manager read ---

data "aws_iam_policy_document" "secrets_read" {
  statement {
    sid    = "SecretsRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:*:secret:${var.project_name}/*",
    ]
  }
}

resource "aws_iam_role_policy" "secrets_read" {
  name   = "${var.project_name}-secrets-read"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

# --- CloudWatch Logs ---

data "aws_iam_policy_document" "cloudwatch" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:*:log-group:/${var.project_name}/*",
      "arn:aws:logs:${var.aws_region}:*:log-group:/${var.project_name}/*:*",
    ]
  }

  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "cloudwatch" {
  name   = "${var.project_name}-cloudwatch"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.cloudwatch.json
}

# --- SSM access (Session Manager, no SSH needed) ---

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# --- EC2 instance profile ---

resource "aws_iam_instance_profile" "ec2" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2.name

  tags = { Component = "ec2-instance" }
}
