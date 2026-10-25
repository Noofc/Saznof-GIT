import json
import os
import time
import threading
import copy
from typing import Optional, Any
from connections.mongo_db import collection as bot_collection

class database:
    # Cache em memória para documentos frequentemente acessados
    _cache: dict[str, tuple[Any, float]] = {}
    _cache_lock = threading.Lock()
    _default_ttl = 60  # 60 segundos por padrão
    
    # Documentos que devem ser cacheados por mais tempo (configurações raramente alteradas)
    _long_cache_docs = {
        "custom_mode",
        "custom_panel_mode",
        "custom_colors",
        "canais",
    }
    _long_cache_ttl = 300  # 5 minutos para documentos de configuração

    # Cache em memória para arquivos JSON lidos diretamente do disco
    _file_cache: dict[str, tuple[Any, float]] = {}
    _file_cache_lock = threading.Lock()
    _file_cache_ttl = 60  # 60 segundos para arquivos JSON lidos diretamente

    # Documentos da loja que nao podem ser perdidos em reinicio/redeploy.
    # Se algum fluxo tentar salvar vazio por acidente, preservamos o dado existente.
    _protected_persistent_docs = {
        "loja_products",
        "products",
        "loja_buys",
        "loja_customers",
        "loja_data",
        "loja_preferences",
        "loja_stock_notifications",
        "loja_stock_requests",
        "loja_mass_coupons",
        "loja_roles_temp",
        "stock_config",
        "products_preferences",
        "blacklist",
        "whitelist",
        "protection_advanced_security",
        "protection_privatizacoes_apps",
        "protection_privatizacoes_cargos",
        "protection_privatizacoes_mencoes",
        "protection_privatizacoes_perms",
        "protection_privatizacoes_persistencia",
        "protection_privatizacoes_urls",
        "protection_protecaogeral_banimentos",
        "protection_protecaogeral_canais",
        "protection_protecaogeral_cargos",
        "protection_protecaogeral_comandosext",
        "protection_protecaogeral_expulsoes",
        "protection_protecaogeral_webhooks",
        "antifake_logs",
        "antifake_authorized",
        "protection_config",
        "antifake_config",
        "advanced_security_config",
    }
    @staticmethod
    def _persistent_data_dir() -> str:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        candidates = [
            os.getenv("SYSTEMPRO_DATA_DIR"),
            os.getenv("SYSTEM_DATA_DIR"),
            os.getenv("PERSISTENT_DATA_DIR"),
            os.getenv("DATA_DIR"),
            os.getenv("CAMPOSCLOUD_DATA_DIR"),
            "/data/systempro",
            "/app/data/systempro",
            os.path.join(os.path.dirname(base_dir), "data", "systempro"),
            os.path.join(base_dir, "database"),
        ]
        for candidate in candidates:
            path = str(candidate or "").strip()
            if not path:
                continue
            try:
                os.makedirs(path, exist_ok=True)
                probe = os.path.join(path, ".write-test")
                with open(probe, "w", encoding="utf-8") as file:
                    file.write("ok")
                try:
                    os.remove(probe)
                except Exception:
                    pass
                return path
            except Exception:
                continue
        fallback = os.path.join(base_dir, "database")
        os.makedirs(fallback, exist_ok=True)
        return fallback

    _persistent_backup_file = os.path.join(_persistent_data_dir.__func__(), "persistent_documents_backup.json")

    @staticmethod
    def _payload_from_document(document):
        if not document:
            return None
        try:
            doc_copy = document.copy()
        except Exception:
            try:
                doc_copy = dict(document)
            except Exception:
                return None

        doc_copy.pop("_id", None)
        if len(doc_copy) == 1 and "items" in doc_copy:
            return doc_copy.get("items")
        if len(doc_copy) == 1 and "value" in doc_copy:
            return doc_copy.get("value")
        return doc_copy

    @staticmethod
    def _is_empty_persistent_data(data):
        if data is None:
            return True
        if isinstance(data, (list, tuple, set)):
            return len(data) == 0
        if isinstance(data, dict):
            clean = {k: v for k, v in data.items() if k != "_id"}
            if not clean:
                return True
            if set(clean.keys()) == {"items"}:
                return database._is_empty_persistent_data(clean.get("items"))
            if set(clean.keys()) == {"value"}:
                return database._is_empty_persistent_data(clean.get("value"))
            return False
        return False

    @staticmethod
    def _load_persistent_backup(config_type: str):
        if config_type not in database._protected_persistent_docs:
            return None
        try:
            if not os.path.exists(database._persistent_backup_file):
                return None
            with open(database._persistent_backup_file, "r", encoding="utf-8") as file:
                backups = json.load(file)
            data = backups.get(config_type)
            if database._is_empty_persistent_data(data):
                return None
            return data
        except Exception as e:
            print(f"[Database] Backup persistente indisponivel para '{config_type}': {e}")
            return None

    @staticmethod
    def _save_persistent_backup(config_type: str, data):
        if config_type not in database._protected_persistent_docs:
            return
        if database._is_empty_persistent_data(data):
            return
        try:
            directory = os.path.dirname(database._persistent_backup_file)
            if directory:
                os.makedirs(directory, exist_ok=True)

            backups = {}
            if os.path.exists(database._persistent_backup_file):
                try:
                    with open(database._persistent_backup_file, "r", encoding="utf-8") as file:
                        loaded = json.load(file)
                    backups = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    backups = {}

            backups[config_type] = copy.deepcopy(data)
            temp_file = f"{database._persistent_backup_file}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(backups, file, ensure_ascii=False, indent=4)
            os.replace(temp_file, database._persistent_backup_file)
        except Exception as e:
            print(f"[Database] Nao foi possivel criar backup persistente de '{config_type}': {e}")

    @staticmethod
    def _normalize_custom_mode(data):
        if not isinstance(data, dict):
            data = {}

        result = copy.deepcopy(data)
        style = str(result.get("style") or result.get("bot_style") or "").lower().strip()
        mode = str(result.get("mode") or "").lower().strip()
        aliases = {
            "components": "full_v2",
            "componentes": "full_v2",
            "components_v2": "full_v2",
            "componentes_v2": "full_v2",
            "container": "full_v2",
            "containers": "full_v2",
            "full_components": "full_v2",
            "full_components_v2": "full_v2",
            "full components v2": "full_v2",
            "full comp v2": "full_v2",
            "full_comp_v2": "full_v2",
            "full_v2": "full_v2",
            "embed": "embed",
            "embeds": "embed",
            "embed_v1": "embed",
            "hybrid": "hybrid",
            "hibrido": "hybrid",
            "comp v2 + embed": "hybrid",
            "compv2 + embed": "hybrid",
            "components v2 + embed": "hybrid",
            "embed + comp v2": "hybrid",
            "embed + components v2": "hybrid",
            "comp v2 embed": "hybrid",
            "compv2 embed": "hybrid",
            "comp_v2_embed": "hybrid",
            "compv2_embed": "hybrid",
            "components_embed": "hybrid",
            "embed_components": "hybrid",
            "embed_components_v2": "hybrid",
            "embed_comp_v2": "hybrid",
        }
        style = aliases.get(style)
        if style is None:
            style = "embed" if mode == "embed" else "full_v2"

        result["style"] = style
        result["mode"] = "embed" if style == "embed" else "components"
        return result

    @staticmethod
    def _normalize_custom_panel_mode(data):
        if not isinstance(data, dict):
            data = {}

        result = copy.deepcopy(data)
        panel_mode = str(result.get("mode") or result.get("layout") or "").lower().strip()
        aliases = {
            "button": "buttons",
            "buttons": "buttons",
            "botao": "buttons",
            "botoes": "buttons",
            "botões": "buttons",
            "select": "select",
            "select_menu": "select",
            "menu": "select",
            "both": "both",
            "ambos": "both",
            "complete": "both",
            "completo": "both",
        }
        result["mode"] = aliases.get(panel_mode, "both")
        return result

    @staticmethod
    def _default_document(config_type: str):
        if config_type == "custom_mode":
            return {"mode": "components", "style": "full_v2"}
        if config_type == "custom_panel_mode":
            return {"mode": "both"}
        return {}

    @staticmethod
    def _normalize_document(config_type: str, data):
        if config_type == "custom_mode":
            return database._normalize_custom_mode(data)
        if config_type == "custom_panel_mode":
            return database._normalize_custom_panel_mode(data)
        return data

    @staticmethod
    def _file_document_id(filename: str) -> str:
        """Converte um caminho legado em um `_id` estável dentro do Mongo."""
        normalized = os.path.normpath(str(filename)).replace(os.sep, "/")
        return f"__file__:{normalized}"

    @staticmethod
    def obter(filename: str):
        """Lê um arquivo legado a partir do MongoDB e migra o JSON na primeira leitura."""
        current_time = time.time()
        with database._file_cache_lock:
            cached = database._file_cache.get(filename)
            if cached:
                data, expiry = cached
                if current_time < expiry:
                    return copy.deepcopy(data)
                database._file_cache.pop(filename, None)

        document_id = database._file_document_id(filename)
        try:
            document = bot_collection.find_one({"_id": document_id})
            if document and "value" in document:
                data = copy.deepcopy(document["value"])
                with database._file_cache_lock:
                    database._file_cache[filename] = (copy.deepcopy(data), current_time + database._file_cache_ttl)
                return data
        except Exception as e:
            print(f"[Database] Erro ao ler arquivo legado no Mongo '{filename}': {e}")

        # Migração sob demanda: importa o JSON antigo sem torná-lo a fonte principal.
        try:
            with open(filename, "r", encoding="utf-8") as file:
                data = json.load(file)
            bot_collection.replace_one(
                {"_id": document_id},
                {"_id": document_id, "value": data, "source": "legacy-json"},
                upsert=True,
            )
            with database._file_cache_lock:
                database._file_cache[filename] = (copy.deepcopy(data), current_time + database._file_cache_ttl)
            print(f"[Database] JSON legado migrado para MongoDB: {filename}")
            return data
        except FileNotFoundError:
            print(f"[Database] Arquivo legado não encontrado: {filename}")
            return {}
        except json.JSONDecodeError as e:
            print(f"[Database] JSON inválido em '{filename}': {e}")
            return {}
        except Exception as e:
            print(f"[Database] Erro ao importar '{filename}' para MongoDB: {e}")
            return {}

    @staticmethod
    def salvar(filename: str, data):
        """Salva no MongoDB e mantém um espelho JSON para compatibilidade legada."""
        document_id = database._file_document_id(filename)
        try:
            bot_collection.replace_one(
                {"_id": document_id},
                {"_id": document_id, "value": copy.deepcopy(data), "source": "legacy-json"},
                upsert=True,
            )

            # Espelho opcional: módulos antigos que abrem o arquivo diretamente continuam funcionando.
            directory = os.path.dirname(filename)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=4)

            with database._file_cache_lock:
                database._file_cache[filename] = (copy.deepcopy(data), time.time() + database._file_cache_ttl)
            return True
        except Exception as e:
            print(f"[Database] Erro ao salvar '{filename}' no MongoDB: {type(e).__name__} - {e}")
            return False

    @staticmethod
    def get_document(config_type: str):
        """
        Obtém um documento de configuração específico do bot.
        Usa cache em memória para melhorar performance.
        config_type é usado como _id do documento.
        Retorna um dicionário vazio ou lista vazia se nenhum documento for encontrado.
        
        Se o documento contém apenas a chave 'items' (além de _id), retorna a lista diretamente.
        """
        current_time = time.time()
        
        # Verificar cache primeiro
        with database._cache_lock:
            if config_type in database._cache:
                cached_data, expiry_time = database._cache[config_type]
                if current_time < expiry_time:
                    # Cache válido, retornar cópia profunda para evitar mutação
                    return copy.deepcopy(cached_data)
        
        # Cache não encontrado ou expirado, buscar do MongoDB com timeout
        try:
            # Usar thread com timeout para evitar travamento
            result_holder = [None]
            error_holder = [None]
            
            def fetch_from_mongo():
                try:
                    document = bot_collection.find_one({"_id": config_type})
                    result_holder[0] = document
                except Exception as e:
                    error_holder[0] = e
            
            thread = threading.Thread(target=fetch_from_mongo, daemon=True)
            thread.start()
            thread.join(timeout=3)  # Aguardar 3 segundos
            
            if thread.is_alive():
                # Thread ainda está executando, timeout atingido
                print(f"[Database] TIMEOUT ao buscar documento '{config_type}' do MongoDB")
                return database._default_document(config_type)
            
            if error_holder[0]:
                print(f"[Database] ERRO ao buscar documento '{config_type}': {error_holder[0]}")
                return database._default_document(config_type)
            
            document = result_holder[0]
            if document:
                # Remove o _id para manter compatibilidade
                doc_copy = document.copy()
                doc_copy.pop("_id", None)
                
                # Se o documento tem apenas 'items', retornar a lista diretamente
                if len(doc_copy) == 1 and "items" in doc_copy:
                    result = doc_copy["items"]
                elif len(doc_copy) == 1 and "value" in doc_copy:
                    result = doc_copy["value"]
                else:
                    result = doc_copy
                result = database._normalize_document(config_type, result)
                
                # Armazenar no cache (fazer cópia profunda para evitar mutação)
                cached_result = copy.deepcopy(result)
                ttl = database._long_cache_ttl if config_type in database._long_cache_docs else database._default_ttl
                with database._cache_lock:
                    database._cache[config_type] = (cached_result, current_time + ttl)
                
                # Retornar cópia profunda para evitar mutação
                return copy.deepcopy(result)
            
            # Documento não encontrado. Para dados criticos da loja, tentar restaurar backup local.
            backup_result = database._load_persistent_backup(config_type)
            if backup_result is not None:
                print(f"[Database] Documento persistente '{config_type}' restaurado do backup local.")
                try:
                    database.save_document(config_type, backup_result)
                except Exception as e:
                    print(f"[Database] Nao foi possivel reenviar backup de '{config_type}' ao MongoDB: {e}")
                return copy.deepcopy(backup_result)

            # Documento não encontrado, cachear resultado vazio por menos tempo
            empty_result = database._default_document(config_type)
            with database._cache_lock:
                database._cache[config_type] = (empty_result, current_time + 10)  # 10 segundos para "não encontrado"
            return copy.deepcopy(empty_result)
            
        except Exception as e:
            if config_type in {"custom_mode", "custom_panel_mode"}:
                print(f"[Database] ERRO ao buscar documento '{config_type}': {e}")
                return database._default_document(config_type)
            # Em caso de erro, retornar vazio
            print(f"[Database] ERRO não tratado ao buscar '{config_type}': {e}")
            return {}

    @staticmethod
    def get_documents(query: dict = None):
        """
        Obtém múltiplos documentos de configuração do bot.
        Retorna uma lista de dicionários.
        """
        if query is None:
            query = {}
        documents = list(bot_collection.find(query))
        # Remove o _id de cada documento
        for doc in documents:
            doc.pop("_id", None)
        return documents

    @staticmethod
    def delete_document(config_type: str):
        """
        Deleta um documento de configuração específico do bot.
        """
        bot_collection.delete_one({"_id": config_type})
        # Invalidar cache
        with database._cache_lock:
            database._cache.pop(config_type, None)

    @staticmethod
    def delete_documents(query: dict):
        """
        Deleta múltiplos documentos de configuração do bot.
        """
        # Buscar IDs dos documentos que serão deletados para invalidar cache
        documents_to_delete = list(bot_collection.find(query, {"_id": 1}))
        deleted_ids = [doc["_id"] for doc in documents_to_delete]
        
        bot_collection.delete_many(query)
        
        # Invalidar cache dos documentos deletados
        with database._cache_lock:
            for doc_id in deleted_ids:
                database._cache.pop(doc_id, None)
        
    @staticmethod
    def save_document(config_type: str, query_or_data=None, data=None):
        """
        Salva um documento de configuração do bot (atualiza se existir, insere se não).
        config_type é usado como _id do documento.
        
        Aceita duas assinaturas para retrocompatibilidade:
        - save_document(config_type, data) - Nova assinatura
        - save_document(config_type, {}, data) - Assinatura antiga (query ignorado)
        
        Suporta tanto dicionários quanto listas.
        """
        # Se data é None, então query_or_data é o data (nova assinatura)
        if data is None:
            data = query_or_data
        # Caso contrário, query_or_data é o query (ignorado) e data é o terceiro argumento
        
        # Se data é uma lista, encapsular em um dicionário
        data = database._normalize_document(config_type, data)

        if isinstance(data, list):
            document = {
                "_id": config_type,
                "items": data
            }
            cache_data = data
        elif isinstance(data, dict):
            # Se é um dicionário, copiar e adicionar _id
            data_copy = data.copy()
            data_copy["_id"] = config_type
            document = data_copy
            # Para cache, remover _id novamente
            cache_data = {k: v for k, v in data_copy.items() if k != "_id"}
            # Se o documento tem apenas 'items', retornar a lista diretamente
            if len(cache_data) == 1 and "items" in cache_data:
                cache_data = cache_data["items"]
        else:
            # Suporta valores escalares simples (int, str, bool, etc.)
            document = {
                "_id": config_type,
                "value": data
            }
            cache_data = data
        
        if config_type in database._protected_persistent_docs and database._is_empty_persistent_data(cache_data):
            try:
                existing_doc = bot_collection.find_one({"_id": config_type})
                existing_payload = database._payload_from_document(existing_doc)
                if not database._is_empty_persistent_data(existing_payload):
                    print(f"[Database] Protecao ativa: ignorando tentativa de salvar '{config_type}' vazio para nao perder dados.")
                    current_time = time.time()
                    ttl = database._long_cache_ttl if config_type in database._long_cache_docs else database._default_ttl
                    with database._cache_lock:
                        database._cache[config_type] = (copy.deepcopy(existing_payload), current_time + ttl)
                    database._save_persistent_backup(config_type, existing_payload)
                    return
            except Exception as e:
                print(f"[Database] Falha ao validar protecao de '{config_type}': {e}")

        bot_collection.replace_one(
            {"_id": config_type},
            document,
            upsert=True
        )
        
        # Atualizar cache imediatamente (fazer cópia profunda)
        current_time = time.time()
        ttl = database._long_cache_ttl if config_type in database._long_cache_docs else database._default_ttl
        cached_data = copy.deepcopy(cache_data)
        with database._cache_lock:
            database._cache[config_type] = (cached_data, current_time + ttl)

        database._save_persistent_backup(config_type, cache_data)

    @staticmethod
    def initialize_database_if_needed():
        """
        Verifica se o bot já foi inicializado. Se não, popula a coleção do bot
        com o arquivo consolidado 'database_template.json'.
        Cada chave do JSON vira um documento com _id = nome da chave.
        """
        initialization_doc = bot_collection.find_one({"_id": "_meta_initialization"})

        if initialization_doc:
            # O bot já foi inicializado, não faz nada.
            return

        print("Primeira inicialização detectada. Populando a coleção do bot com valores padrão...")

        template_file = "database_template.json"
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                all_configs = json.load(f)
            
            for config_type, default_data in all_configs.items():
                try:
                    if isinstance(default_data, list):
                        # Se for lista, salva como um documento com a lista dentro
                        database.save_document(config_type, {"items": default_data})
                        print(f" - Config '{config_type}' inicializada com {len(default_data)} itens.")
                    else:
                        # Se for dict, salva diretamente
                        database.save_document(config_type, default_data)
                        print(f" - Config '{config_type}' inicializada com sucesso.")
                
                except Exception as e:
                    print(f"Erro ao inicializar a config '{config_type}': {e}")
            
            # Marca que a inicialização foi concluída para não rodar novamente.
            bot_collection.insert_one({
                "_id": "_meta_initialization",
                "initialized_at": os.path.getmtime(template_file)
            })
            print("Inicialização da coleção do bot concluída.")
        
        except FileNotFoundError:
            print(f"ERRO: Arquivo '{template_file}' não encontrado!")
        except json.JSONDecodeError as e:
            print(f"ERRO: Arquivo '{template_file}' contém JSON inválido: {e}")

    @staticmethod
    def verify_and_create_missing_documents():
        """
        Verifica se todos os documentos do template existem na database.
        Se algum estiver faltando, cria com os valores padrão do template.
        Executa toda vez que o bot inicia.
        """
        template_file = "database_template.json"
        
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                all_configs = json.load(f)
            
            missing_count = 0
            for config_type, default_data in all_configs.items():
                # Verifica se o documento existe
                existing_doc = bot_collection.find_one({"_id": config_type})
                
                if not existing_doc:
                    # Documento não existe, criar com valores padrão
                    try:
                        if isinstance(default_data, list):
                            database.save_document(config_type, {"items": default_data})
                            print(f"[MongoDB] Documento faltante '{config_type}' criado com {len(default_data)} itens.")
                        else:
                            database.save_document(config_type, default_data)
                            print(f"[MongoDB] Documento faltante '{config_type}' criado com sucesso.")
                        missing_count += 1
                    except Exception as e:
                        print(f"[MongoDB] Erro ao criar documento '{config_type}': {e}")
            
            if missing_count > 0:
                print(f"[MongoDB] {missing_count} documento(s) faltante(s) foi(ram) criado(s).")
            else:
                print("[MongoDB] Todos os documentos do template estão presentes na database.")
        
        except FileNotFoundError:
            print(f"[MongoDB] ERRO: Arquivo '{template_file}' não encontrado!")
        except json.JSONDecodeError as e:
            print(f"[MongoDB] ERRO: Arquivo '{template_file}' contém JSON inválido: {e}")
        except Exception as e:
            print(f"[MongoDB] ERRO ao verificar documentos: {e}")
    
    @staticmethod
    def clear_cache(config_type: Optional[str] = None):
        """
        Limpa o cache de documentos.
        
        Args:
            config_type: Se fornecido, limpa apenas o cache deste documento.
                        Se None, limpa todo o cache.
        """
        with database._cache_lock:
            if config_type:
                database._cache.pop(config_type, None)
            else:
                database._cache.clear()
    
    @staticmethod
    def get_cache_stats() -> dict:
        """
        Retorna estatísticas do cache.
        """
        with database._cache_lock:
            current_time = time.time()
            valid_entries = sum(1 for _, (_, expiry) in database._cache.items() if current_time < expiry)
            expired_entries = len(database._cache) - valid_entries
            return {
                "total_entries": len(database._cache),
                "valid_entries": valid_entries,
                "expired_entries": expired_entries,
                "cached_documents": list(database._cache.keys())
            }
