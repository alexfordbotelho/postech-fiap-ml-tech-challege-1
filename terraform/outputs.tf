output "instance_name" {
  description = "Nome da instância criada"
  value       = var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name
}

output "instance_ip" {
  description = "IP público da instância"
  value       = var.use_static_ip ? google_compute_address.static_ip.address : google_compute_instance.app_instance.network_interface[0].access_config[0].nat_ip
}

output "api_url" {
  description = "URL da API"
  value       = "http://${var.use_static_ip ? google_compute_address.static_ip.address : google_compute_instance.app_instance.network_interface[0].access_config[0].nat_ip}:8081"
}

output "ssh_command" {
  description = "Comando para conectar via SSH"
  value       = "gcloud compute ssh ${var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name} --zone=${var.zone}"
}

output "vpc_network_name" {
  description = "Nome da rede VPC criada"
  value       = google_compute_network.vpc_network.name
}

output "view_startup_logs" {
  description = "Comando para ver logs de inicialização"
  value       = "gcloud compute instances get-serial-port-output ${var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name} --zone=${var.zone}"
}

output "check_docker_status" {
  description = "Comando para verificar status do Docker na VM"
  value       = "gcloud compute ssh ${var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name} --zone=${var.zone} --command='docker ps && docker logs ${var.app_name}'"
}

output "setup_instructions" {
  description = "Instruções pós-deploy"
  value       = <<-EOT
    ╔════════════════════════════════════════════════════════════════╗
    ║  SETUP CONCLUÍDO - Aguarde 3-5 minutos para instalação        ║
    ╚════════════════════════════════════════════════════════════════╝
    
    1️⃣  Ver logs de instalação:
       gcloud compute instances get-serial-port-output ${var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name} --zone=${var.zone}
    
    2️⃣  Verificar status do Docker:
       gcloud compute ssh ${var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name} --zone=${var.zone} --command='sudo docker ps'
    
    3️⃣  Ver logs da aplicação:
       gcloud compute ssh ${var.use_static_ip ? google_compute_instance.app_instance_with_static_ip[0].name : google_compute_instance.app_instance.name} --zone=${var.zone} --command='sudo docker logs ${var.app_name}'
    
    4️⃣  Testar a API:
       curl http://${var.use_static_ip ? google_compute_address.static_ip.address : google_compute_instance.app_instance.network_interface[0].access_config[0].nat_ip}:8081
    
    ⏱️  Nota: O script de startup leva ~3-5 minutos para completar.
        Você pode monitorar o progresso com o comando #1 acima.
  EOT
}
