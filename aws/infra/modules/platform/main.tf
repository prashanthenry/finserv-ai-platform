variable "name" {
  type = string
}
variable "region" {
  type = string
}
variable "kubernetes_version" {
  type = string
}
variable "github_oidc_provider_arn" {
  type = string
}
variable "github_subject" {
  type = string
}
variable "bedrock_model_id" {
  type = string
}
variable "api_cidrs" {
  type = list(string)
}

data "aws_availability_zones" "available" { state = "available" }
data "aws_partition" "current" {}

resource "aws_vpc" "main" {
  cidr_block           = "10.70.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = var.name }
}
resource "aws_internet_gateway" "main" { vpc_id = aws_vpc.main.id }
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  map_public_ip_on_launch = false
  tags                    = { "kubernetes.io/role/elb" = "1" }
}
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  availability_zone = data.aws_availability_zones.available.names[count.index]
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)
  tags              = { "kubernetes.io/role/internal-elb" = "1" }
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}
resource "aws_eip" "nat" { domain = "vpc" }
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.main]
}
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
}
resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_iam_role" "cluster" {
  name               = "${var.name}-cluster"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_eks_cluster" "main" {
  name                      = var.name
  role_arn                  = aws_iam_role.cluster.arn
  version                   = var.kubernetes_version
  #Fixing for CKV_AWS_37
  enabled_cluster_log_types = [
  "api",
  "audit",
  "authenticator",
  "controllerManager",
  "scheduler",
]
  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }
  vpc_config {
    subnet_ids              = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.api_cidrs
  }
  depends_on = [aws_iam_role_policy_attachment.cluster]
}
resource "aws_iam_role" "node" {
  name               = "${var.name}-node"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "node" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEKS_CNI_Policy", "AmazonEC2ContainerRegistryReadOnly"])
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/${each.key}"
}
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "general"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = aws_subnet.private[*].id
  launch_template {
    id      = aws_launch_template.node.id
    version = aws_launch_template.node.latest_version
  }
  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 3
  }
  depends_on = [aws_iam_role_policy_attachment.node, aws_route_table_association.private]
}
resource "aws_launch_template" "node" {
  name_prefix   = "${var.name}-node-"
  instance_type = "t3.medium"
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
}
resource "aws_eks_addon" "vpc_cni" {
  cluster_name                = aws_eks_cluster.main.name
  addon_name                  = "vpc-cni"
  resolve_conflicts_on_create = "OVERWRITE"
  configuration_values        = jsonencode({ enableNetworkPolicy = "true" })
}
data "tls_certificate" "eks" { url = aws_eks_cluster.main.identity[0].oidc[0].issuer }
resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
}
locals { issuer = replace(aws_eks_cluster.main.identity[0].oidc[0].issuer, "https://", "") }
resource "aws_iam_role" "pod" {
  name = "${var.name}-bedrock"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Principal = { Federated = aws_iam_openid_connect_provider.eks.arn }, Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = { "${local.issuer}:aud" = "sts.amazonaws.com", "${local.issuer}:sub" = "system:serviceaccount:genai:copilot" } }
  }] })
}
resource "aws_iam_role_policy" "bedrock" {
  role = aws_iam_role.pod.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["bedrock:InvokeModel"],
  Resource = "arn:${data.aws_partition.current.partition}:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}" }] })
}
resource "aws_ecr_repository" "app" {
  name                 = "${var.name}-copilot"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "Keep 20 releases", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }, action = { type = "expire" } }] })
}
resource "aws_ecr_repository" "payment_risk" {
  name                 = "${var.name}-payment-risk"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_lifecycle_policy" "payment_risk" {
  repository = aws_ecr_repository.payment_risk.name
  policy     = jsonencode({ rules = [{ rulePriority = 1, description = "Keep 20 risk releases", selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }, action = { type = "expire" } }] })
}
resource "aws_iam_role" "pipeline" {
  name = "${var.name}-github-deploy"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Principal = { Federated = var.github_oidc_provider_arn }, Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = var.github_subject } }
  }] })
}
resource "aws_iam_role_policy" "pipeline" {
  role = aws_iam_role.pipeline.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Resource = [aws_ecr_repository.app.arn, aws_ecr_repository.payment_risk.arn] },
    { Effect = "Allow", Action = ["eks:DescribeCluster"], Resource = aws_eks_cluster.main.arn }
  ] })
}
resource "aws_eks_access_entry" "pipeline" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.pipeline.arn
}
resource "aws_eks_access_policy_association" "pipeline" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_role.pipeline.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"
  access_scope {
    type       = "namespace"
    namespaces = ["genai"]
  }
  depends_on = [aws_eks_access_entry.pipeline]
}
output "cluster_name" { value = aws_eks_cluster.main.name }
output "ecr_repository" { value = aws_ecr_repository.app.repository_url }
output "ecr_risk_repository" { value = aws_ecr_repository.payment_risk.repository_url }
output "pipeline_role_arn" { value = aws_iam_role.pipeline.arn }
output "pod_role_arn" { value = aws_iam_role.pod.arn }
