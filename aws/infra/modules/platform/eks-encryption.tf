data "aws_caller_identity" "eks_encryption" {}

resource "aws_kms_key" "eks_secrets" {
  description             = "Encryption key for ${var.name} EKS secrets"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "EnableAccountIAMPermissions"
      Effect = "Allow"
      Principal = {
        AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.eks_encryption.account_id}:root"
      }
      Action   = "kms:*"
      Resource = "*"
    }]
  })
}