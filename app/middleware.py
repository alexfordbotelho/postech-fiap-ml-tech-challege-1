# logging_middleware.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
from typing import Optional
import httpx, logging, os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

global_db = None

class LoggingMiddleware(BaseHTTPMiddleware):
    _init_lock = asyncio.Lock()   # evita corridas de inicialização

    def __init__(self, app):
        super().__init__(app)

    async def _ensure_db_initialized(self):
        """Inicializa o Mongo com retry/backoff sem 'travar' em caso de falha."""
        global global_db
        if global_db is not None:
            return

        async with LoggingMiddleware._init_lock:
            if global_db is not None:
                return

            MONGODB_URL = os.getenv("MONGODB_URL")
            DATABASE_NAME = os.getenv("DATABASE_NAME")

            print("=" * 80)
            print("🔧 Inicializando MongoDB...")
            print(f"URI: {MONGODB_URL}")
            print(f"DB : {DATABASE_NAME}")

            # tente por ~30s (15 x 2s)
            for attempt in range(1, 16):
                try:
                    client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
                    db = client[DATABASE_NAME]
                    await db.command("ping")
                    global_db = db
                    print(f"✅ MongoDB OK na tentativa {attempt}")
                    print("=" * 80)
                    return
                except Exception as e:
                    print(f"⏳ Mongo indisponível (tentativa {attempt}/15): {e}")
                    await asyncio.sleep(2)

            print("❌ Falhou inicializar o Mongo após múltiplas tentativas")
            print("=" * 80)

    @property
    def db(self):
        global global_db
        return global_db

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Não faça trabalho de DB no /metrics e /healthz (deixe leves e sempre 200)
        if path in ("/metrics", "/healthz", "/ready"):
            return await call_next(request)

        # Garante inicialização com retry (não marca flag até dar certo)
        await self._ensure_db_initialized()

        # Se ainda não conectou, apenas segue sem logar em DB
        if self.db is None:
            logger.warning(f"⚠️ MongoDB ainda não inicializado - não logando {request.method} {path}")
            return await call_next(request)

        # ---- Daqui pra baixo igual ao seu fluxo (encurtei por brevidade) ----
        start_time = datetime.utcnow()
        client_ip = self.get_client_ip(request)
        isp_info = await self.get_isp_info(client_ip)
        response = await call_next(request)
        process_time = (datetime.utcnow() - start_time).total_seconds()
        username = getattr(request.state, "username", None)
        is_authenticated = username is not None

        log_entry = {
            "timestamp": start_time,
            "ip_address": client_ip,
            "mac_address": self.get_mac_address(request),
            "isp": isp_info.get("isp"),
            "country": isp_info.get("country"),
            "region": isp_info.get("region"),
            "city": isp_info.get("city"),
            "user": username if is_authenticated else "anonymous",
            "is_authenticated": is_authenticated,
            "method": request.method,
            "path": path,
            "query_params": str(request.url.query),
            "user_agent": request.headers.get("user-agent"),
            "status_code": response.status_code,
            "process_time": process_time,
        }

        try:
            result = await self.db["request_logs"].insert_one(log_entry)
            logger.info(f"✅ Log salvo [{result.inserted_id}] {request.method} {path} {response.status_code}")
        except Exception as e:
            logger.error(f"❌ ERRO ao salvar log: {e}")

        response.headers["X-Process-Time"] = str(process_time)
        return response

    def get_client_ip(self, request: Request) -> str:
        """
        Extrai o IP real do cliente considerando proxies
        """
        # Verificar headers de proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # IP direto da conexão
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def get_mac_address(self, request: Request) -> str:
        """
        Nota: O endereço MAC não pode ser obtido via HTTP/HTTPS
        Esta função retorna 'N/A' pois o MAC address só é acessível na camada de rede local
        Para obter MAC, seria necessário um agente no cliente ou acesso à rede local
        """
        return "N/A (não acessível via HTTP)"
    
    async def get_isp_info(self, ip: str) -> dict:
        """
        Obtém informações de ISP e geolocalização do IP
        Usa serviço gratuito ip-api.com (limite de 45 req/min)
        """
        # Não fazer lookup para IPs locais
        if ip in ["127.0.0.1", "localhost", "unknown"] or ip.startswith("192.168.") or ip.startswith("10."):
            return {
                "isp": "Local Network",
                "country": "Local",
                "region": "Local",
                "city": "Local"
            }
        
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"http://ip-api.com/json/{ip}")
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "isp": data.get("isp", "Unknown"),
                        "country": data.get("country", "Unknown"),
                        "region": data.get("regionName", "Unknown"),
                        "city": data.get("city", "Unknown"),
                    }
        except Exception as e:
            logger.error(f"Erro ao obter informações de ISP: {e}")
        
        return {
            "isp": "Unknown",
            "country": "Unknown",
            "region": "Unknown",
            "city": "Unknown"
        }


# Middleware simplificado para adicionar username ao request.state
class AuthContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware para extrair usuário do token JWT e adicionar ao request.state
    Isso permite que o LoggingMiddleware acesse o usuário autenticado
    """
    
    async def dispatch(self, request: Request, call_next):
        # Tentar extrair token do header Authorization
        auth_header = request.headers.get("Authorization")
        
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
            try:
                from jose import jwt
                from auth import SECRET_KEY, ALGORITHM
                
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username = payload.get("sub")
                if username:
                    request.state.username = username
            except Exception:
                pass  # Token inválido, usuário permanece None
        
        response = await call_next(request)
        return response
