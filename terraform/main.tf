terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# Rede VPC
resource "google_compute_network" "vpc_network" {
  name                    = "${var.app_name}-vpc"
  auto_create_subnetworks = false
}

# Subnet
resource "google_compute_subnetwork" "subnet" {
  name          = "${var.app_name}-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc_network.id
}

# Firewall - permite SSH
resource "google_compute_firewall" "allow_ssh" {
  name    = "${var.app_name}-allow-ssh"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["${var.app_name}-instance"]
}

# Firewall - permite acesso à API (porta 8081)
resource "google_compute_firewall" "allow_api" {
  name    = "${var.app_name}-allow-api"
  network = google_compute_network.vpc_network.name

  allow {
    protocol = "tcp"
    ports    = ["8081","3000","9090","9091","27017"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["${var.app_name}-instance"]
}

# Script de inicialização da VM
locals {
  startup_script = <<-EOF
    #!/bin/bash
    set -e

    # Log de inicialização
    exec > >(tee -a /var/log/startup-script.log)
    exec 2>&1

    echo "=== Iniciando script de setup - $(date) ==="

    # Aguardar o sistema estar pronto
    sleep 10

    # Atualiza o sistema
    echo "=== Atualizando sistema ==="
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get upgrade -y

    # Instala dependências
    echo "=== Instalando Git ==="
    apt-get install -y git curl wget

    # Instala Docker
    echo "=== Instalando Docker ==="
    apt-get install -y ca-certificates gnupg lsb-release

    # Remove instalações antigas do Docker
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    # Adiciona repositório oficial do Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Inicia e habilita o Docker
    echo "=== Iniciando Docker ==="
    systemctl start docker
    systemctl enable docker

    # Verifica se Docker está funcionando
    docker --version
    docker ps

    # Adiciona usuário ubuntu ao grupo docker (para SSH posterior)
    usermod -aG docker ubuntu 2>/dev/null || true

    # Cria diretório para a aplicação
    echo "=== Preparando diretório da aplicação ==="
    mkdir -p /opt/app
    cd /opt/app

    # Clona o repositório (se já existir, só atualiza)
    echo "=== Clonando/atualizando repositório: ${var.git_repository} ==="
    if [ ! -d "/opt/app/.git" ]; then
      git clone ${var.git_repository} /opt/app
    else
      git -C /opt/app pull --ff-only || true
    fi

EOF

}

# Compute Engine Instance
resource "google_compute_instance" "app_instance" {
  name         = "${var.app_name}-instance"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["${var.app_name}-instance"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = google_compute_network.vpc_network.name
    subnetwork = google_compute_subnetwork.subnet.name

    access_config {
      # IP público efêmero
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = local.startup_script

  service_account {
    scopes = ["cloud-platform"]
  }

  allow_stopping_for_update = true
}

# IP estático (opcional, mas recomendado)
resource "google_compute_address" "static_ip" {
  name   = "${var.app_name}-static-ip"
  region = var.region
}

# Associa o IP estático à instância
resource "google_compute_instance" "app_instance_with_static_ip" {
  count        = var.use_static_ip ? 1 : 0
  name         = "${var.app_name}-instance-static"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["${var.app_name}-instance"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = google_compute_network.vpc_network.name
    subnetwork = google_compute_subnetwork.subnet.name

    access_config {
      nat_ip = google_compute_address.static_ip.address
    }
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = local.startup_script

  service_account {
    scopes = ["cloud-platform"]
  }

  allow_stopping_for_update = true
}
