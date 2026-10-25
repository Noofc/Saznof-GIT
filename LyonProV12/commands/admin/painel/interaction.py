import disnake
from disnake.ext import commands
import asyncio
import inspect
import time
import traceback

from functions.emoji import emoji
from functions.database import database as db
from functions.display_mode import get_bot_mode, get_bot_style, get_panel_layout
from functions.perms import perms
from functions.email_utils import owner_email_is_verified
from functions.message import message, embed_message
from functions.user_permissions import user_permissions
from functions.utils import utils
from functions.logger import logger

from .components import PainelComponents, PainelEmbed, PainelGroupComponents, PANEL_GROUP_IDS, get_panel_button_states
from .image import load_panel_image_file


PANEL_REFRESH_INTERVAL_SECONDS = 30
PANEL_REFRESH_TTL_SECONDS = 13 * 60


class PainelCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._panel_sessions = {}
        self._panel_color_cache = (0.0, None)
        self._panel_refresh_task = self.bot.loop.create_task(self._panel_refresh_loop())

    def cog_unload(self):
        if self._panel_refresh_task:
            self._panel_refresh_task.cancel()

    def _is_v2_components(self, components) -> bool:
        return bool(components and isinstance(components[0], disnake.ui.Container))

    def _merge_v2_components(self, components):
        """Garante que um payload híbrido não envie navegação fora do Container principal."""
        if not self._is_v2_components(components) or len(components) <= 1:
            return components
        primary = components[0]
        children = list(getattr(primary, "children", []) or [])
        extras = [item for item in components[1:] if item is not None]
        if not extras:
            return components
        kwargs = {}
        accent = getattr(primary, "accent_colour", None)
        if accent is not None:
            kwargs["accent_colour"] = accent
        return [disnake.ui.Container(*children, *extras, **kwargs)]

    def _is_invalid_emoji_error(self, error: disnake.HTTPException) -> bool:
        return getattr(error, "code", None) == 50035 and "Invalid emoji" in str(error)

    def _is_embed_with_v2_flag_error(self, error: disnake.HTTPException) -> bool:
        text = str(error)
        return getattr(error, "code", None) == 50035 and "IS_COMPONENTS_V2" in text and "embeds" in text

    async def _delete_original_safely(self, inter: disnake.MessageInteraction) -> None:
        for method_name in ("delete_original_message", "delete_original_response"):
            method = getattr(inter, method_name, None)
            if not method:
                continue
            try:
                await method()
                return
            except Exception:
                pass

    async def _send_embed_followup(self, inter: disnake.MessageInteraction, embed=None, components=None):
        await self._delete_original_safely(inter)
        try:
            return await inter.followup.send(embed=embed, components=components, ephemeral=True)
        except disnake.HTTPException as e:
            if components and self._is_invalid_emoji_error(e):
                logger.warning("Discord recusou um emoji do painel. Reenviando embed sem emojis.")
                components = self._strip_component_emojis(components)
                return await inter.followup.send(embed=embed, components=components, ephemeral=True)
            raise

    async def _try_initial_defer(self, inter: disnake.ApplicationCommandInteraction) -> bool:
        if inter.response.is_done():
            return True

        try:
            await inter.response.defer(ephemeral=True)
            return True
        except disnake.HTTPException as e:
            code = getattr(e, "code", None)
            if code == 40060:
                return True
            if code == 10062:
                logger.warning("A interacao do /painel expirou antes do defer. Usando envio direto no canal como fallback.")
                return False
            raise
        except disnake.NotFound:
            logger.warning("A interacao do /painel expirou antes do defer. Usando envio direto no canal como fallback.")
            return False

    async def _send_channel_fallback(self, inter: disnake.ApplicationCommandInteraction, embed=None, components=None, file=None, content=None):
        channel = getattr(inter, "channel", None)
        if channel is None:
            return None

        kwargs = {}
        if file is not None:
            kwargs["file"] = file

        if self._is_v2_components(components):
            components = self._merge_v2_components(components)
            kwargs["flags"] = disnake.MessageFlags(is_components_v2=True)
            try:
                return await channel.send(components=components, **kwargs)
            except disnake.HTTPException as e:
                if self._is_invalid_emoji_error(e):
                    logger.warning("Discord recusou um emoji do painel. Reenviando fallback sem emojis.")
                    components = self._strip_component_emojis(components)
                    return await channel.send(components=components, **kwargs)
                raise

        try:
            return await channel.send(content=content, embed=embed, components=components, **kwargs)
        except disnake.HTTPException as e:
            if components and self._is_invalid_emoji_error(e):
                logger.warning("Discord recusou um emoji do painel. Reenviando fallback sem emojis.")
                components = self._strip_component_emojis(components)
                return await channel.send(content=content, embed=embed, components=components, **kwargs)
            raise

    async def _send_expired_permission_notice(self, inter: disnake.ApplicationCommandInteraction, text: str) -> None:
        channel = getattr(inter, "channel", None)
        if channel is None:
            return
        try:
            await channel.send(f"{getattr(inter.user, 'mention', '')} {text}", delete_after=12)
        except Exception:
            pass

    def _strip_component_emojis(self, components):
        def strip_item(item):
            if hasattr(item, "emoji"):
                try:
                    item.emoji = None
                except Exception:
                    pass

            for option in getattr(item, "options", []) or []:
                try:
                    option.emoji = None
                except Exception:
                    pass

            for child in list(getattr(item, "children", []) or []):
                strip_item(child)

        for component in components or []:
            strip_item(component)
        return components

    def _embed_to_v2_components(self, embed: disnake.Embed = None, components=None):
        if self._is_v2_components(components):
            return components

        media_url = None
        if embed:
            media_url = getattr(getattr(embed, "image", None), "url", None)

        text_parts = []
        if embed:
            if embed.title:
                text_parts.append(f"# {embed.title}")
            if embed.description:
                text_parts.append(str(embed.description))
            for field in getattr(embed, "fields", []) or []:
                text_parts.append(f"**{field.name}**\n{field.value}")

        if not text_parts:
            text_parts.append("Painel")

        container_children = []
        if media_url:
            container_children.append(
                disnake.ui.MediaGallery(
                    disnake.MediaGalleryItem(
                        media_url,
                        description="Painel de gerenciamento",
                    )
                )
            )
            container_children.append(disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small))

        container_children.append(disnake.ui.TextDisplay("\n\n".join(text_parts)[:4000]))
        for component in components or []:
            if isinstance(component, disnake.ui.Container):
                continue
            container_children.append(component)

        container_kwargs = {}
        if embed and embed.color:
            container_kwargs["accent_colour"] = embed.color

        converted = [disnake.ui.Container(*container_children, **container_kwargs)]
        converted.extend([component for component in components or [] if isinstance(component, disnake.ui.Container)])
        return converted

    async def _edit_original_response(self, inter: disnake.MessageInteraction, embed=None, components=None, file=None, **kwargs):
        if file is not None:
            kwargs["file"] = file
            kwargs.setdefault("attachments", [])

        if embed is not None and not self._is_v2_components(components) and self._get_mode() != "embed":
            components = self._embed_to_v2_components(embed, components)
            embed = None

        if self._is_v2_components(components):
            components = self._merge_v2_components(components)
            kwargs.setdefault("flags", disnake.MessageFlags(is_components_v2=True))
            try:
                return await inter.edit_original_response(content=None, embed=None, components=components, **kwargs)
            except disnake.HTTPException as e:
                if self._is_invalid_emoji_error(e):
                    logger.warning("Discord recusou um emoji do painel. Reenviando componentes sem emojis.")
                    components = self._strip_component_emojis(components)
                    return await inter.edit_original_response(content=None, embed=None, components=components, **kwargs)
                raise

        try:
            return await inter.edit_original_response(content=None, embed=embed, components=components, **kwargs)
        except disnake.HTTPException as e:
            if embed is not None and self._is_embed_with_v2_flag_error(e):
                logger.warning("Mensagem original estava em Components V2. Reenviando painel embed em follow-up.")
                return await self._send_embed_followup(inter, embed=embed, components=components)
            if components and self._is_invalid_emoji_error(e):
                logger.warning("Discord recusou um emoji do painel. Reenviando componentes sem emojis.")
                components = self._strip_component_emojis(components)
                return await inter.edit_original_response(content=None, embed=embed, components=components, **kwargs)
            raise

    async def _edit_original_message(self, inter: disnake.MessageInteraction, embed=None, components=None, file=None, **kwargs):
        if file is not None:
            kwargs["file"] = file
            kwargs.setdefault("attachments", [])

        if embed is not None and not self._is_v2_components(components) and self._get_mode() != "embed":
            components = self._embed_to_v2_components(embed, components)
            embed = None

        if self._is_v2_components(components):
            components = self._merge_v2_components(components)
            kwargs.setdefault("flags", disnake.MessageFlags(is_components_v2=True))
            try:
                return await inter.edit_original_message(content=None, embed=None, components=components, **kwargs)
            except disnake.HTTPException as e:
                if self._is_invalid_emoji_error(e):
                    logger.warning("Discord recusou um emoji do painel. Reenviando componentes sem emojis.")
                    components = self._strip_component_emojis(components)
                    return await inter.edit_original_message(content=None, embed=None, components=components, **kwargs)
                raise

        try:
            return await inter.edit_original_message(content=None, embed=embed, components=components, **kwargs)
        except disnake.HTTPException as e:
            if embed is not None and self._is_embed_with_v2_flag_error(e):
                logger.warning("Mensagem original estava em Components V2. Reenviando painel embed em follow-up.")
                return await self._send_embed_followup(inter, embed=embed, components=components)
            if components and self._is_invalid_emoji_error(e):
                logger.warning("Discord recusou um emoji do painel. Reenviando componentes sem emojis.")
                components = self._strip_component_emojis(components)
                return await inter.edit_original_message(content=None, embed=embed, components=components, **kwargs)
            raise

    async def _defer_message_update(self, inter: disnake.MessageInteraction) -> None:
        if inter.response.is_done():
            return
        try:
            await inter.response.defer(with_message=False)
        except (disnake.NotFound, disnake.HTTPException):
            pass

    async def _apply_panel_result(self, inter: disnake.MessageInteraction, result):
        if inspect.isawaitable(result):
            result = await result

        if result is None:
            return

        await self._defer_message_update(inter)

        if isinstance(result, tuple):
            if len(result) == 2 and isinstance(result[0], disnake.Embed):
                embed, components = result
                return await self._edit_original_message(inter, embed=embed, components=components)

            components = []
            for item in result:
                if isinstance(item, (list, tuple)):
                    components.extend(item)
                else:
                    components.append(item)
            return await self._edit_original_message(inter, components=components)

        if isinstance(result, dict):
            embed = result.get("embed")
            components = result.get("components")
            file = result.get("file")
            extra = {
                key: value
                for key, value in result.items()
                if key not in {"content", "embed", "embeds", "components", "file"}
            }

            if "embeds" in result:
                return await inter.edit_original_message(
                    content=None,
                    embeds=result["embeds"],
                    components=components,
                    **extra,
                )

            return await self._edit_original_message(
                inter,
                embed=embed,
                components=components,
                file=file,
                **extra,
            )

        if isinstance(result, list):
            return await self._edit_original_message(inter, components=result)

    async def _send_panel_error(self, inter: disnake.MessageInteraction, detail: str = "Erro ao abrir este painel.") -> None:
        try:
            if not inter.response.is_done():
                await inter.response.send_message(f"{emoji.wrong} {detail}", ephemeral=True)
            else:
                await inter.followup.send(f"{emoji.wrong} {detail}", ephemeral=True)
        except Exception:
            pass

    async def _run_panel_method(self, inter: disnake.MessageInteraction, method):
        try:
            await message.wait(inter, send=False)
            return await self._apply_panel_result(inter, method(inter))
        except Exception as e:
            logger.error(f"Erro ao executar painel `{getattr(method, '__name__', method)}`: {e}\n{traceback.format_exc()}")
            await self._send_panel_error(inter, "Erro ao abrir este painel. O erro foi registrado no console.")

    def _can_user_access_panel(self, user_id: str, panel_id: str) -> bool:
        if str(user_id) == perms.get_owner_id():
            return True
        if owner_email_is_verified(user_id):
            return True
        if str(user_id) not in perms.get_all_users():
            return False
        return user_permissions.can_access_panel(str(user_id), panel_id)

    def _get_mode(self) -> str:
        return get_bot_mode()

    def _get_style(self) -> str:
        return get_bot_style()

    def _get_primary_color_hex(self) -> str | None:
        cached_at, cached_value = self._panel_color_cache
        if time.monotonic() - cached_at < 3.0:
            return cached_value
        colors = db.get_document("custom_colors")
        value = colors.get("primary") if colors else None
        self._panel_color_cache = (time.monotonic(), value)
        return value

    def _is_owner(self, user_id: str) -> bool:
        config = db.obter("config.json") or {}
        owner_id = config.get("bot", {}).get("owner")
        return str(user_id) == str(owner_id) or owner_email_is_verified(user_id)

    def _panel_session_key(self, inter) -> tuple:
        guild = getattr(inter, "guild", None)
        guild_id = getattr(guild, "id", None) or getattr(inter, "guild_id", None) or 0
        user = getattr(inter, "user", None) or getattr(inter, "author", None)
        user_id = getattr(user, "id", None) or 0
        return (guild_id, user_id)

    def _register_panel_session(self, inter, edit_kind: str, mode: str, style: str, show_header_image: bool, panel_layout: str | None = None) -> None:
        key = self._panel_session_key(inter)
        if not key[1]:
            return

        self._panel_sessions[key] = {
            "inter": inter,
            "kind": edit_kind,
            "mode": mode,
            "style": style,
            "panel_layout": panel_layout or get_panel_layout(),
            "show_header_image": show_header_image,
            "expires_at": time.monotonic() + PANEL_REFRESH_TTL_SECONDS,
        }

    def _unregister_panel_session(self, inter) -> None:
        self._panel_sessions.pop(self._panel_session_key(inter), None)

    async def _build_live_panel_payload(self, inter, mode: str, style: str, show_header_image: bool, panel_layout: str | None = None) -> dict:
        primary_color_hex = self._get_primary_color_hex()
        button_states = get_panel_button_states()
        panel_layout = panel_layout or get_panel_layout()

        if mode == "embed":
            embed, components = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
            if show_header_image:
                embed.set_image(url="attachment://painellyonapplications.png")
            return {"embed": embed, "components": components}

        if style == "hybrid":
            embed, components = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
            if show_header_image:
                embed.set_image(url="attachment://painellyonapplications.png")
            return {"components": self._embed_to_v2_components(embed, components)}

        return {
            "components": PainelComponents(
                inter,
                primary_color_hex,
                button_states,
                show_header_image=show_header_image,
                panel_layout=panel_layout,
            )
        }

    async def _refresh_panel_session(self, key, session: dict) -> bool:
        if time.monotonic() >= session.get("expires_at", 0):
            return False

        inter = session.get("inter")
        if inter is None:
            return False

        try:
            payload = await self._build_live_panel_payload(
                inter,
                session.get("mode") or self._get_mode(),
                session.get("style") or self._get_style(),
                bool(session.get("show_header_image")),
                session.get("panel_layout") or get_panel_layout(),
            )
            if session.get("kind") == "message":
                await self._edit_original_message(inter, **payload)
            else:
                await self._edit_original_response(inter, **payload)
            return True
        except (disnake.NotFound, disnake.HTTPException) as e:
            logger.debug(f"Parando auto refresh do /painel para {key}: {e}")
            return False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Erro ao atualizar uptime/ping do /painel: {e}")
            return False

    async def _panel_refresh_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(PANEL_REFRESH_INTERVAL_SECONDS)
            if not self._panel_sessions:
                continue

            for key, session in list(self._panel_sessions.items()):
                keep = await self._refresh_panel_session(key, session)
                if not keep:
                    self._panel_sessions.pop(key, None)

    async def _show_panel_group(self, inter: disnake.MessageInteraction, group_id: str) -> None:
        primary_color_hex = self._get_primary_color_hex()
        button_states = get_panel_button_states()
        await message.wait(inter, send=False)
        await self._edit_original_message(
            inter,
            components=PainelGroupComponents(inter, group_id, primary_color_hex, button_states),
        )

    @commands.slash_command(
        name="painel",
        description="Abre o painel de controle do bot.",
        guild_ids=utils.obter_guild_ids(),
    )
    async def painel(self, inter: disnake.ApplicationCommandInteraction):
        interaction_ready = False
        try:
            interaction_ready = await self._try_initial_defer(inter)

            # Obter configurações iniciais
            try:
                style = self._get_style()
                mode = self._get_mode()
                panel_layout = get_panel_layout()
            except Exception as e:
                logger.error(f"Erro ao obter modo do painel: {e}")
                style = "full_v2"
                mode = "components"
                panel_layout = "both"
            
            try:
                primary_color_hex = self._get_primary_color_hex()
            except Exception as e:
                logger.error(f"Erro ao obter cor primária: {e}")
                primary_color_hex = None

            # Mostrar carregamento apenas no modo V2; embed deve manter a resposta sem a flag IS_COMPONENTS_V2.
            if interaction_ready and mode != "embed":
                await message.wait(inter, send=False, use_v2_components=True)

            # Verificar permissões
            try:
                if not await perms.check(inter.user.id):
                    if not interaction_ready:
                        await self._send_expired_permission_notice(inter, f"{emoji.wrong} Voce nao tem permissao para usar este comando.")
                    elif mode == "embed":
                        await embed_message.error(inter, "Você não tem permissão para usar este comando", send=False)
                    else:
                        await message.error(inter, "Você não tem permissão para usar este comando", send=False)
                    return
            except Exception as e:
                logger.error(f"Erro ao verificar permissões: {e}")
                if interaction_ready:
                    await message.error(inter, "Erro ao verificar permissões", send=False)
                else:
                    await self._send_expired_permission_notice(inter, f"{emoji.wrong} Erro ao verificar permissões.")
                return

            # Obter estados dos botões
            try:
                button_states = get_panel_button_states()
            except Exception as e:
                logger.error(f"Erro ao obter estados dos botões: {e}")
                button_states = get_panel_button_states()

            # Exibir painel no modo embed
            if mode == "embed":
                try:
                    file = await load_panel_image_file()
                    embed, components = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
                    if file:
                        embed.set_image(url="attachment://painellyonapplications.png")
                    if interaction_ready:
                        await self._edit_original_response(inter, embed=embed, components=components, file=file)
                        self._register_panel_session(inter, "response", mode, style, file is not None, panel_layout)
                    else:
                        await self._send_channel_fallback(inter, embed=embed, components=components, file=file)
                except Exception as e:
                    logger.error(f"Erro ao exibir painel em modo embed: {e}\n{traceback.format_exc()}")
                    if interaction_ready:
                        await message.error(inter, "Erro ao carregar o painel", send=False)
                return

            # Exibir painel no modo components
            try:
                file = await load_panel_image_file()
            except Exception as e:
                logger.error(f"Erro ao carregar imagem do painel: {e}")
                file = None

            try:
                panel_embed, _ = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
            except Exception as e:
                logger.error(f"Erro ao criar embed do painel: {e}\n{traceback.format_exc()}")
                if interaction_ready:
                    await message.error(inter, "Erro ao carregar o painel", send=False)
                return

            if style == "hybrid":
                try:
                    embed, classic_components = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
                    if file:
                        embed.set_image(url="attachment://painellyonapplications.png")
                    hybrid_components = self._embed_to_v2_components(embed, classic_components)
                    if interaction_ready:
                        await self._edit_original_response(inter, components=hybrid_components, file=file)
                        self._register_panel_session(inter, "response", mode, style, file is not None, panel_layout)
                    else:
                        await self._send_channel_fallback(inter, components=hybrid_components, file=file)
                except Exception as e:
                    logger.error(f"Erro ao exibir painel em modo hybrid: {e}\n{traceback.format_exc()}")
                    if interaction_ready:
                        await message.error(inter, "Erro ao carregar o painel", send=False)
                return

            try:
                panel_components = PainelComponents(
                    inter,
                    primary_color_hex,
                    button_states,
                    show_header_image=file is not None,
                    panel_layout=panel_layout,
                )
            except Exception as e:
                logger.error(f"Erro ao criar componentes do painel: {e}\n{traceback.format_exc()}")
                if interaction_ready:
                    await message.error(inter, "Erro ao carregar os botões do painel", send=False)
                else:
                    await self._send_channel_fallback(inter, content=f"{emoji.wrong} Erro ao carregar os botões do painel.")
                return

            # Enviar painel com imagem se disponível
            if file:
                try:
                    panel_embed.set_image(url="attachment://painellyonapplications.png")
                    if interaction_ready:
                        await self._edit_original_response(inter, embed=panel_embed, components=panel_components, file=file)
                        self._register_panel_session(inter, "response", mode, style, True, panel_layout)
                    else:
                        await self._send_channel_fallback(inter, components=panel_components, file=file)
                except Exception as e:
                    logger.error(f"Erro ao enviar painel com imagem: {e}\n{traceback.format_exc()}")
                    retry_file = await load_panel_image_file()
                    fallback_components = PainelComponents(
                        inter,
                        primary_color_hex,
                        button_states,
                        show_header_image=retry_file is not None,
                        panel_layout=panel_layout,
                    )
                    if interaction_ready:
                        await self._edit_original_response(inter, embed=panel_embed, components=fallback_components, file=retry_file)
                        self._register_panel_session(inter, "response", mode, style, retry_file is not None, panel_layout)
                    else:
                        await self._send_channel_fallback(inter, components=fallback_components, file=retry_file)
                return

            # Enviar painel sem imagem
            try:
                if interaction_ready:
                    await self._edit_original_response(inter, embed=panel_embed, components=panel_components)
                    self._register_panel_session(inter, "response", mode, style, False, panel_layout)
                else:
                    await self._send_channel_fallback(inter, components=panel_components)
            except Exception as e:
                logger.error(f"Erro ao enviar painel: {e}\n{traceback.format_exc()}")
                if interaction_ready:
                    await message.error(inter, "Erro ao carregar o painel", send=False)

        except Exception as e:
            logger.error(f"Erro não tratado no painel: {e}\n{traceback.format_exc()}")
            try:
                if interaction_ready:
                    await message.error(inter, "Erro ao abrir o painel", send=False)
            except:
                pass

    @commands.Cog.listener("on_message_interaction")
    async def Painel_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = getattr(inter.component, "custom_id", "")
        if custom_id == "Painel_Select" or not custom_id.startswith("Painel"):
            return

        panel_id = custom_id
        if panel_id == "PainelAnterior":
            panel_id = "PainelInicial"
        if panel_id in PANEL_GROUP_IDS:
            self._unregister_panel_session(inter)
            await self._show_panel_group(inter, panel_id)
            return

        if panel_id != "PainelInicial" and not self._can_user_access_panel(inter.user.id, panel_id):
            await inter.response.send_message(f"{emoji.wrong} Você não tem permissão para acessar este painel.", ephemeral=True)
            return

        if panel_id != "PainelInicial":
            self._unregister_panel_session(inter)

        if panel_id == "PainelInicial":
            style = self._get_style()
            mode = self._get_mode()
            panel_layout = get_panel_layout()
            primary_color_hex = self._get_primary_color_hex()

            if mode == "embed":
                await embed_message.wait(inter)
            else:
                await self._defer_message_update(inter)

            button_states = get_panel_button_states()
            if mode == "embed":
                file = await load_panel_image_file()
                embed, components = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
                if file:
                    embed.set_image(url="attachment://painellyonapplications.png")
                await self._edit_original_message(inter, embed=embed, components=components, file=file)
                self._register_panel_session(inter, "message", mode, style, file is not None, panel_layout)
            elif style == "hybrid":
                file = await load_panel_image_file()
                embed, components = PainelEmbed(inter, primary_color_hex, button_states, panel_layout=panel_layout)
                if file:
                    embed.set_image(url="attachment://painellyonapplications.png")
                await self._edit_original_message(
                    inter,
                    components=self._embed_to_v2_components(embed, components),
                    file=file,
                )
                self._register_panel_session(inter, "message", mode, style, file is not None, panel_layout)
            else:
                file = await load_panel_image_file()
                await self._edit_original_message(
                    inter,
                    components=PainelComponents(inter, primary_color_hex, button_states, show_header_image=file is not None, panel_layout=panel_layout),
                    file=file,
                )
                self._register_panel_session(inter, "message", mode, style, file is not None, panel_layout)
            return

        if inter.component.custom_id == "Painel_Protection":
            if not self._is_owner(inter.user.id):
                await inter.response.send_message(f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.", ephemeral=True)
                return
            protection_cog = self.bot.get_cog("ProtectionCog")
            if protection_cog:
                await self._run_panel_method(inter, protection_cog.display_protection_panel)
            return

        if inter.component.custom_id == "Painel_Cloud":
            if not self._is_owner(inter.user.id):
                await inter.response.send_message(f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.", ephemeral=True)
                return
            cloud_cog = self.bot.get_cog("Cloud")
            if cloud_cog:
                await self._run_panel_method(inter, cloud_cog.display_cloud_panel)
            return

        if panel_id == "Painel_Loja":
            loja_cog = self.bot.get_cog("Loja")
            if not loja_cog:
                await inter.response.send_message(f"{emoji.wrong} O painel de loja nao esta carregado.", ephemeral=True)
                return
            await self._run_panel_method(inter, loja_cog.panel)
            return

        if panel_id == "Painel_Personalizacao":
            personalizacao_cog = self.bot.get_cog("Personalizacao")
            if not personalizacao_cog:
                await inter.response.send_message(f"{emoji.wrong} O painel de themes nao esta carregado.", ephemeral=True)
                return

            mode = self._get_mode()
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = personalizacao_cog.personalizacao_embed(inter)
                await self._edit_original_message(inter, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_original_message(inter, components=personalizacao_cog.personalizacao_components(inter))
            return

        if panel_id == "Painel_Configuracoes":
            settings_cog = self.bot.get_cog("Settings")
            method = getattr(settings_cog, "display_configuracoes_panel", None) if settings_cog else None
            if not method:
                await inter.response.send_message(f"{emoji.wrong} O painel de configuracoes nao esta carregado.", ephemeral=True)
                return
            await self._run_panel_method(inter, method)
            return

        panel_map = {
            "Painel_Automacoes": ("AutomationModulesCog", "display_automations_panel"),
            "Painel_Automações": ("AutomationModulesCog", "display_automations_panel"),
            "Painel_Economia": ("Economia", "display_economia_panel"),
            "Painel_Comunidade": ("Comunidade", "display_comunidade_panel"),
            "Painel_Ferramentas": ("Ferramentas", "display_ferramentas_panel"),
            "Painel_Parcerias": ("Parcerias", "display_parcerias_panel"),
            "Painel_Ticket": ("TicketConfigCog", "display_ticket_panel"),
            "Painel_ApostadoFF": ("ApostadoFreeFire", "display_apostado_panel"),
            "Painel_Middleman": ("MiddlemanPanel", "display_middleman_panel"),
            "Painel_Sorteios": ("Giveaways", "display_giveaways_panel"),
            "Painel_Giveaways": ("Giveaways", "display_giveaways_panel"),
            "Painel_Rendimentos": ("RendimentosLyon", "panel"),
            "Painel_BoasVindas": ("BoasVindasPanel", "display_boasvindas_panel"),
            "Painel_GiftCard": ("GiftCardPanel", "display_giftcard_panel"),
            "Painel_Key": ("KeysPanel", "display_keys_panel"),
            "Painel_Conversor": ("ConversorCog", "display_conversor_panel"),
            "Painel_Twitter": ("TwitterCog", "display_twitter_panel"),
            "Painel_SistemaIA": ("SistemaIAPanel", "display_sistemaai_panel"),
            "Painel_FilasApostas": ("ApostadoFreeFire", "display_apostado_panel"),
            "Painel_Moderacao": ("ModeradorPanel", "display_moderacao_panel"),
            "Painel_Verificacao": ("VerificacaoPanel", "display_verificacao_panel"),
            "Painel_AntiFraude": ("AntiFraudePanel", "display_antifraud_panel"),
            "Painel_ScamDetector": ("ScamDetectorPanel", "display_scam_detector_panel"),
            "Painel_AutoSetup": ("AutoSetupPanel", "display_auto_setup_panel"),
            "Painel_GIFs": ("GIFsPanel", "display_gifs_panel"),
            "Painel_Ranking": ("RanksPanel", "display_ranking_panel"),
            "Painel_Robux": ("RobuxPanel", "display_robux_panel"),
            "Painel_Engajamento": ("SocialLyonsPanel", "display_engagement_panel"),
            "Painel_Instagram": ("SocialLyonsPanel", "display_instagram_panel"),
            "Painel_Organizador": ("ServerOrganizerPanel", "display_server_organizer_panel"),
            "Painel_FiveM": ("FiveMLyonPanel", "display_fivem_panel"),
            "Painel_BatePonto": ("BatePontoPanel", "display_bateponto_panel"),
            "Painel_Stock": ("StockPanel", "display_stock_panel"),
            "Painel_Feedback": ("FeedbackPanel", "display_feedback_panel"),
        }

        panel_entry = panel_map.get(panel_id)
        if not panel_entry:
            await inter.response.send_message(f"{emoji.wrong} Painel nao encontrado ou ainda nao conectado.", ephemeral=True)
            return

        cog_name, method_name = panel_entry
        cog = self.bot.get_cog(cog_name)
        method = getattr(cog, method_name, None) if cog else None
        if not method:
            await inter.response.send_message(f"{emoji.wrong} O sistema `{cog_name}` nao esta carregado.", ephemeral=True)
            return

        await self._run_panel_method(inter, method)

    @commands.Cog.listener("on_message_interaction")
    async def Painel_Dropdown_Listener(self, inter: disnake.MessageInteraction):
        component_id = inter.component.custom_id
        if component_id != "Painel_Select":
            return

        choice = inter.values[0]
        if choice == "none":
            await self._defer_message_update(inter)
            return

        if not self._can_user_access_panel(inter.user.id, choice):
            await inter.response.send_message(f"{emoji.wrong} Você não tem permissão para acessar este painel.", ephemeral=True)
            return

        if choice in {"Painel_Cloud", "Painel_Protection"} and not self._is_owner(inter.user.id):
            await inter.response.send_message(f"{emoji.wrong} Apenas o dono do bot pode acessar esta funcionalidade.", ephemeral=True)
            return

        self._unregister_panel_session(inter)

        mode = self._get_mode()
        panel_map = {
            "Painel_Ticket": ("TicketConfigCog", "display_ticket_panel"),
            "Painel_Automacoes": ("AutomationModulesCog", "display_automations_panel"),
            "Painel_Automações": ("AutomationModulesCog", "display_automations_panel"),
            "Painel_Economia": ("Economia", "display_economia_panel"),
            "Painel_Comunidade": ("Comunidade", "display_comunidade_panel"),
            "Painel_Ferramentas": ("Ferramentas", "display_ferramentas_panel"),
            "Painel_Parcerias": ("Parcerias", "display_parcerias_panel"),
            "Painel_BoasVindas": ("BoasVindasPanel", "display_boasvindas_panel"),
            "Painel_GiftCard": ("GiftCardPanel", "display_giftcard_panel"),
            "Painel_Key": ("KeysPanel", "display_keys_panel"),
            "Painel_Conversor": ("ConversorCog", "display_conversor_panel"),
            "Painel_Twitter": ("TwitterCog", "display_twitter_panel"),
            "Painel_SistemaIA": ("SistemaIAPanel", "display_sistemaai_panel"),
            "Painel_FilasApostas": ("ApostadoFreeFire", "display_apostado_panel"),
            "Painel_Moderacao": ("ModeradorPanel", "display_moderacao_panel"),
            "Painel_Verificacao": ("VerificacaoPanel", "display_verificacao_panel"),
            "Painel_AntiFraude": ("AntiFraudePanel", "display_antifraud_panel"),
            "Painel_ScamDetector": ("ScamDetectorPanel", "display_scam_detector_panel"),
            "Painel_AutoSetup": ("AutoSetupPanel", "display_auto_setup_panel"),
            "Painel_GIFs": ("GIFsPanel", "display_gifs_panel"),
            "Painel_Ranking": ("RanksPanel", "display_ranking_panel"),
            "Painel_Robux": ("RobuxPanel", "display_robux_panel"),
            "Painel_Engajamento": ("SocialLyonsPanel", "display_engagement_panel"),
            "Painel_Instagram": ("SocialLyonsPanel", "display_instagram_panel"),
            "Painel_Organizador": ("ServerOrganizerPanel", "display_server_organizer_panel"),
            "Painel_FiveM": ("FiveMLyonPanel", "display_fivem_panel"),
            "Painel_BatePonto": ("BatePontoPanel", "display_bateponto_panel"),
            "Painel_Stock": ("StockPanel", "display_stock_panel"),
            "Painel_Feedback": ("FeedbackPanel", "display_feedback_panel"),
            "Painel_Cloud": ("Cloud", "display_cloud_panel"),
            "Painel_Protection": ("ProtectionCog", "display_protection_panel"),
            "Painel_Rendimentos": ("RendimentosLyon", "panel"),
            "Painel_Personalizacao": ("Personalizacao", "personalizacao_embed"),
            "Painel_Loja": ("Loja", "panel"),
            "Painel_ApostadoFF": ("ApostadoFreeFire", "display_apostado_panel"),
            "Painel_Middleman": ("MiddlemanPanel", "display_middleman_panel"),
            "Painel_Giveaways": ("Giveaways", "display_giveaways_panel"),
            "Painel_Sorteios": ("Giveaways", "display_giveaways_panel"),
            "Painel_Configuracoes": ("Settings", "display_configuracoes_panel"),
        }

        panel_entry = panel_map.get(choice)
        if not panel_entry:
            await inter.response.send_message(f"{emoji.wrong} Painel nao encontrado ou ainda nao conectado.", ephemeral=True)
            return

        cog_name, method_name = panel_entry
        cog = self.bot.get_cog(cog_name)
        if not cog:
            await inter.response.send_message(f"{emoji.wrong} O sistema `{cog_name}` nao esta carregado.", ephemeral=True)
            return

        method = getattr(cog, method_name, None)
        if not method:
            await inter.response.send_message(f"{emoji.wrong} O metodo `{method_name}` nao foi encontrado.", ephemeral=True)
            return

        if choice == "Painel_Loja":
            msg_handler = embed_message if mode == "embed" else message
            await msg_handler.wait(inter, send=False)
            panel_data = cog.panel(inter)
            if isinstance(panel_data, dict) and "embed" not in panel_data:
                await self._edit_original_message(inter, **panel_data, flags=disnake.MessageFlags(is_components_v2=True))
            else:
                await self._edit_original_message(inter, **panel_data)
            return

        if choice == "Painel_Personalizacao":
            if mode == "embed":
                await embed_message.wait(inter, send=False)
                embed, components = method(inter)
                await self._edit_original_message(inter, embed=embed, components=components)
            else:
                await message.wait(inter, send=False)
                await self._edit_original_message(inter, components=cog.personalizacao_components(inter))
            return

        if choice == "Painel_Rendimentos":
            if mode == "embed":
                await embed_message.wait(inter)
            else:
                await message.wait(inter)
            panel_data = method(inter)
            if mode == "embed":
                embed, components = panel_data
                await self._edit_original_message(inter, embed=embed, components=components)
            else:
                await self._edit_original_message(inter, **panel_data)
            return

        await self._run_panel_method(inter, method)
