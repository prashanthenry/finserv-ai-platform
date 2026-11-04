variable "name" {
  type = string
}
variable "location" {
  type = string
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
  type = string
}
variable "api_cidrs" {
  type = list(string)
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.name}"
  location = var.location
  tags     = { Project = var.name, Environment = "lab", ManagedBy = "Terraform" }
}
resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  address_space       = ["10.80.0.0/16"]
}
resource "azurerm_subnet" "aks" {
  name                 = "aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.80.0.0/22"]
}
resource "azurerm_user_assigned_identity" "cluster" {
  name                = "${var.name}-cluster"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
}
resource "azurerm_role_assignment" "network" {
  scope                = azurerm_subnet.aks.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.cluster.principal_id
}
resource "azurerm_container_registry" "app" {
  name                = var.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
}
resource "azurerm_kubernetes_cluster" "main" {
  name                              = var.name
  resource_group_name               = azurerm_resource_group.main.name
  location                          = var.location
  dns_prefix                        = var.name
  sku_tier                          = "Free"
  local_account_disabled            = true
  oidc_issuer_enabled               = true
  workload_identity_enabled         = true
  role_based_access_control_enabled = true
  default_node_pool {
    name           = "system"
    vm_size        = var.node_size
    node_count     = 1
    vnet_subnet_id = azurerm_subnet.aks.id
    upgrade_settings { max_surge = "10%" }
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.cluster.id]
  }
  azure_active_directory_role_based_access_control { azure_rbac_enabled = true }
  api_server_access_profile { authorized_ip_ranges = var.api_cidrs }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    pod_cidr            = "10.244.0.0/16"
    service_cidr        = "10.90.0.0/16"
    dns_service_ip      = "10.90.0.10"
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }
  depends_on = [azurerm_role_assignment.network]
}
resource "azurerm_role_assignment" "pull" {
  scope                            = azurerm_container_registry.app.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}
resource "azurerm_role_assignment" "push" {
  scope                = azurerm_container_registry.app.id
  role_definition_name = "AcrPush"
  principal_id         = var.pipeline_object_id
}
resource "azurerm_role_assignment" "pipeline_credentials" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = var.pipeline_object_id
}
resource "azurerm_role_assignment" "pipeline_deploy" {
  scope                = "${azurerm_kubernetes_cluster.main.id}/namespaces/genai"
  role_definition_name = "Azure Kubernetes Service RBAC Writer"
  principal_id         = var.pipeline_object_id
}
resource "azurerm_role_assignment" "operator_credentials" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = var.operator_object_id
}
resource "azurerm_role_assignment" "operator_admin" {
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = var.operator_object_id
}
resource "azurerm_cognitive_account" "ai" {
  name                  = var.openai_name
  resource_group_name   = azurerm_resource_group.main.name
  location              = var.location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = var.openai_name
  local_auth_enabled    = false
}
resource "azurerm_cognitive_deployment" "chat" {
  name                 = "copilot-chat"
  cognitive_account_id = azurerm_cognitive_account.ai.id
  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }
  sku {
    name     = "GlobalStandard"
    capacity = 1
  }
}
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.name}-copilot"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
}
resource "azurerm_federated_identity_credential" "app" {
  name                = "aks-copilot"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.app.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:genai:copilot"
}
resource "azurerm_role_assignment" "inference" {
  scope                = azurerm_cognitive_account.ai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}
output "resource_group" { value = azurerm_resource_group.main.name }
output "cluster_name" { value = azurerm_kubernetes_cluster.main.name }
output "acr_name" { value = azurerm_container_registry.app.name }
output "acr_login_server" { value = azurerm_container_registry.app.login_server }
output "workload_client_id" { value = azurerm_user_assigned_identity.app.client_id }
output "openai_endpoint" { value = azurerm_cognitive_account.ai.endpoint }
output "openai_deployment" { value = azurerm_cognitive_deployment.chat.name }
