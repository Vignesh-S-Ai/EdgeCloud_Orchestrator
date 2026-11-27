# ---------------------------------------------------------------------------
# ECR Repositories — one per deployable service
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "cloud_node" {
  name                 = "${var.project_name}/cloud-node"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = { Component = "cloud-node" }
}

resource "aws_ecr_repository" "scheduler" {
  name                 = "${var.project_name}/scheduler"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = { Component = "scheduler" }
}

resource "aws_ecr_repository" "orchestrator" {
  name                 = "${var.project_name}/orchestrator"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = { Component = "orchestrator" }
}

resource "aws_ecr_repository" "edge_node" {
  name                 = "${var.project_name}/edge-node"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = { Component = "edge-node" }
}

# ---------------------------------------------------------------------------
# Lifecycle policies — clean up untagged images to control storage costs
# ---------------------------------------------------------------------------

resource "aws_ecr_lifecycle_policy" "untagged_clean" {
  for_each = {
    cloud_node   = aws_ecr_repository.cloud_node.name
    scheduler    = aws_ecr_repository.scheduler.name
    orchestrator = aws_ecr_repository.orchestrator.name
    edge_node    = aws_ecr_repository.edge_node.name
  }

  repository = each.value

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
