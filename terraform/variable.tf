variable "project_id" {
  description = "ID do projeto GCP"
  type        = string
}

variable "region" {
  description = "Região GCP"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zona GCP"
  type        = string
  default     = "us-central1-a"
}

variable "instance_name" {
  description = "Nome da VM"
  type        = string
  default     = "vm-docker-app"
}

variable "machine_type" {
  description = "Tipo da máquina"
  type        = string
  default     = "e2-medium"
}

variable "repo_url" {
  description = "URL do repositório Git (https://... ou git@...)"
  type        = string
}

variable "app_name" {
  description = "Nome da imagem/container Docker"
  type        = string
  default     = "my-app"
}

variable "app_port" {
  description = "Porta exposta pelo seu app dentro do container"
  type        = number
  default     = 8080
}
