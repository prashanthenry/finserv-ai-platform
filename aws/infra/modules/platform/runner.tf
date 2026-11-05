variable "enable_github_runner" {
  type    = bool
  default = false
}

variable "github_runner_instance_type" {
  type    = string
  default = "t3.large"
}

data "aws_ssm_parameter" "runner_ubuntu_ami" {
  count = var.enable_github_runner ? 1 : 0
  name  = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_iam_role" "github_runner_host" {
  count = var.enable_github_runner ? 1 : 0
  name  = "${var.name}-github-runner-host"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# The host can communicate with SSM. Deployment AWS permissions come from GitHub OIDC.
resource "aws_iam_role_policy_attachment" "github_runner_ssm" {
  count      = var.enable_github_runner ? 1 : 0
  role       = aws_iam_role.github_runner_host[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "github_runner" {
  count = var.enable_github_runner ? 1 : 0
  name  = "${var.name}-github-runner"
  role  = aws_iam_role.github_runner_host[0].name
}

resource "aws_security_group" "github_runner" {
  count       = var.enable_github_runner ? 1 : 0
  name        = "${var.name}-github-runner"
  description = "Private deployment runner; inbound administration uses SSM."
  vpc_id      = aws_vpc.main.id

  ingress = []

  egress {
    description = "HTTPS for GitHub, registries, AWS APIs and private EKS."
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description = "Ubuntu package mirrors over the existing NAT gateway."
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-github-runner" }
}

resource "aws_vpc_security_group_ingress_rule" "runner_to_eks" {
  count                        = var.enable_github_runner ? 1 : 0
  security_group_id            = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.github_runner[0].id
  description                  = "Kubernetes API from the deployment runner."
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
}

resource "aws_instance" "github_runner" {
  count                       = var.enable_github_runner ? 1 : 0
  ami                         = data.aws_ssm_parameter.runner_ubuntu_ami[0].value
  instance_type               = var.github_runner_instance_type
  subnet_id                   = aws_subnet.private[0].id
  associate_public_ip_address = false
  vpc_security_group_ids      = [aws_security_group.github_runner[0].id]
  iam_instance_profile        = aws_iam_instance_profile.github_runner[0].name
  monitoring                  = true
  ebs_optimized               = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 60
    encrypted             = true
    delete_on_termination = true
  }

  user_data                   = file("${path.module}/runner-user-data.sh")
  user_data_replace_on_change = true

  tags = { Name = "${var.name}-github-runner" }

  depends_on = [
    aws_iam_role_policy_attachment.github_runner_ssm,
    aws_route_table_association.private,
    aws_vpc_security_group_ingress_rule.runner_to_eks,
  ]
}

output "github_runner_instance_id" {
  value = try(aws_instance.github_runner[0].id, null)
}

output "github_runner_private_ip" {
  value = try(aws_instance.github_runner[0].private_ip, null)
}
