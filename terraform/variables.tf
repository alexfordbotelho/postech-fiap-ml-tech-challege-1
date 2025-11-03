variable "project_id" {
  description = "ID do projeto no Google Cloud"
  type        = string
}

variable "region" {
  description = "Região do GCP"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zona do GCP"
  type        = string
  default     = "us-central1-a"
}

variable "app_name" {
  description = "Nome da aplicação"
  type        = string
  default     = "my-api"
}

variable "machine_type" {
  description = "Tipo de máquina da VM"
  type        = string
  default     = "e2-small"
  # Opções: e2-micro, e2-small, e2-medium, n1-standard-1, etc.
}

variable "git_repository" {
  description = "URL do repositório Git público"
  type        = string
}

variable "use_static_ip" {
  description = "Usar IP estático para a instância"
  type        = bool
  default     = false
}
