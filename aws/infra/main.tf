module "platform" {
  source                   = "./modules/platform"
  name                     = var.name
  region                   = var.region
  kubernetes_version       = var.kubernetes_version
  github_oidc_provider_arn = var.github_oidc_provider_arn
  github_subject           = var.github_subject
  bedrock_model_id         = var.bedrock_model_id
  api_cidrs                = var.api_cidrs
}

variable "name" {

  type = string

  default = "genai-lab"

}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "kubernetes_version" {
  type = string
}
variable "github_oidc_provider_arn" {
  type = string
}
variable "github_subject" {
  type        = string
  description = "Exact GitHub OIDC subject for the aws-dev environment; inspect new immutable subject format."
}
variable "bedrock_model_id" {
  type        = string
  description = "Single-region foundation model ID supporting Converse. Cross-region profiles need expanded IAM policy."
}
variable "api_cidrs" {
  type        = list(string)
  default     = ["0.0.0.0/0"]
  description = "Lab: public authenticated API for rotating hosted runner IPs. Restrict for production."
}
output "cluster_name" { value = module.platform.cluster_name }
output "ecr_repository" { value = module.platform.ecr_repository }
output "ecr_risk_repository" { value = module.platform.ecr_risk_repository }
output "pipeline_role_arn" { value = module.platform.pipeline_role_arn }
output "pod_role_arn" { value = module.platform.pod_role_arn }
