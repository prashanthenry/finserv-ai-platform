variable "enable_github_runner" {
  type        = bool
  default     = false
  description = "Create the private EC2 deployment runner. Register it with GitHub after apply."
}

variable "github_runner_instance_type" {
  type        = string
  default     = "t3.large"
  description = "x86_64 instance for building the TensorFlow/PyTorch image."
}

output "github_runner_instance_id" {
  value = module.platform.github_runner_instance_id
}

output "github_runner_private_ip" {
  value = module.platform.github_runner_private_ip
}

output "deployment_region" {
  value = var.region
}
