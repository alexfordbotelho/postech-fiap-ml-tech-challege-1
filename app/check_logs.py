#!/usr/bin/env python3
"""
Script para verificar os logs no MongoDB
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta
import os

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "webscrapper_books")

async def check_logs():
    """Verificar logs no MongoDB"""
    
    print("🔍 Conectando ao MongoDB...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    
    try:
        # Testar conexão
        await db.command("ping")
        print("✅ Conectado ao MongoDB com sucesso!")
        
        # Listar collections
        collections = await db.list_collection_names()
        print(f"\n📚 Collections disponíveis: {collections}")
        
        if "request_logs" not in collections:
            print("\n⚠️  Collection 'request_logs' não existe ainda!")
            print("   Isso é normal se você ainda não fez nenhuma requisição.")
            return
        
        # Contar total de logs
        total_logs = await db["request_logs"].count_documents({})
        print(f"\n📊 Total de logs: {total_logs}")
        
        if total_logs == 0:
            print("\n⚠️  Nenhum log encontrado!")
            print("   Possíveis causas:")
            print("   1. O middleware não está sendo executado")
            print("   2. O banco de dados não foi inicializado no middleware")
            print("   3. Há erro ao salvar os logs (verifique os logs da aplicação)")
            return
        
        # Buscar logs recentes (últimos 10)
        print(f"\n📝 Últimos 10 logs:")
        print("=" * 80)
        
        cursor = db["request_logs"].find().sort("timestamp", -1).limit(10)
        logs = await cursor.to_list(length=10)
        
        for i, log in enumerate(logs, 1):
            print(f"\n{i}. [{log.get('timestamp')}]")
            print(f"   Usuário: {log.get('user')} {'✓ autenticado' if log.get('is_authenticated') else '✗ não autenticado'}")
            print(f"   Método: {log.get('method')} | Rota: {log.get('path')}")
            print(f"   IP: {log.get('ip_address')} | ISP: {log.get('isp')}")
            print(f"   Status: {log.get('status_code')} | Tempo: {log.get('process_time'):.3f}s")
        
        print("\n" + "=" * 80)
        
        # Estatísticas
        print(f"\n📈 Estatísticas:")
        
        # Logs autenticados vs não autenticados
        authenticated = await db["request_logs"].count_documents({"is_authenticated": True})
        unauthenticated = await db["request_logs"].count_documents({"is_authenticated": False})
        print(f"   ✓ Autenticados: {authenticated}")
        print(f"   ✗ Não autenticados: {unauthenticated}")
        
        # Rotas mais acessadas
        print(f"\n   🔥 Top 5 rotas mais acessadas:")
        pipeline = [
            {"$group": {"_id": "$path", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        top_routes = await db["request_logs"].aggregate(pipeline).to_list(5)
        for i, route in enumerate(top_routes, 1):
            print(f"      {i}. {route['_id']}: {route['count']} requisições")
        
        # Usuários mais ativos (se houver logs autenticados)
        if authenticated > 0:
            print(f"\n   👤 Top 5 usuários mais ativos:")
            pipeline = [
                {"$match": {"is_authenticated": True}},
                {"$group": {"_id": "$user", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            top_users = await db["request_logs"].aggregate(pipeline).to_list(5)
            for i, user in enumerate(top_users, 1):
                print(f"      {i}. {user['_id']}: {user['count']} requisições")
        
        # Logs recentes (últimas 24h)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_logs = await db["request_logs"].count_documents({
            "timestamp": {"$gte": yesterday}
        })
        print(f"\n   ⏰ Logs nas últimas 24h: {recent_logs}")
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        client.close()
        print("\n✅ Conexão fechada")

if __name__ == "__main__":
    print("=" * 80)
    print("         🔍 VERIFICAÇÃO DE LOGS NO MONGODB")
    print("=" * 80)
    asyncio.run(check_logs())