import os
import base64
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor


class EmojiAuthError(Exception):
    """Raised when Discord refuses Application Emoji access for this token/app."""


def _discord_error_message(action: str, status: int, text: str, app_id: str) -> str:
    clean_text = (text or "").strip()
    return (
        f"Discord recusou {action} de Application Emojis ({status}) para app {app_id}. "
        "Confira se o token pertence a esta aplicacao e se Application Emojis esta liberado. "
        f"Detalhe: {clean_text}"
    )


async def find_existing_application_emoji(session, app_id, bot_token, name):
    url = f"https://discord.com/api/v10/applications/{app_id}/emojis"
    headers = {"Authorization": f"Bot {bot_token}"}

    async with session.get(url, headers=headers) as response:
        if response.status in (401, 403):
            text = await response.text()
            raise EmojiAuthError(
                _discord_error_message("a listagem", response.status, text, app_id)
            )
        if response.status != 200:
            return None

        data = await response.json()
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return None

        for item in items:
            if item.get("name") == name:
                return item.get("id")

    return None

async def upload_emoji_aLyon(session, name, image_path, app_id, bot_token):
    ext = os.path.splitext(image_path)[1].lower()
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()

    tipo = "gif" if ext == ".gif" else "png"
    base64_image = f"data:image/{tipo};base64,{base64.b64encode(image_data).decode()}"

    url = f"https://discord.com/api/v10/applications/{app_id}/emojis"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "name": name,
        "image": base64_image
    }

    async with session.post(url, headers=headers, json=payload) as response:
        if response.status == 201:
            data = await response.json()
            emoji_id = data["id"]
            print(f"[EmojiUpload] Emoji '{name}' adicionado com sucesso! ID: {emoji_id}")
            return emoji_id
        else:
            text = await response.text()
            if response.status in (401, 403):
                raise EmojiAuthError(
                    _discord_error_message(f"o upload do emoji '{name}'", response.status, text, app_id)
                )
            if response.status == 400 and "APPLICATION_EMOJI_NAME_ALREADY_TAKEN" in text:
                emoji_id = await find_existing_application_emoji(session, app_id, bot_token, name)
                if emoji_id:
                    print(f"[EmojiUpload] Emoji '{name}' ja existe. Reutilizando ID: {emoji_id}")
                    return emoji_id

            print(f"[EmojiUpload] Erro ao criar emoji '{name}': {response.status} - {text}")
            raise Exception(f"Erro ao criar emoji {name}: {response.status} - {text}")

def upload_emoji(name, image_path, app_id, bot_token):
    """Versão síncrona para compatibilidade"""
    return asyncio.run(upload_emoji_aLyon_wrapper(name, image_path, app_id, bot_token))

async def upload_emoji_aLyon_wrapper(name, image_path, app_id, bot_token):
    async with aiohttp.ClientSession() as session:
        return await upload_emoji_aLyon(session, name, image_path, app_id, bot_token)

async def upload_emojis_batch(emojis_data, app_id, bot_token, max_concurrent=5):
    """
    Upload múltiplos emojis em paralelo
    emojis_data: lista de tuplas (name, image_path)
    max_concurrent: número máximo de uploads simultâneos
    """
    connector = aiohttp.TCPConnector(limit=max_concurrent)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for name, image_path in emojis_data:
            task = asyncio.create_task(upload_emoji_aLyon(session, name, image_path, app_id, bot_token))
            tasks.append(task)
            await asyncio.sleep(0.2)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
