# ---------------------------------------------------------------------------
# Elastic IP — preserves public IP across instance stop/start
# ---------------------------------------------------------------------------

resource "aws_eip" "cloud" {
  domain = "vpc"

  tags = {
    Name      = "${var.project_name}-eip"
    Component = "cloud-node"
  }
}

resource "aws_eip_association" "cloud" {
  instance_id   = aws_instance.cloud.id
  allocation_id = aws_eip.cloud.id
}
