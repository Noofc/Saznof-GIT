"""
Função centralizada para chamadas à API de IA com fallback para Groq.
"""
import aiohttp
import asyncio
import random
from functions.database import database as db

# Configurações da API GetProject
GETPROJECT_URL = "https://getproject.online/api/unlimited-generate"
GETPROJECT_TOKEN = "Bearer c5db5f0b6b1dad0021b90537e4cbd42fbc50960ecff22c8a"

# Configurações da API Groq (fallback)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEYS = [
    "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",
    "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",
    "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"
]
# Modelos disponíveis da Groq (ordenados por custo - mais baratos primeiro)
# Preços: $0.05/$0.08 (llama-3.1-8b) < $0.075/$0.30 (gpt-oss-20b) < $0.15/$0.60 (gpt-oss-120b) < $0.20/$0.20 (guard) < $0.59/$0.79 (llama-3.3-70b)
GROQ_MODELS = [
    "llama-3.1-8b-instant",              # $0.05/$0.08 - Mais barato e rápido (560 T/s)
    "openai/gpt-oss-20b",                # $0.075/$0.30 - Segundo mais barato (1000 T/s)
    "openai/gpt-oss-120b",               # $0.15/$0.60 - Terceiro mais barato (500 T/s)
    "meta-llama/llama-guard-4-12b",      # $0.20/$0.20 - Quarto mais barato (1200 T/s, mas max 1K completion)
    "llama-3.3-70b-versatile"            # $0.59/$0.79 - Mais caro, mas mais poderoso (280 T/s)
]
GROQ_MODEL = GROQ_MODELS[0]  # Usar o primeiro modelo por padrão (mais barato)

# Contador para alternar entre as chaves da Groq
_groq_key_index = 0

def _get_next_groq_key() -> str:
    """Retorna a próxima chave da Groq de forma rotativa."""
    global _groq_key_index
    key = GROQ_API_KEYS[_groq_key_index]
    _groq_key_index = (_groq_key_index + 1) % len(GROQ_API_KEYS)
    return key

def _get_configured_provider() -> tuple[str, str, str] | None:
    try:
        config = db.get_document("ai_config") or {}
    except Exception as e:
        print(f"[AI] Erro ao ler ai_config: {e}")
        return None

    if config.get("enabled") is False:
        return None

    api_key = str(config.get("api_key") or "").strip()
    model = str(config.get("model") or "").strip()
    if not api_key or api_key.lower() in {"nao configurado", "não configurado", "none", "null"}:
        return None

    if api_key.startswith("gsk_"):
        return (GROQ_URL, api_key, model or GROQ_MODEL)

    return ("https://api.openai.com/v1/chat/completions", api_key, model or "gpt-4o-mini")

async def _call_configured_provider(conteudo: str, module_name: str = "IA") -> str:
    provider = _get_configured_provider()
    if not provider:
        return ""

    url, api_key, model = provider
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": conteudo}],
                "temperature": 0.7,
                "max_tokens": 1500,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            async with session.post(url, json=payload, headers=headers, timeout=35) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"[AI] API configurada falhou ({module_name}): Status {resp.status} - {error_text[:200]}")
                    return ""

                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    content = data.get("text") or data.get("response") or ""
                return str(content).strip()
    except aiohttp.ClientError as e:
        print(f"[AI] Erro de conexao na API configurada ({module_name}): {e}")
        return ""
    except asyncio.TimeoutError:
        print(f"[AI] Timeout na API configurada ({module_name})")
        return ""
    except Exception as e:
        print(f"[AI] Erro inesperado na API configurada ({module_name}): {type(e).__name__}: {e}")
        return ""

