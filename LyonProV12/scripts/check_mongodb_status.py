#!/usr/bin/env python
"""
Script para verificar o status da conexão MongoDB e diagnosticar problemas.
"""

import json
import pymongo
import sys
from datetime import datetime
from _path import PROJECT_ROOT

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def check_mongodb():
    """Verifica a conexão com MongoDB"""
    print_header("Verificação de Conexão MongoDB")
    
    try:
        with open(PROJECT_ROOT / "config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        print("✓ config.json carregado com sucesso")
    except Exception as e:
        print(f"✗ Erro ao carregar config.json: {e}")
        return False
    
    try:
        with open(PROJECT_ROOT / "configs" / "config_mongo.json", "r", encoding="utf-8") as f:
            mongo_config = json.load(f)
        print("✓ config_mongo.json carregado com sucesso")
    except Exception as e:
        print(f"✗ Erro ao carregar config_mongo.json: {e}")
        return False
    
    mongo_url = mongo_config.get("mongoURL")
    database_name = mongo_config.get("databaseName", "Lyon_bots")
    bot_id = config.get("botID")
    
    print(f"\nConfigurações encontradas:")
    print(f"  MongoDB URL: {mongo_url}")
    print(f"  Database: {database_name}")
    print(f"  Pro ID: {bot_id}")
    
    # Tentar conectar
    print(f"\nTentando conectar ao MongoDB...")
    try:
        client = pymongo.MongoClient(
            mongo_url,
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=3000,
        )
        
        # Testar a conexão
        client.admin.command('ping')
        print("✓ Conexão com MongoDB bem-sucedida!")
        
        # Verificar banco de dados
        database = client[database_name]
        collection = database[bot_id]
        
        # Tentar buscar um documento de teste
        test_doc = collection.find_one({})
        if test_doc:
            print(f"✓ Banco de dados possui documentos")
            print(f"  Exemplo de documento: {list(test_doc.keys())[:5]}")
        else:
            print(f"⚠ Banco de dados vazio ou sem documentos")
        
        client.close()
        return True
        
    except pymongo.errors.ServerSelectionTimeoutError:
        print(f"✗ ERRO: Não foi possível conectar ao MongoDB em {mongo_url}")
        print(f"  Possíveis causas:")
        print(f"    - MongoDB não está rodando")
        print(f"    - Servidor MongoDB está inacessível")
        print(f"    - Firewall bloqueando a conexão")
        return False
    except pymongo.errors.OperationFailure as e:
        print(f"✗ ERRO: Falha na operação MongoDB: {e}")
        return False
    except Exception as e:
        print(f"✗ ERRO: {type(e).__name__}: {e}")
        return False

def print_solutions():
    """Exibe as soluções para problemas com MongoDB"""
    print_header("Soluções")
    
    print("Se o MongoDB não está conectando:")
    print("\n1. Verifique se o MongoDB está rodando:")
    print("   - Windows: verifique o serviço MongoDB no Services")
    print("   - Linux: sudo systemctl status mongod")
    print("   - macOS: brew services list | grep mongo")
    
    print("\n2. Inicie o MongoDB se não estiver rodando:")
    print("   - Windows: net start MongoDB")
    print("   - Linux: sudo systemctl start mongod")
    print("   - macOS: brew services start mongodb-community")
    
    print("\n3. Verifique a URL de conexão em configs/config_mongo.json:")
    print("   - Padrão local: mongodb://localhost:27017")
    print("   - MongoDB Atlas: mongodb+srv://user:pass@cluster.mongodb.net/")
    
    print("\n4. Se usar MongoDB remoto, atualize a URL:")
    print("   - Edite: configs/config_mongo.json")
    print("   - Atualize: 'mongoURL' com seu endpoint")

def main():
    """Função principal"""
    print(f"\n{'='*60}")
    print(f"  Diagnóstico MongoDB - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    success = check_mongodb()
    
    if not success:
        print_solutions()
    
    print("\n")
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
