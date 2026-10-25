import os
import re
import unicodedata
import sys
import asyncio
import aiohttp
import json
import hashlib
from .database import load_emojis, save_emojis
from .verify import verify_emojis_batch
from .upload import EmojiAuthError, upload_emoji_aLyon
from .delete import delete_emoji_aLyon


class emojis:
    DB_PATH = "database/emojis/emojis.json"
    ASSETS_PATH = "database/emojis/assets"
    ASSET_STATE_PATH = "database/emojis/emojis_assets_state.json"

    def __init__(self, bot_token: str, app_id: str):
        self.bot_token = bot_token
        self.app_id = app_id
        self.emojis_db = load_emojis()
        self.emoji_upload_disabled = False
        self.asset_state = self._load_asset_state()
        self._ensure_emojis_structure()
        # Recarregar após garantir estrutura
        if not self.emojis_db or len(self.emojis_db) == 0:
            self.emojis_db = load_emojis()

    def _load_asset_state(self) -> dict:
        try:
            with open(self.ASSET_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save_asset_state(self) -> None:
        try:
            with open(self.ASSET_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.asset_state, f, indent=4, ensure_ascii=False, sort_keys=True)
        except OSError as exc:
            print(f"[Emojis] Não foi possível salvar o estado dos assets: {exc}")

    def _asset_path(self, name: str) -> str | None:
        gif_path = os.path.join(self.ASSETS_PATH, f"{name}.gif")
        png_path = os.path.join(self.ASSETS_PATH, f"{name}.png")
        if os.path.isfile(gif_path):
            return gif_path
        if os.path.isfile(png_path):
            return png_path
        return None

    def _asset_hash(self, path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _asset_names(self) -> list[str]:
        if not os.path.isdir(self.ASSETS_PATH):
            return []
        names = set()
        for filename in os.listdir(self.ASSETS_PATH):
            if filename.lower().endswith((".png", ".gif")):
                names.add(os.path.splitext(filename)[0])
        return sorted(names)

    def get(self, name: str) -> str | None:
        return self.emojis_db.get(name)

    def list(self) -> dict:
        return self.emojis_db

    def save(self):
        save_emojis(self.emojis_db)

    def _ensure_emojis_structure(self):
        """Garante que emojis.json tenha a estrutura correta escaneando assets"""
        if not self.emojis_db or len(self.emojis_db) == 0:
            print("[Emojis] emojis.json vazio, escaneando pasta de assets...")
            
            if not os.path.exists(self.ASSETS_PATH):
                print(f"[Emojis] Pasta de assets não encontrada: {self.ASSETS_PATH}")
                return
            
            # Escanear todos os arquivos na pasta de assets
            emoji_files = {}
            try:
                for filename in os.listdir(self.ASSETS_PATH):
                    if filename.endswith(('.png', '.gif')):
                        # Remover extensão para obter o nome do emoji
                        emoji_name = os.path.splitext(filename)[0]
                        emoji_files[emoji_name] = ""
                
                if emoji_files:
                    self.emojis_db = emoji_files
                    self.save()
                    print(f"[Emojis] Estrutura criada com {len(self.emojis_db)} emojis encontrados em assets")
                else:
                    print("[Emojis] Nenhum arquivo de emoji encontrado em assets")
            except Exception as e:
                print(f"[Emojis] Erro ao escanear assets: {e}")

    def safe_discord_name(self, name: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(name or ""))
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        safe = re.sub(r"[^A-Za-z0-9_]", "_", ascii_name).strip("_")
        safe = re.sub(r"_+", "_", safe)
        if len(safe) < 2:
            safe = f"emoji_{abs(hash(str(name))) % 100000}"
        return safe[:32]

    def validate_name(self, name: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_]{2,32}", name or ""))

    async def _list_guild_emojis_aLyon(self, session: aiohttp.ClientSession):
        url = f"https://discord.com/api/v10/applications/{self.app_id}/emojis"
        headers = {"Authorization": f"Bot {self.bot_token}"}
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("items", [])
            text = await response.text()
            if response.status in (401, 403):
                raise EmojiAuthError(
                    f"Discord recusou a listagem de Application Emojis ({response.status}) "
                    f"para app {self.app_id}. Detalhe: {(text or '').strip()}"
                )
            print(f"[Emojis] Nao foi possivel listar emojis: {response.status} - {text}")
        return []

    def emoji_name_exists(self, name: str, guild_emojis: list) -> bool:
        return any(e["name"] == name for e in guild_emojis)

    def get_emoji_id(self, name: str, guild_emojis: list) -> str | None:
        for emoji in guild_emojis:
            if emoji["name"] == name:
                return emoji["id"]
        return None

    async def validate_or_create_aLyon(
        self, session: aiohttp.ClientSession, name: str, guild_emojis: list
    ) -> tuple[str | None, bool]:
        tag = self.emojis_db.get(name, "")
        create = False

        if not tag:
            create = True
        else:
            match = re.search(r"<a?:\w+:(\d+)>", tag)
            emoji_id = match.group(1) if match else None
            if emoji_id:
                # Verificação rápida inline
                verify_results = await verify_emojis_batch(
                    self.app_id, self.bot_token, [emoji_id]
                )
                if not verify_results.get(emoji_id, False):
                    await delete_emoji_aLyon(session, self.app_id, self.bot_token, emoji_id)
                    create = True
                    self.emojis_db[name] = ""
            else:
                create = True

        if create:
            if not self.validate_name(name):
                return None, False

            if self.emoji_name_exists(name, guild_emojis):
                emoji_id = self.get_emoji_id(name, guild_emojis)
                if emoji_id:
                    await delete_emoji_aLyon(
                        session, self.app_id, self.bot_token, emoji_id
                    )

            gif_path = os.path.join(self.ASSETS_PATH, f"{name}.gif")
            png_path = os.path.join(self.ASSETS_PATH, f"{name}.png")
            path = gif_path if os.path.isfile(gif_path) else png_path

            if not os.path.isfile(path):
                return None, False

            try:
                new_id = await upload_emoji_aLyon(
                    session, name, path, self.app_id, self.bot_token
                )
                new_tag = (
                    f"<a:{name}:{new_id}>"
                    if path.endswith(".gif")
                    else f"<:{name}:{new_id}>"
                )
                self.emojis_db[name] = new_tag
                return new_tag, True
            except EmojiAuthError:
                raise
            except Exception as e:
                print(f"[Error] Failed to create emoji {name}: {e}")
                return None, False
        return tag, False

    def _set_configured_True(self):
        try:
            path = "database/emojis/emojis_data.json"
            data = {
                "configured": "True",
                "lastToken": self.bot_token
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print("[Emojis] emojis_data.json atualizado com sucesso")
        except Exception as e:
            print(f"[Emojis] Falha ao atualizar emojis_data.json: {e}")

    def _set_upload_disabled(self, reason: str):
        try:
            path = "database/emojis/emojis_data.json"
            data = {
                "configured": "True",
                "lastToken": self.bot_token,
                "uploadDisabled": True,
                "reason": str(reason)[:500],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Emojis] Falha ao salvar estado de upload desativado: {e}")

    def _handle_emoji_auth_error(self, error: EmojiAuthError, total: int, progress_callback=None):
        if not self.emoji_upload_disabled:
            self.emoji_upload_disabled = True
            print("[Emojis] Upload de Application Emojis desativado para este token.")
            print(f"[Emojis] Motivo: {error}")
            print("[Emojis] O bot vai continuar online usando emojis salvos ou fallback.")
        self._set_upload_disabled(str(error))
        if progress_callback:
            progress_callback(0, total)
        return 0, total

    async def Lyon_all_aLyon(self, progress_callback=None):
        total = len(self.emojis_db)

        print(f"[Emojis] Iniciando sincronização de {total} emojis...")

        connector = aiohttp.TCPConnector(limit=50)
        async with aiohttp.ClientSession(connector=connector) as session:
            # ═══════════════════════════════════════════
            # FASE 1: Deletar TODOS os emojis existentes
            # ═══════════════════════════════════════════
            try:
                existing_emojis = await self._list_guild_emojis_aLyon(session)
            except EmojiAuthError as error:
                return self._handle_emoji_auth_error(error, total, progress_callback)
            print(f"[Emojis] {len(existing_emojis)} emojis encontrados no Discord")

            if existing_emojis:
                print(f"[Emojis] Deletando {len(existing_emojis)} emojis existentes...")
                delete_batch_size = 10
                deleted = 0

                for i in range(0, len(existing_emojis), delete_batch_size):
                    batch = existing_emojis[i : i + delete_batch_size]
                    tasks = []
                    for e in batch:
                        task = asyncio.create_task(
                            delete_emoji_aLyon(session, self.app_id, self.bot_token, e["id"])
                        )
                        tasks.append(task)
                        await asyncio.sleep(0.2)
                    await asyncio.gather(*tasks, return_exceptions=True)
                    deleted += len(batch)
                    print(f"[Emojis] Deletados: {deleted}/{len(existing_emojis)}")

                # Aguardar um breve período para a API processar todas as deleções
                await asyncio.sleep(2)
                print(f"[Emojis] ✅ Todos os {len(existing_emojis)} emojis deletados!")

            # ═══════════════════════════════════════════
            # FASE 2: Criar TODOS os novos emojis
            # ═══════════════════════════════════════════
            print(f"[Emojis] Criando {total} emojis novos...")
            names = list(self.emojis_db.keys())
            upload_batch_size = 10
            success = 0

            for i in range(0, len(names), upload_batch_size):
                batch = names[i : i + upload_batch_size]
                tasks = []
                for name in batch:
                    gif_path = os.path.join(self.ASSETS_PATH, f"{name}.gif")
                    png_path = os.path.join(self.ASSETS_PATH, f"{name}.png")
                    path = gif_path if os.path.isfile(gif_path) else png_path

                    if not os.path.isfile(path):
                        print(f"[Emojis] ⚠️ Arquivo não encontrado para '{name}', pulando...")
                        continue

                    task = asyncio.create_task(
                        self._upload_and_save(session, name, path)
                    )
                    tasks.append(task)
                    await asyncio.sleep(0.2)

                results = await asyncio.gather(*tasks, return_exceptions=True)
                auth_error = next(
                    (result for result in results if isinstance(result, EmojiAuthError)),
                    None,
                )
                if auth_error:
                    return self._handle_emoji_auth_error(auth_error, total, progress_callback)
                for result in results:
                    if isinstance(result, Exception):
                        print(f"[Emojis] Erro: {result}")
                    elif result:
                        success += 1

                if progress_callback:
                    progress_callback(success, total)

                print(f"[Emojis] Upload: {success}/{total}")

        # Salvar todas as mudanças de uma vez
        self.save()

        print(f"[Emojis] ✅ Sincronização concluída: {success}/{total} emojis criados")

        if success == total:
            self._set_configured_True()
            print("[Emojis] Todos os emojis foram sincronizados com sucesso!")
            print("[Emojis] Reiniciando bot...")
            return os.execv(sys.executable, ["python"] + sys.argv)

        return success, total

    async def _upload_and_save(self, session, name, path):
        """Upload um emoji e salvar o tag no database"""
        discord_name = self.safe_discord_name(name)
        if not self.validate_name(discord_name):
            print(f"[Emojis] Nome invalido para '{name}', pulando...")
            return False
        new_id = await upload_emoji_aLyon(session, discord_name, path, self.app_id, self.bot_token)
        new_tag = (
            f"<a:{discord_name}:{new_id}>"
            if path.endswith(".gif")
            else f"<:{discord_name}:{new_id}>"
        )
        self.emojis_db[name] = new_tag
        return True

    def Lyon_all(self, progress_callback=None):
        """Versão síncrona para compatibilidade"""
        return asyncio.run(self.Lyon_all_aLyon(progress_callback))

    async def Lyon_add_missing_aLyon(self, progress_callback=None):
        """Sincroniza emojis sem apagar os demais e recria apenas assets alterados."""
        asset_names = self._asset_names()
        for name in asset_names:
            self.emojis_db.setdefault(name, "")
        total = len(asset_names)
        print(f"[Emojis] Verificando {total} assets de emojis (novos e modificados)...")

        connector = aiohttp.TCPConnector(limit=50)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                existing_emojis = await self._list_guild_emojis_aLyon(session)
            except EmojiAuthError as error:
                return self._handle_emoji_auth_error(error, total, progress_callback)

            existing_names = {e['name']: e for e in existing_emojis}
            print(f"[Emojis] {len(existing_emojis)} emojis existentes no Discord (serão preservados)")
            success = 0
            changed = 0
            created = 0

            for start in range(0, len(asset_names), 10):
                tasks = []
                task_meta = []
                for name in asset_names[start:start + 10]:
                    path = self._asset_path(name)
                    if not path:
                        continue
                    current_hash = self._asset_hash(path)
                    existing = existing_names.get(name)
                    previous_hash = self.asset_state.get(name)
                    asset_changed = bool(existing and previous_hash and previous_hash != current_hash)

                    if existing and not asset_changed:
                        tag = f"<a:{name}:{existing['id']}>" if existing.get('animated') else f"<:{name}:{existing['id']}>"
                        self.emojis_db[name] = tag
                        self.asset_state[name] = current_hash
                        success += 1
                        continue

                    if existing and asset_changed:
                        changed += 1
                        task = asyncio.create_task(self._replace_changed_emoji(session, name, path, existing))
                    else:
                        created += 1
                        task = asyncio.create_task(self._upload_and_save(session, name, path))
                    tasks.append(task)
                    task_meta.append((name, current_hash))
                    await asyncio.sleep(0.2)

                results = await asyncio.gather(*tasks, return_exceptions=True)
                auth_error = next((r for r in results if isinstance(r, EmojiAuthError)), None)
                if auth_error:
                    return self._handle_emoji_auth_error(auth_error, total, progress_callback)
                for (name, current_hash), result in zip(task_meta, results):
                    if isinstance(result, Exception):
                        print(f"[Emojis] Erro ao sincronizar '{name}': {result}")
                    elif result:
                        self.asset_state[name] = current_hash
                        success += 1
                if progress_callback:
                    progress_callback(success, total)
                print(f"[Emojis] Progresso: {success}/{total}")

        self.save()
        self._save_asset_state()
        print(f"[Emojis] ✅ Sincronização concluída: {success}/{total}; alterados: {changed}; criados: {created}")
        return success, total

    async def _replace_changed_emoji(self, session, name, path, existing):
        """Remove e recria apenas o emoji cujo arquivo mudou."""
        deleted = await delete_emoji_aLyon(session, self.app_id, self.bot_token, existing['id'])
        if not deleted:
            return False
        return await self._upload_and_save(session, name, path)

    def Lyon_add_missing(self, progress_callback=None):
        return asyncio.run(self.Lyon_add_missing_aLyon(progress_callback))