async def _call_getproject(conteudo: str, module_name: str = "IA") -> tuple[str, bool]:
    """
    Chama a API GetProject.
    Retorna (resposta, sucesso).
    """
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Content-Type": "application/json",
                "Authorization": GETPROJECT_TOKEN,
            }
            payload = {
                "model": "Project-Model-Free",
                "messages": [{"content": conteudo}],
            }
            async with session.post(
                GETPROJECT_URL,
                json=payload,
                headers=headers,
                timeout=30
            ) as resp:
                # Verificar status code antes de tentar decodificar JSON
                if resp.status != 200:
                    try:
                        error_text = await resp.text()
                        content_type = resp.headers.get('Content-Type', 'unknown')
                        print(f"⚠️ Erro na API GetProject ({module_name}): Status {resp.status}, Content-Type: {content_type}")
                        if len(error_text) < 500:
                            print(f"   Resposta: {error_text[:200]}...")
                    except Exception:
                        pass
                    
                    if resp.status == 403:
                        print(f"   ❌ Acesso negado (403) - usando fallback Groq")
                    elif resp.status == 429:
                        print(f"   ⚠️ Rate limit excedido (429) - usando fallback Groq")
                    elif resp.status >= 500:
                        print(f"   ⚠️ Erro do servidor ({resp.status}) - usando fallback Groq")
                    return ("", False)
                
                # Verificar content-type antes de decodificar JSON
                content_type = resp.headers.get('Content-Type', '').lower()
                if 'application/json' not in content_type:
                    error_text = await resp.text()
                    print(f"⚠️ Resposta não é JSON GetProject ({module_name}): Content-Type: {content_type}")
                    if len(error_text) < 500:
                        print(f"   Resposta recebida: {error_text[:200]}...")
                    return ("", False)
                
                # Tentar decodificar JSON
                try:
                    data = await resp.json()
                    return (data.get("text") or "", True)
                except aiohttp.ContentTypeError as json_error:
                    error_text = await resp.text()
                    print(f"⚠️ Erro ao decodificar JSON GetProject ({module_name}): {json_error}")
                    if len(error_text) < 500:
                        print(f"   Resposta recebida: {error_text[:200]}...")
                    return ("", False)
                    
    except aiohttp.ClientError as e:
        print(f"⚠️ Erro de conexão GetProject ({module_name}): {e}")
        return ("", False)
    except asyncio.TimeoutError:
        print(f"⚠️ Timeout GetProject ({module_name}) - usando fallback Groq")
        return ("", False)
    except Exception as e:
        print(f"⚠️ Erro inesperado GetProject ({module_name}): {type(e).__name__}: {e}")
        return ("", False)

