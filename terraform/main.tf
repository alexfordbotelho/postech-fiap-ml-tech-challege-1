terraform {
  required_version = ">= 1.6.0"
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

# (Opcional) firewall para HTTP/HTTPS e porta do app
resource "google_compute_firewall" "allow_web" {
  name    = "allow-web"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["80", "443", var.app_port]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["docker-app"]
}

resource "google_compute_instance" "vm" {
  name         = var.instance_name
  machine_type = var.machine_type
  tags         = ["docker-app"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
    }
  }

  network_interface {
    network = "default"
    access_config {} # IP público
  }

  # Script que roda no boot
  metadata_startup_script = <<-EOT
    #!/usr/bin/env bash
    set -euxo pipefail

    # Variáveis
    REPO_URL="${var.repo_url}"
    APP_DIR="/opt/app"
    APP_NAME="${var.app_name}"
    APP_PORT="${var.app_port}"

    # Atualiza pacotes
    apt-get update -y

    # Instala dependências
    apt-get install -y git ca-certificates curl gnupg

    # Instala Docker (debian)
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    systemctl enable docker
    systemctl start docker

    # Puxa ou atualiza o repo
    mkdir -p "${APP_DIR}"
    if [ ! -d "${APP_DIR}/.git" ]; then
      git clone "${REPO_URL}" "${APP_DIR}"
    else
      cd "${APP_DIR}"
      git pull --ff-only
    fi

    cd "${APP_DIR}"

    # Build da imagem
    docker build -t "${APP_NAME}:latest" .

    # Sobe o container (idempotente)
    if docker ps -a --format '{{.Names}}' | grep -q "^${APP_NAME}$"; then
      docker rm -f "${APP_NAME}" || true
    fi

    docker run -d --restart unless-stopped \
      --name "${APP_NAME}" \
      -p ${APP_PORT}:${APP_PORT} \
      "${APP_NAME}:latest"

    # (Opcional) redirecionar porta 80 -> APP_PORT com iptables se seu app não expõe 80
    # iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports ${APP_PORT}
  EOT
}

