terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  profile = var.aws_profile
  region  = var.aws_region

  default_tags {
    tags = {
      Project     = "EdgeCloudOrchestrator"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Owner       = "Vignesh"
    }
  }
}
