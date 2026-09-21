# ---------------------------------------------------------------------------
# Global variables
# ---------------------------------------------------------------------------

variable "aws_profile" {
  description = "AWS CLI profile for authentication"
  type        = string
  default     = "edgecloud"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Short project name used in resource naming"
  type        = string
  default     = "edgecloud"
}

variable "environment" {
  description = "Environment label (dev, staging, prod)"
  type        = string
  default     = "development"
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for the project VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet (EC2)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "rds_subnet_cidr" {
  description = "CIDR block for the RDS subnet (public, tight SG)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "availability_zone" {
  description = "Primary AZ for EC2 and subnets"
  type        = string
  default     = "ap-south-1a"
}

variable "availability_zone_2" {
  description = "Secondary AZ for RDS subnet"
  type        = string
  default     = "ap-south-1b"
}

# ---------------------------------------------------------------------------
# EC2
# ---------------------------------------------------------------------------

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ami_id" {
  description = "AMI ID (Amazon Linux 2023 in ap-south-1). Leave empty to auto-resolve."
  type        = string
  default     = ""
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 30
}

variable "edge_public_ip" {
  description = "Public IP of the edge node (WSL2/Windows host) for KubeEdge SG rules"
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# RDS
# ---------------------------------------------------------------------------

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_engine" {
  description = "RDS engine"
  type        = string
  default     = "postgres"
}

variable "db_engine_version" {
  description = "RDS engine version"
  type        = string
  default     = "15.18"
}

variable "db_name" {
  description = "Initial database name"
  type        = string
  default     = "edgecloud"
}

variable "db_username" {
  description = "Master database username"
  type        = string
  default     = "edgecloud_admin"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_backup_retention" {
  description = "Backup retention in days"
  type        = number
  default     = 7
}

# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

variable "db_password_length" {
  description = "Length of auto-generated DB password"
  type        = number
  default     = 32
}
