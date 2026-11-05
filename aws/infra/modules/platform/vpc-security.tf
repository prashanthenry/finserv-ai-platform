locals {
  flow_log_group_name = "/aws/vpc/${var.name}/flow"
  flow_log_group_arn  = "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.eks_encryption.account_id}:log-group:${local.flow_log_group_name}"
}

resource "aws_default_security_group" "locked" {
  vpc_id = aws_vpc.main.id

  ingress = []
  egress  = []

  tags = { Name = "${var.name}-default-deny" }
}

resource "aws_kms_key" "vpc_flow_logs" {
  description             = "Encryption key for ${var.name} VPC flow logs"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableAccountIAMPermissions"
        Effect    = "Allow"
        Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.eks_encryption.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowCloudWatchForThisLogGroup"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.region}.${data.aws_partition.current.dns_suffix}" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource  = "*"
        Condition = {
          ArnEquals = { "kms:EncryptionContext:aws:logs:arn" = local.flow_log_group_arn }
        }
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  name              = local.flow_log_group_name
  retention_in_days = 365
  kms_key_id        = aws_kms_key.vpc_flow_logs.arn
}

resource "aws_iam_role" "vpc_flow_logs" {
  name = "${var.name}-vpc-flow-logs"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.eks_encryption.account_id }
        ArnLike = {
          "aws:SourceArn" = "arn:${data.aws_partition.current.partition}:ec2:${var.region}:${data.aws_caller_identity.eks_encryption.account_id}:vpc-flow-log/*"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "vpc_flow_logs" {
  name = "publish-vpc-flow-logs"
  role = aws_iam_role.vpc_flow_logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = [local.flow_log_group_arn, "${local.flow_log_group_arn}:*"]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:DescribeLogGroups"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"]
        Resource = aws_kms_key.vpc_flow_logs.arn
        Condition = {
          StringEquals = { "kms:ViaService" = "logs.${var.region}.${data.aws_partition.current.dns_suffix}" }
          ArnEquals    = { "kms:EncryptionContext:aws:logs:arn" = local.flow_log_group_arn }
        }
      }
    ]
  })
}

resource "aws_flow_log" "main" {
  vpc_id                   = aws_vpc.main.id
  traffic_type             = "ALL"
  log_destination_type     = "cloud-watch-logs"
  log_destination          = aws_cloudwatch_log_group.vpc_flow_logs.arn
  iam_role_arn             = aws_iam_role.vpc_flow_logs.arn
  max_aggregation_interval = 60

  depends_on = [aws_iam_role_policy.vpc_flow_logs]
}
