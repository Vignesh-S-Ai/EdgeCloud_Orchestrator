# ---------------------------------------------------------------------------
# CloudWatch — log group for EC2 application services
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "edgecloud" {
  name              = "/${var.project_name}/ec2-services"
  retention_in_days = 14

  tags = { Component = "cloudwatch" }
}

# --- Basic CPU alarm (warn if > 85% for 5 min) ---

resource "aws_cloudwatch_metric_alarm" "ec2_cpu_high" {
  alarm_name          = "${var.project_name}-ec2-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "EC2 CPU utilization > 85% for 10 minutes"
  alarm_actions       = []

  dimensions = {
    InstanceId = aws_instance.cloud.id
  }

  tags = { Component = "cloudwatch-alarm" }
}
