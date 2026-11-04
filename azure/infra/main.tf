module "platform" {
  source             = "./modules/platform"
  name               = var.name
  location           = var.location
  acr_name           = var.acr_name
  openai_name        = var.openai_name
  model_name         = var.model_name
  model_version      = var.model_version
  pipeline_object_id = var.pipeline_object_id
  operator_object_id = var.operator_object_id
  node_size          = var.node_size
  api_cidrs          = var.api_cidrs
}
variable "subscription_id" {
  type = string
}
variable "name" {
  type    = string
  default = "genai-lab"
}
variable "location" {
  type    = string
  default = "eastus2"
}
variable "acr_name" {
  type = string
}
variable "openai_name" {
  type = string
}
variable "model_name" {
  type = string
}
variable "model_version" {
  type = string
}
variable "pipeline_object_id" {
  type = string
}
variable "operator_object_id" {
  type = string
}
variable "node_size" {
  type    = string
  default = "Standard_D2s_v3"
}
variable "api_cidrs" {
  type    = list(string)
  default = []
}
output "resource_group" { value = module.platform.resource_group }
output "cluster_name" { value = module.platform.cluster_name }
output "acr_name" { value = module.platform.acr_name }
output "acr_login_server" { value = module.platform.acr_login_server }
output "workload_client_id" { value = module.platform.workload_client_id }
output "openai_endpoint" { value = module.platform.openai_endpoint }
output "openai_deployment" { value = module.platform.openai_deployment }
