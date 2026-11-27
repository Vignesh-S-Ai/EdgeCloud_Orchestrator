# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project_name}-vpc" }
}

# ---------------------------------------------------------------------------
# Public subnet — EC2 lives here
# ---------------------------------------------------------------------------

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = { Name = "${var.project_name}-public-subnet" }
}

# ---------------------------------------------------------------------------
# RDS subnet — public (tight security group, no NAT cost)
# ---------------------------------------------------------------------------

resource "aws_subnet" "rds" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.rds_subnet_cidr
  availability_zone       = var.availability_zone_2
  map_public_ip_on_launch = false

  tags = { Name = "${var.project_name}-rds-subnet" }
}

# ---------------------------------------------------------------------------
# Internet Gateway
# ---------------------------------------------------------------------------

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${var.project_name}-igw" }
}

# ---------------------------------------------------------------------------
# Public route table (routes to IGW)
# ---------------------------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = { Name = "${var.project_name}-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# RDS subnet uses the same route table (VPC-local routing handles EC2↔RDS)
resource "aws_route_table_association" "rds" {
  subnet_id      = aws_subnet.rds.id
  route_table_id = aws_route_table.public.id
}