async def _call_groq(conteudo: str, module_name: str = "IA", max_retries: int = 3) -> str:
    """
    Chama a API Groq com retry logic, exponential backoff e fallback de modelos.
    Retorna a resposta ou string vazia em caso de falha.
    """
    # Tentar cada modelo disponível
    for model_index, model in enumerate(GROQ_MODELS):
        for attempt in range(max_retries):
            try:
                # Usar chave rotativa
                api_key = _get_next_groq_key()
                
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    
                    # Ajustar max_tokens baseado no modelo
                    # llama-guard-4-12b tem limite de 1,024 tokens de completion
                    if "llama-guard" in model:
                        max_tokens = 1024
                    else:
                        max_tokens = 2048
                    
                    payload = {
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": conteudo
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": max_tokens,
                    }
                    
                    async with session.post(
                        GROQ_URL,
                        json=payload,
                        headers=headers,
                        timeout=30
                    ) as resp:
                        if resp.status == 200:
                            try:
                                data = await resp.json()
                                # Formato Groq: choices[0].message.content
                                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                                if content:
                                    if model_index > 0:
                                        print(f"✅ Groq ({module_name}): Sucesso com modelo {model} (fallback)")
                                    elif attempt > 0:
                                        print(f"✅ Groq ({module_name}): Sucesso após {attempt + 1} tentativa(s)")
                                    return content.strip()
                            except Exception as e:
                                print(f"⚠️ Erro ao decodificar resposta Groq ({module_name}): {e}")
                        
                        elif resp.status == 400:
                            # Erro 400 pode ser modelo descontinuado ou outros problemas
                            try:
                                error_data = await resp.json()
                                error_msg = error_data.get("error", {}).get("message", "")
                                
                                # Verificar se é erro de modelo descontinuado
                                if "decommissioned" in error_msg.lower() or "no longer supported" in error_msg.lower():
                                    print(f"⚠️ Modelo {model} descontinuado ({module_name}) - tentando próximo modelo...")
                                    break  # Sair do loop de tentativas e tentar próximo modelo
                                else:
                                    print(f"⚠️ Erro Groq ({module_name}): Status {resp.status} - {error_msg}")
                                    if attempt < max_retries - 1:
                                        wait_time = min(2 ** attempt, 5)
                                        await asyncio.sleep(wait_time)
                                        continue
                                    return ""
                            except Exception:
                                error_text = await resp.text()
                                print(f"⚠️ Erro Groq ({module_name}): Status {resp.status} - {error_text[:200]}")
                                if attempt < max_retries - 1:
                                    wait_time = min(2 ** attempt, 5)
                                    await asyncio.sleep(wait_time)
                                    continue
                                return ""
                        
                        elif resp.status == 429:
                            # Rate limit - usar exponential backoff
                            retry_after = int(resp.headers.get('Retry-After', 2 ** attempt))
                            if attempt < max_retries - 1:
                                wait_time = min(retry_after, 60)  # Máximo 60 segundos
                                print(f"⚠️ Groq rate limit ({module_name}) - aguardando {wait_time}s antes de tentar novamente...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                # Se esgotou tentativas para este modelo, tentar próximo
                                if model_index < len(GROQ_MODELS) - 1:
                                    print(f"⚠️ Groq rate limit ({module_name}) - tentando próximo modelo...")
                                    break
                                print(f"❌ Groq rate limit ({module_name}) - esgotadas todas as tentativas")
                                return ""
                        
                        elif resp.status >= 500:
                            # Erro do servidor - usar exponential backoff
                            if attempt < max_retries - 1:
                                wait_time = min(2 ** attempt, 10)  # Máximo 10 segundos
                                print(f"⚠️ Erro do servidor Groq ({module_name}) - aguardando {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                # Se esgotou tentativas para este modelo, tentar próximo
                                if model_index < len(GROQ_MODELS) - 1:
                                    print(f"⚠️ Erro do servidor Groq ({module_name}) - tentando próximo modelo...")
                                    break
                                print(f"❌ Erro do servidor Groq ({module_name}) - esgotadas todas as tentativas")
                                return ""
                        
                        else:
                            # Outros erros HTTP
                            try:
                                error_data = await resp.json()
                                error_msg = error_data.get("error", {}).get("message", "Erro desconhecido")
                                print(f"⚠️ Erro Groq ({module_name}): Status {resp.status} - {error_msg}")
                            except Exception:
                                error_text = await resp.text()
                                print(f"⚠️ Erro Groq ({module_name}): Status {resp.status} - {error_text[:200]}")
                            
                            if resp.status == 401 or resp.status == 403:
                                # Erro de autenticação - não tentar outros modelos
                                return ""
                            
                            if attempt < max_retries - 1:
                                wait_time = min(2 ** attempt, 5)
                                await asyncio.sleep(wait_time)
                                continue
                            
                            # Se esgotou tentativas e não é erro crítico, tentar próximo modelo
                            if model_index < len(GROQ_MODELS) - 1:
                                break
                            return ""
                            
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 5)
                    print(f"⚠️ Erro de conexão Groq ({module_name}) - tentando novamente em {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                # Se esgotou tentativas, tentar próximo modelo
                if model_index < len(GROQ_MODELS) - 1:
                    break
                print(f"⚠️ Erro de conexão Groq ({module_name}): {e}")
                return ""
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 5)
                    print(f"⚠️ Timeout Groq ({module_name}) - tentando novamente em {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                # Se esgotou tentativas, tentar próximo modelo
                if model_index < len(GROQ_MODELS) - 1:
                    break
                print(f"⚠️ Timeout Groq ({module_name}) - esgotadas todas as tentativas")
                return ""
            except Exception as e:
                print(f"⚠️ Erro inesperado Groq ({module_name}): {type(e).__name__}: {e}")
                # Tentar próximo modelo se disponível
                if model_index < len(GROQ_MODELS) - 1:
                    break
                return ""
    
    # Se chegou aqui, todos os modelos falharam
    print(f"❌ Todos os modelos Groq falharam ({module_name})")
    return ""

async def chamar_ia(conteudo: str, module_name: str = "IA") -> str:
    """
    Chama a API de IA com fallback automático para Groq.
    
    Args:
        conteudo: O prompt/conteúdo para enviar à IA
        module_name: Nome do módulo para logs (ex: "Feedbacks", "AIChat", "Tickets")
    
    Returns:
        Resposta da IA ou string vazia em caso de falha
    """
    # Tentar primeiro com a API configurada no painel Sistema IA
    resposta_configurada = await _call_configured_provider(conteudo, module_name)
    if resposta_configurada:
        return resposta_configurada

    # Tentar com GetProject
    resposta, sucesso = await _call_getproject(conteudo, module_name)
    
    if sucesso and resposta:
        return resposta.strip()
    
    # Se GetProject falhou, usar Groq como fallback
    print(f"🔄 Usando fallback Groq ({module_name})...")
    resposta_groq = await _call_groq(conteudo, module_name)
    
    if resposta_groq:
        print(f"✅ Fallback Groq bem-sucedido ({module_name})")
        return resposta_groq
    
    print(f"❌ Todas as APIs falharam ({module_name})")
    return ""

