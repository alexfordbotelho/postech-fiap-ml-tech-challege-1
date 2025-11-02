#!/usr/bin/env python3
"""
Script de teste para validar a API com autenticação JWT e logging
"""
import requests
import json
import time
from typing import Optional

BASE_URL = "http://localhost:8081"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg: str):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_error(msg: str):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")

class APITester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.username = f"teste_user_{int(time.time())}"
        
    def test_register(self):
        """Testar registro de usuário"""
        print_info("Testando registro de usuário...")
        
        data = {
            "username": self.username,
            "email": f"{self.username}@test.com",
            "password": "senha123",
            "full_name": "Usuário de Teste"
        }
        
        response = requests.post(
            f"{self.base_url}/api/v1/auth/register",
            json=data
        )
        
        if response.status_code == 201:
            result = response.json()
            self.token = result.get("access_token")
            print_success(f"Usuário registrado: {self.username}")
            print_success(f"Token recebido: {self.token[:20]}...")
            return True
        else:
            print_error(f"Falha no registro: {response.status_code}")
            print_error(response.text)
            return False
    
    def test_login(self):
        """Testar login"""
        print_info("Testando login...")
        
        data = {
            "username": self.username,
            "password": "senha123"
        }
        
        response = requests.post(
            f"{self.base_url}/api/v1/auth/login",
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            self.token = result.get("access_token")
            print_success("Login realizado com sucesso")
            return True
        else:
            print_error(f"Falha no login: {response.status_code}")
            return False
    
    def test_protected_route_without_auth(self):
        """Testar acesso a rota protegida sem autenticação"""
        print_info("Testando acesso sem autenticação (deve falhar)...")
        
        response = requests.get(f"{self.base_url}/api/v1/books")
        
        if response.status_code == 401:
            print_success("Rota protegida corretamente (401 sem token)")
            return True
        else:
            print_error(f"Esperado 401, recebido: {response.status_code}")
            return False
    
    def test_protected_route_with_auth(self):
        """Testar acesso a rota protegida com autenticação"""
        print_info("Testando acesso com autenticação...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            f"{self.base_url}/api/v1/books?page=1&limit=5",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Livros obtidos: {result.get('total', 0)} total")
            print_success(f"Página retornada: {len(result.get('items', []))} items")
            return True
        else:
            print_error(f"Falha ao obter livros: {response.status_code}")
            return False
    
    def test_health_check(self):
        """Testar health check"""
        print_info("Testando health check...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            f"{self.base_url}/api/v1/health",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Status: {result.get('status')}")
            print_success(f"Database: {result.get('database')}")
            print_success(f"Books count: {result.get('books_count')}")
            return True
        else:
            print_error(f"Falha no health check: {response.status_code}")
            return False
    
    def test_categories(self):
        """Testar listagem de categorias"""
        print_info("Testando categorias...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            f"{self.base_url}/api/v1/categories",
            headers=headers
        )
        
        if response.status_code == 200:
            categories = response.json()
            print_success(f"Categorias encontradas: {len(categories)}")
            print_info(f"Primeiras 5: {', '.join(categories[:5])}")
            return True
        else:
            print_error(f"Falha ao obter categorias: {response.status_code}")
            return False
    
    def test_stats(self):
        """Testar estatísticas"""
        print_info("Testando estatísticas...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            f"{self.base_url}/api/v1/stats/overview",
            headers=headers
        )
        
        if response.status_code == 200:
            stats = response.json()
            print_success(f"Total de livros: {stats.get('total_books')}")
            print_success(f"Preço médio: £{stats.get('average_price')}")
            print_success(f"Total de categorias: {stats.get('total_categories')}")
            return True
        else:
            print_error(f"Falha ao obter estatísticas: {response.status_code}")
            return False
    
    def test_logs(self):
        """Testar consulta de logs"""
        print_info("Testando consulta de logs...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(
            f"{self.base_url}/api/v1/logs?page=1&limit=10",
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            print_success(f"Logs encontrados: {result.get('total')}")
            
            # Mostrar último log
            if result.get('items'):
                last_log = result['items'][0]
                print_info(f"Último log: {last_log.get('method')} {last_log.get('path')}")
                print_info(f"Usuário: {last_log.get('user')}")
                print_info(f"IP: {last_log.get('ip_address')}")
                print_info(f"ISP: {last_log.get('isp')}")
            
            return True
        else:
            print_error(f"Falha ao obter logs: {response.status_code}")
            return False
    
    def run_all_tests(self):
        """Executar todos os testes"""
        print("\n" + "="*60)
        print("🚀 INICIANDO TESTES DA API")
        print("="*60 + "\n")
        
        tests = [
            ("Registro de Usuário", self.test_register),
            ("Acesso sem Autenticação", self.test_protected_route_without_auth),
            ("Login", self.test_login),
            ("Acesso com Autenticação", self.test_protected_route_with_auth),
            ("Health Check", self.test_health_check),
            ("Listagem de Categorias", self.test_categories),
            ("Estatísticas", self.test_stats),
            ("Consulta de Logs", self.test_logs),
        ]
        
        passed = 0
        failed = 0
        
        for name, test_func in tests:
            print(f"\n{'─'*60}")
            print(f"📋 Teste: {name}")
            print(f"{'─'*60}")
            
            try:
                if test_func():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print_error(f"Erro no teste: {str(e)}")
                failed += 1
            
            time.sleep(0.5)
        
        print("\n" + "="*60)
        print("📊 RESUMO DOS TESTES")
        print("="*60)
        print(f"{Colors.GREEN}✓ Passou: {passed}{Colors.END}")
        print(f"{Colors.RED}✗ Falhou: {failed}{Colors.END}")
        print(f"Total: {passed + failed}")
        print("="*60 + "\n")
        
        if failed == 0:
            print_success("🎉 Todos os testes passaram!")
        else:
            print_warning(f"⚠️  {failed} teste(s) falharam")

def main():
    print_info("Verificando se a API está online...")
    
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        if response.status_code == 200:
            print_success("API está online!")
        else:
            print_warning("API retornou status diferente de 200")
    except requests.exceptions.RequestException:
        print_error("API não está acessível!")
        print_info(f"Certifique-se de que a API está rodando em {BASE_URL}")
        return
    
    tester = APITester(BASE_URL)
    tester.run_all_tests()

if __name__ == "__main__":
    main()