from disnake.ext import tasks
import asyncio
import requests
from functions.database import database as db
from functions.emoji import emoji
from functions.perms import perms
from core.change_bio import change_bio, get_expected_description

def get_expected_bio():
    """Retorna a bio esperada do bot."""
    return get_expected_description()

def get_current_bio(token: str, app_id: str) -> str:
    """Obtém a bio atual do bot via API do Discord."""
    try:
        url = f"https://discord.com/api/v9/applications/{app_id}"
        headers = {
            "authorization": f"Bot {token}",
            "content-type": "application/json",
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("description", "")
        return ""
    except Exception as e:
        print(f"Erro ao obter bio atual: {e}")
        return ""

def correct_bio():
    """Corrige a bio do bot para o valor esperado."""
    try:
        return bool(change_bio())
    except Exception as e:
        print(f"Erro ao corrigir bio: {e}")
        return False

async def send_alert_dm(bot, user_id: int, current_bio: str, expected_bio: str):
    """Envia uma DM de alerta para um usuário."""
    try:
        user = await bot.fetch_user(user_id)
        if user:
            message = (
                f"# ALERTA\n"
                f"A bio do bot foi alterada por um script externo!\n"
                f"**Bio atual:**\n{current_bio}\n\n"
                f"**Bio esperada:**\n{expected_bio}\n\n"
                f"-# O bot será desligado automaticamente para proteção."
            )
            await user.send(message)
    except Exception as e:
        print(f"Erro ao enviar DM para {user_id}: {e}")

EMERGENCY_ALERT_USER_ID = 1463424951393587342

async def shutdown_bot(bot):
    """Desliga o bot de forma segura."""
    try:
        print("⚠️ Desligando o bot devido a alteração não autorizada da bio...")
        await bot.close()
        print("✅ Pro fechado com sucesso. Saída limpa iniciada.")
    except Exception as e:
        print(f"Erro ao desligar bot: {e}")

# Contador de tentativas de correção consecutivas
correction_attempts = 0
max_correction_attempts = 3  # Número máximo de tentativas antes de desligar

# Variável global para armaLyonar a referência do bot
_bot_instance = None

@tasks.loop(minutes=10)
async def bio_monitor_task(bot):
    """Monitora e corrige a bio do bot sem fazer spam na API do Discord."""
    global correction_attempts, _bot_instance
    _bot_instance = bot
    
    try:
        database = db.obter("config.json")
        token = database["bot"]["token"]
        app_id = database["bot"]["id"]
        owner_id = int(database["bot"]["owner"])
        # Usar a nova classe perms para obter a lista de usuários com permissão
        perms_ids = [int(perm_id) for perm_id in perms.get_all_users()]
        
        # Obtém a bio atual e esperada
        expected_bio = get_expected_bio()
        loop = asyncio.get_event_loop()
        current_bio = await loop.run_in_executor(None, get_current_bio, token, app_id)
        
        # Compara as bios (remove espaços em branco extras para comparação)
        if current_bio.strip() != expected_bio.strip():
            print(f"⚠️ ALERTA: Bio foi alterada! Atual: {current_bio[:50]}... Esperada: {expected_bio[:50]}...")
            
            # Tenta corrigir a bio automaticamente
            print(f"Tentando corrigir a bio (tentativa {correction_attempts + 1}/{max_correction_attempts})...")
            success = await loop.run_in_executor(None, correct_bio)
            
            if success:
                correction_attempts = 0  # Reset contador se correção foi bem-sucedida
                print("✅ Bio corrigida com sucesso!")
            else:
                correction_attempts += 1
                print(f"❌ Falha ao corrigir bio. Tentativas: {correction_attempts}/{max_correction_attempts}")
                
                # Se excedeu o número máximo de tentativas, envia alertas e desliga
                if correction_attempts >= max_correction_attempts:
                    print("🚨 Número máximo de tentativas de correção atingido. Enviando alertas...")
                    
                    # Envia alertas para o dono, usuário de emergência e todos os perms
                    all_users = [owner_id, EMERGENCY_ALERT_USER_ID] + perms_ids
                    all_users = list(dict.fromkeys(all_users))  # remove duplicatas mantendo a ordem
                    for user_id in all_users:
                        try:
                            await send_alert_dm(bot, user_id, current_bio, expected_bio)
                            await asyncio.sleep(0.5)  # Pequeno delay entre envios
                        except Exception as e:
                            print(f"Erro ao enviar alerta para {user_id}: {e}")
                    
                    # Desliga o bot após um pequeno delay para garantir que as DMs foram enviadas
                    await asyncio.sleep(2)
                    await shutdown_bot(bot)
        else:
            # Bio está correta, reseta o contador
            if correction_attempts > 0:
                correction_attempts = 0
                print("✅ Bio verificada e está correta!")
            
    except Exception as e:
        print(f"Erro no monitoramento de bio: {e}")

@bio_monitor_task.before_loop
async def before_bio_monitor_task():
    """Aguarda o bot estar pronto antes de iniciar a task."""
    if _bot_instance:
        await _bot_instance.wait_until_ready()

