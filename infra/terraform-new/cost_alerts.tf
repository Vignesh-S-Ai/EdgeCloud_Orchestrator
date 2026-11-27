# ---------------------------------------------------------------------------
# Cost safeguards (Gate 2 post-upgrade additions — zero security impact)
# ---------------------------------------------------------------------------
# - $110/month AWS Cost budget with ACTUAL 80% + FORECASTED 100% notifications
# - CloudWatch billing alarm (EstimatedCharges > $110) as hard backstop
# - ONE SNS topic in us-east-1 (billing metrics/alarms only exist there) with
#   an email subscription. AWS sends a CONFIRMATION email; alerts stay silent
#   until the link is clicked (one-time manual step, documented in
#   docs/NEW_AWS_DEPLOYMENT_PROGRESS.md).
# Safeguard cost: $0.00/mo — budget monitoring/notifications are free, the
# 2nd CloudWatch alarm is within the 10-alarm free allowance, SNS email is
# within the 1k-email free tier.

provider "aws" {
  alias   = "us_east_1"
  profile = var.aws_profile
  region  = "us-east-1"

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = "Vignesh"
    }
  }
}

resource "aws_sns_topic" "cost_alerts" {
  provider = aws.us_east_1
  name     = "edgecloud-cost-alerts"
}

# aws_sns_topic_policy REPLACES the default policy, so the owner statement is
# re-declared alongside the AWS Budgets service principal (matches the policy
# documented in the AWS Budgets SNS guide, incl. aws:SourceAccount condition).
resource "aws_sns_topic_policy" "cost_alerts" {
  provider = aws.us_east_1
  arn      = aws_sns_topic.cost_alerts.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "OwnerPublish"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.cost_alerts.arn
      },
      {
        Sid       = "BudgetsPublish"
        Effect    = "Allow"
        Principal = { Service = "budgets.amazonaws.com" }
        Action    = "SNS:Publish"
        Resource  = aws_sns_topic.cost_alerts.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      }
    ]
  })
}

resource "aws_sns_topic_subscription" "cost_alert_email" {
  provider  = aws.us_east_1
  topic_arn = aws_sns_topic.cost_alerts.arn
  protocol  = "email"
  endpoint  = var.cost_alert_email
}

resource "aws_budgets_budget" "monthly" {
  provider = aws.us_east_1

  name         = "edgecloud-monthly-110"
  budget_type  = "COST"
  limit_amount = "110"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    notification_type         = "ACTUAL"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    subscriber_sns_topic_arns = [aws_sns_topic.cost_alerts.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    notification_type         = "FORECASTED"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    subscriber_sns_topic_arns = [aws_sns_topic.cost_alerts.arn]
  }
}

resource "aws_cloudwatch_metric_alarm" "billing" {
  provider = aws.us_east_1

  alarm_name          = "edgecloud-billing-110"
  alarm_description   = "Estimated monthly AWS charges exceed $110 (cost safeguard backstop)"
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  dimensions          = { Currency = "USD" }
  statistic           = "Maximum"
  period              = 21600 # 6h — AWS billing metric cadence
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 110
  alarm_actions       = [aws_sns_topic.cost_alerts.arn]
}
