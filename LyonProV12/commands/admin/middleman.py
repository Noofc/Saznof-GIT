import secrets
import time
import asyncio

import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.bool_utils import as_bool
from .panel_v2 import build_panel_card, channel_label, status_label
from .painel.components import PainelComponents


KEY_PREFIX = "middleman_"
DEFAULT_FEE = 0.0


def _emoji(name: str, fallback=None):
    value = getattr(emoji, name, None)
    if value:
        return value
    if isinstance(fallback, str):
        fallback_value = getattr(emoji, fallback, None)
        if fallback_value:
            return fallback_value
        if fallback.startswith("<"):
            return fallback
    return getattr(emoji, "commands", "")


class MiddlemanPanel(commands.Cog):
    """Sistema de middleman integrado ao painel, sem comandos slash."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._send_panel_cooldowns = {}

    def _flags(self) -> disnake.MessageFlags:
        return disnake.MessageFlags(is_components_v2=True)

    def _key(self, guild_id: int) -> str:
        return f"{KEY_PREFIX}{guild_id}"

    def _get_config(self, guild_id: int) -> dict:
        data = db.get_document(self._key(guild_id)) or {}
        return data if isinstance(data, dict) else {}

    def _save_config(self, guild_id: int, data: dict) -> None:
        db.save_document(self._key(guild_id), data)

    def _fee_text(self, value) -> str:
        try:
            fee = max(0, float(str(value).replace(",", ".")))
        except (TypeError, ValueError):
            fee = DEFAULT_FEE
        return f"R$ {fee:.2f}".replace(".", ",")

    def _roles_text(self, role_ids) -> str:
        if not isinstance(role_ids, list) or not role_ids:
            return "`Nao configurado`"
        return ", ".join(f"<@&{role_id}>" for role_id in role_ids[:8])

    def _can_manage(self, inter: disnake.MessageInteraction, cfg: dict) -> bool:
        perms = getattr(inter.author, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_guild):
            return True
        staff_roles = {str(role_id) for role_id in cfg.get("staff_roles", []) if role_id}
        return any(str(role.id) in staff_roles for role in getattr(inter.author, "roles", []))

    async def _safe_defer(self, inter: disnake.MessageInteraction, *, ephemeral: bool = False, with_message: bool | None = None) -> bool:
        if inter.response.is_done():
            return True
        try:
            kwargs = {"ephemeral": ephemeral}
            if with_message is not None:
                kwargs["with_message"] = with_message
            await inter.response.defer(**kwargs)
            return True
        except disnake.HTTPException as exc:
            if getattr(exc, "code", None) == 40060:
                return True
            print(f"[Middleman] Interacao expirada/indisponivel ao deferir: {exc}")
            return False
        except disnake.NotFound as exc:
            print(f"[Middleman] Interacao expirada ao deferir: {exc}")
            return False

    async def _safe_reply(self, inter: disnake.MessageInteraction, text: str, *, ephemeral: bool = True):
        try:
            if inter.response.is_done():
                return await inter.followup.send(text, ephemeral=ephemeral)
            return await inter.response.send_message(text, ephemeral=ephemeral)
        except (disnake.NotFound, disnake.HTTPException) as exc:
            print(f"[Middleman] Falha ao responder interacao: {exc}")
            return None

    def _active_cases(self, cfg: dict) -> int:
        cases = cfg.get("cases") if isinstance(cfg.get("cases"), dict) else {}
        return sum(1 for case in cases.values() if case.get("status") == "open")

    def display_middleman_panel(self, inter: disnake.MessageInteraction):
        cfg = self._get_config(inter.guild.id)
        enabled = as_bool(cfg.get("enabled"), False)
        return build_panel_card(
            title=f"{_emoji('shield', '')} Middleman",
            breadcrumb="Painel > Middleman",
            description=(
                "Configure um atendimento de intermediação para compras, trocas e acordos entre usuarios. "
                "O painel publico abre um canal privado para o cliente e a equipe."
            ),
            status_lines=[
                f"**Status:** {status_label(enabled)}",
                f"**Categoria:** {channel_label(cfg.get('category_id'))}",
                f"**Canal de logs:** {channel_label(cfg.get('logs_channel_id'))}",
                f"**Equipe:** {self._roles_text(cfg.get('staff_roles'))}",
                f"**Taxa:** `{self._fee_text(cfg.get('service_fee', DEFAULT_FEE))}`",
                f"**Atendimentos abertos:** `{self._active_cases(cfg)}`",
            ],
            rows=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Desativar" if enabled else "Ativar",
                        style=disnake.ButtonStyle.danger if enabled else disnake.ButtonStyle.success,
                        emoji=_emoji("power"),
                        custom_id="Middleman_Toggle",
                    ),
                    disnake.ui.Button(label="Enviar Painel", style=disnake.ButtonStyle.success, emoji=_emoji("send", _emoji("rocket")), custom_id="Middleman_SendPanel"),
                    disnake.ui.Button(label="Taxa", style=disnake.ButtonStyle.grey, emoji=_emoji("dollar"), custom_id="Middleman_Fee"),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Categoria", style=disnake.ButtonStyle.grey, emoji=_emoji("folder"), custom_id="Middleman_Category"),
                    disnake.ui.Button(label="Logs", style=disnake.ButtonStyle.grey, emoji=_emoji("speech"), custom_id="Middleman_Logs"),
                    disnake.ui.Button(label="Equipe", style=disnake.ButtonStyle.blurple, emoji=_emoji("staff", _emoji("members")), custom_id="Middleman_Staff"),
                ),
            ],
        )

    def _build_public_panel(self, guild_id: int) -> list:
        cfg = self._get_config(guild_id)
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {_emoji('shield', '')} Middleman"),
                disnake.ui.TextDisplay(
                    "Abra uma solicitação de intermediação para uma compra, troca ou acordo.\n"
                    f"**Taxa do serviço:** `{self._fee_text(cfg.get('service_fee', DEFAULT_FEE))}`\n"
                    f"**Status:** {status_label(as_bool(cfg.get('enabled'), False))}"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Solicitar Middleman",
                        style=disnake.ButtonStyle.success,
                        emoji=_emoji("shield"),
                        custom_id="Middleman_Request",
                    )
                ),
                accent_colour=disnake.Colour.blue(),
            )
        ]

    def _build_config_select(self, custom_id: str, placeholder: str, select_type: str) -> list:
        if select_type == "category":
            select = disnake.ui.ChannelSelect(
                placeholder=placeholder,
                custom_id=custom_id,
                min_values=1,
                max_values=1,
                channel_types=[disnake.ChannelType.category],
            )
        elif select_type == "text":
            select = disnake.ui.ChannelSelect(
                placeholder=placeholder,
                custom_id=custom_id,
                min_values=1,
                max_values=1,
                channel_types=[disnake.ChannelType.text],
            )
        else:
            select = disnake.ui.RoleSelect(
                placeholder=placeholder,
                custom_id=custom_id,
                min_values=1,
                max_values=25,
            )
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {_emoji('settings', '')} Middleman"),
                disnake.ui.TextDisplay("Selecione a opção desejada abaixo."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(select),
                accent_colour=disnake.Colour.blue(),
            ),
        ]

    async def _edit_admin_panel(self, inter: disnake.MessageInteraction, components: list):
        if not await self._safe_defer(inter, with_message=False):
            return
        try:
            await inter.edit_original_message(content=None, embed=None, components=components, flags=self._flags())
        except (disnake.NotFound, disnake.HTTPException) as exc:
            print(f"[Middleman] Falha ao editar painel: {exc}")

    async def _log(self, guild: disnake.Guild, cfg: dict, text: str):
        channel_id = cfg.get("logs_channel_id")
        channel = guild.get_channel(int(channel_id)) if guild and channel_id else None
        if isinstance(channel, disnake.TextChannel):
            try:
                await channel.send(text)
            except disnake.HTTPException:
                pass

    def _build_case_panel(self, user: disnake.User | disnake.Member, cfg: dict, case_id: str) -> list:
        fee = self._fee_text(cfg.get("service_fee", DEFAULT_FEE))
        diamond = _emoji("diamond", "diamond")
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(user.mention),
                disnake.ui.TextDisplay(f"## {diamond} - Middleman de PIX criado."),
                disnake.ui.TextDisplay(
                    "Seja bem vindo ao novo ticket automatico de MiddleMan, com seguranca e agilidade.\n"
                    "E importante que voce selecione as opcoes ao longo do ticket corretamente e responda as "
                    "perguntas que o bot fizer. Revise sempre antes de prosseguir qualquer passo para evitar scams e erros."
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(
                    "**Passos:**\n"
                    "1. Adicione o usuario com quem vai negociar usando o menu ou botao abaixo.\n"
                    "2. O bot pedira para ambos descreverem os itens no chat.\n"
                    "3. Apos confirmacao, siga as orientacoes da equipe para finalizar com seguranca.\n\n"
                    f"**Taxa do servico:** `{fee}`"
                ),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Adicionar por ID",
                        style=disnake.ButtonStyle.blurple,
                        emoji=_emoji("member", "members"),
                        custom_id=f"Middleman_AddById:{case_id}",
                    ),
                    disnake.ui.Button(
                        label="Cancelar MM",
                        style=disnake.ButtonStyle.danger,
                        emoji=_emoji("wrong", "wrong"),
                        custom_id=f"Middleman_Cancel:{case_id}",
                    ),
                    disnake.ui.Button(
                        label="Termos MM",
                        style=disnake.ButtonStyle.grey,
                        emoji=_emoji("lock", "shield"),
                        custom_id=f"Middleman_Terms:{case_id}",
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.UserSelect(
                        placeholder="Quem vai adicionar ao middleman?",
                        custom_id=f"Middleman_AddUserSelect:{case_id}",
                        min_values=1,
                        max_values=5,
                    )
                ),
                accent_colour=disnake.Colour.dark_gold(),
            )
        ]

    def _closing_components(self) -> list:
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {_emoji('lock', 'shield')} - Fechando Middleman"),
                disnake.ui.TextDisplay("Este middleman sera fechado em 5 segundos..."),
                accent_colour=disnake.Colour.dark_gold(),
            )
        ]

    def _terms_components(self) -> list:
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"## {_emoji('shield', '')} Termos do Middleman"),
                disnake.ui.TextDisplay(
                    "1. Nunca finalize uma negociacao fora do ticket.\n"
                    "2. Confirme usuario, item, valor e comprovantes antes de prosseguir.\n"
                    "3. A equipe pode encerrar o atendimento se houver tentativa de golpe ou abuso.\n"
                    "4. Use este canal como historico oficial da negociacao."
                ),
                accent_colour=disnake.Colour.dark_gold(),
            )
        ]

    async def _send_components_reply(self, inter: disnake.MessageInteraction, components: list, *, ephemeral: bool = True):
        try:
            if inter.response.is_done():
                return await inter.followup.send(components=components, flags=self._flags(), ephemeral=ephemeral)
            return await inter.response.send_message(components=components, flags=self._flags(), ephemeral=ephemeral)
        except (disnake.NotFound, disnake.HTTPException) as exc:
            print(f"[Middleman] Falha ao responder com componentes: {exc}")
            return None

    async def _resolve_member(self, guild: disnake.Guild, user_id) -> disnake.Member | None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except disnake.HTTPException:
            return None

    async def _add_member_to_case(
        self,
        *,
        guild: disnake.Guild,
        channel: disnake.TextChannel,
        cfg: dict,
        case: dict,
        case_id: str,
        member: disnake.Member,
        added_by: disnake.User | disnake.Member,
    ) -> str:
        await channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            reason=f"Usuario adicionado ao Middleman {case_id}",
        )
        participants = {str(value) for value in case.get("participants", [])}
        participants.add(str(member.id))
        case["participants"] = sorted(participants)
        self._save_config(guild.id, cfg)
        await channel.send(f"{emoji.correct} {member.mention} foi adicionado ao middleman por {added_by.mention}.")
        await self._log(guild, cfg, f"{member.mention} adicionado ao Middleman `{case_id}` por {added_by.mention}.")
        return f"{emoji.correct} {member.mention} adicionado ao atendimento."

    async def _close_case_channel(self, inter: disnake.MessageInteraction, case: dict, case_id: str):
        channel_id = case.get("channel_id")
        channel = inter.guild.get_channel(int(channel_id)) if inter.guild and channel_id else None
        if not isinstance(channel, disnake.TextChannel):
            channel = inter.channel if isinstance(inter.channel, disnake.TextChannel) else None
        if not isinstance(channel, disnake.TextChannel):
            return

        try:
            await asyncio.sleep(5)
            await channel.delete(reason=f"Middleman {case_id} fechado por {inter.user}")
            return
        except disnake.HTTPException as exc:
            print(f"[Middleman] Nao foi possivel apagar o canal do atendimento {case_id}: {exc}")

        try:
            overwrites = channel.overwrites
            for target, overwrite in list(overwrites.items()):
                overwrite.send_messages = False
                overwrites[target] = overwrite
            await channel.edit(
                name=f"closed-{channel.name}"[:90],
                overwrites=overwrites,
                reason=f"Middleman {case_id} fechado por {inter.user}",
            )
        except disnake.HTTPException as exc:
            print(f"[Middleman] Nao foi possivel travar o canal do atendimento {case_id}: {exc}")

    async def _create_case_channel(self, inter: disnake.MessageInteraction, cfg: dict) -> disnake.TextChannel | None:
        guild = inter.guild
        if not guild:
            return None

        cases = cfg.setdefault("cases", {})
        for case in cases.values():
            if case.get("status") != "open":
                continue
            if str(case.get("user_id")) != str(inter.user.id):
                continue
            channel_id = case.get("channel_id")
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            if isinstance(channel, disnake.TextChannel):
                return channel

        case_id = secrets.token_hex(3)
        category_id = cfg.get("category_id")
        category = guild.get_channel(int(category_id)) if category_id else None
        if not isinstance(category, disnake.CategoryChannel):
            category = getattr(inter.channel, "category", None)

        overwrites = {
            guild.default_role: disnake.PermissionOverwrite(view_channel=False),
            guild.me: disnake.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
            inter.user: disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for role_id in cfg.get("staff_roles", []):
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = disnake.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        safe_name = "".join(char for char in inter.user.name.lower() if char.isalnum() or char in "-_") or str(inter.user.id)
        try:
            channel = await guild.create_text_channel(
                name=f"middleman-{safe_name}-{case_id}"[:90],
                category=category,
                overwrites=overwrites,
                reason="Solicitacao de Middleman",
            )
        except disnake.HTTPException:
            return None

        cases[case_id] = {
            "id": case_id,
            "status": "open",
            "channel_id": channel.id,
            "user_id": inter.user.id,
            "participants": [str(inter.user.id)],
            "claimed_by": None,
            "created_at": disnake.utils.utcnow().isoformat(),
        }
        self._save_config(guild.id, cfg)

        staff_ping = " ".join(f"<@&{role_id}>" for role_id in cfg.get("staff_roles", []))
        await channel.send(
            components=self._build_case_panel(inter.user, cfg, case_id),
            flags=self._flags(),
        )
        if staff_ping:
            await channel.send(staff_ping, delete_after=2)
        await self._log(guild, cfg, f"Middleman aberto por {inter.user.mention}: {channel.mention} (`{case_id}`).")
        return channel

    @commands.Cog.listener("on_button_click")
    async def on_middleman_button(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if not cid.startswith("Middleman_"):
            return

        public_actions = (
            cid == "Middleman_Request"
            or cid.startswith("Middleman_Claim:")
            or cid.startswith("Middleman_Close:")
            or cid.startswith("Middleman_Cancel:")
            or cid.startswith("Middleman_Terms:")
            or cid.startswith("Middleman_AddById:")
        )
        slow_actions = (
            cid == "Middleman_Request"
            or cid == "Middleman_SendPanel"
            or cid.startswith("Middleman_Claim:")
            or cid.startswith("Middleman_Close:")
            or cid.startswith("Middleman_Cancel:")
            or cid.startswith("Middleman_Terms:")
        )
        if slow_actions:
            if not await self._safe_defer(inter, ephemeral=cid in {"Middleman_Request", "Middleman_SendPanel"}):
                return

        cfg = self._get_config(inter.guild.id)

        if not public_actions and not self._can_manage(inter, cfg):
            await self._safe_reply(inter, f"{emoji.wrong} Voce nao tem permissao para configurar o Middleman.", ephemeral=True)
            return

        if cid == "Middleman_Back":
            await self._edit_admin_panel(inter, PainelComponents(inter))
            return

        if cid == "Middleman_Toggle":
            cfg["enabled"] = not as_bool(cfg.get("enabled"), False)
            self._save_config(inter.guild.id, cfg)
            await self._edit_admin_panel(inter, self.display_middleman_panel(inter))
            await inter.followup.send(f"{emoji.correct} Middleman {'ativado' if cfg['enabled'] else 'desativado'}.", ephemeral=True)
            return

        if cid == "Middleman_Category":
            await self._edit_admin_panel(inter, self._build_config_select("Middleman_SelectCategory", "Categoria dos atendimentos", "category"))
            return

        if cid == "Middleman_Logs":
            await self._edit_admin_panel(inter, self._build_config_select("Middleman_SelectLogs", "Canal de logs", "text"))
            return

        if cid == "Middleman_Staff":
            await self._edit_admin_panel(inter, self._build_config_select("Middleman_SelectStaff", "Cargos da equipe", "role"))
            return

        if cid == "Middleman_SendPanel":
            cooldown_key = f"{inter.guild.id}:{inter.channel.id}:{inter.author.id}"
            now = time.time()
            if now - self._send_panel_cooldowns.get(cooldown_key, 0) < 5:
                await self._safe_reply(
                    inter,
                    f"{emoji.warn} O painel de Middleman ja foi enviado agora. Aguarde alguns segundos.",
                    ephemeral=True,
                )
                return

            interaction_id = str(getattr(inter, "id", ""))
            if interaction_id and cfg.get("last_panel_send_interaction") == interaction_id:
                await self._safe_reply(inter, f"{emoji.warn} Este envio ja foi processado.", ephemeral=True)
                return

            self._send_panel_cooldowns[cooldown_key] = now
            if interaction_id:
                cfg["last_panel_send_interaction"] = interaction_id
            cfg["last_panel_sent_at"] = disnake.utils.utcnow().isoformat()
            self._save_config(inter.guild.id, cfg)

            await inter.channel.send(components=self._build_public_panel(inter.guild.id), flags=self._flags())
            await self._safe_reply(inter, f"{emoji.correct} Painel de Middleman enviado em {inter.channel.mention}.", ephemeral=True)
            return

        if cid == "Middleman_Fee":
            source_message = inter.message
            cog = self

            class FeeModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Taxa do Middleman",
                        custom_id="Middleman_FeeModal",
                        components=[
                            disnake.ui.TextInput(label="Taxa de servico", custom_id="service_fee", placeholder="Ex.: 5.00", required=True, max_length=12)
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    raw = values.get("service_fee", "0").replace(",", ".").strip()
                    try:
                        fee = max(0, float(raw))
                    except ValueError:
                        await modal_inter.response.send_message(f"{emoji.wrong} Taxa invalida.", ephemeral=True)
                        return
                    cfg_local = cog._get_config(modal_inter.guild.id)
                    cfg_local["service_fee"] = round(fee, 2)
                    cog._save_config(modal_inter.guild.id, cfg_local)
                    if not modal_inter.response.is_done():
                        await modal_inter.response.defer(ephemeral=True)
                    await source_message.edit(content=None, embed=None, components=cog.display_middleman_panel(modal_inter), flags=cog._flags())
                    await modal_inter.followup.send(f"{emoji.correct} Taxa do Middleman salva como `{cog._fee_text(fee)}`.", ephemeral=True)

            await inter.response.send_modal(FeeModal())
            return

        if cid.startswith("Middleman_AddById:"):
            case_id = cid.split(":", 1)[1]
            cog = self

            class AddByIdModal(disnake.ui.Modal):
                def __init__(self):
                    super().__init__(
                        title="Adicionar ao Middleman",
                        custom_id=f"Middleman_AddByIdModal:{case_id}",
                        components=[
                            disnake.ui.TextInput(
                                label="ID do usuario",
                                custom_id="user_id",
                                placeholder="Cole o ID do usuario que vai negociar",
                                required=True,
                                max_length=24,
                            )
                        ],
                    )

                async def callback(self, modal_inter: disnake.ModalInteraction):
                    values = getattr(modal_inter, "text_values", None) or getattr(modal_inter, "resolved_values", {})
                    user_id = str(values.get("user_id", "")).strip()
                    cfg_local = cog._get_config(modal_inter.guild.id)
                    case = cfg_local.setdefault("cases", {}).get(case_id)
                    if not case or case.get("status") != "open":
                        await modal_inter.response.send_message(f"{emoji.wrong} Atendimento nao encontrado ou fechado.", ephemeral=True)
                        return

                    channel_id = case.get("channel_id")
                    channel = modal_inter.guild.get_channel(int(channel_id)) if channel_id else modal_inter.channel
                    if not isinstance(channel, disnake.TextChannel):
                        await modal_inter.response.send_message(f"{emoji.wrong} Canal do atendimento nao encontrado.", ephemeral=True)
                        return

                    member = await cog._resolve_member(modal_inter.guild, user_id)
                    if not member:
                        await modal_inter.response.send_message(f"{emoji.wrong} Usuario nao encontrado neste servidor.", ephemeral=True)
                        return

                    try:
                        text = await cog._add_member_to_case(
                            guild=modal_inter.guild,
                            channel=channel,
                            cfg=cfg_local,
                            case=case,
                            case_id=case_id,
                            member=member,
                            added_by=modal_inter.user,
                        )
                    except disnake.HTTPException:
                        await modal_inter.response.send_message(f"{emoji.wrong} Nao consegui liberar esse usuario no canal.", ephemeral=True)
                        return

                    await modal_inter.response.send_message(text, ephemeral=True)

            await inter.response.send_modal(AddByIdModal())
            return

        if cid == "Middleman_Request":
            if not as_bool(cfg.get("enabled"), False):
                await self._safe_reply(inter, f"{emoji.wrong} O Middleman esta desativado no momento.", ephemeral=True)
                return
            channel = await self._create_case_channel(inter, cfg)
            if not channel:
                await self._safe_reply(inter, f"{emoji.wrong} Nao consegui criar o canal de atendimento. Verifique minhas permissoes.", ephemeral=True)
                return
            await self._safe_reply(inter, f"{emoji.correct} Atendimento criado: {channel.mention}", ephemeral=True)
            return

        if cid.startswith("Middleman_Terms:"):
            await self._send_components_reply(inter, self._terms_components(), ephemeral=True)
            return

        if cid.startswith("Middleman_Claim:") or cid.startswith("Middleman_Close:") or cid.startswith("Middleman_Cancel:"):
            action, case_id = cid.split(":", 1)
            cases = cfg.setdefault("cases", {})
            case = cases.get(case_id)
            if not case:
                await self._safe_reply(inter, f"{emoji.wrong} Atendimento nao encontrado.", ephemeral=True)
                return

            is_owner = str(case.get("user_id")) == str(inter.user.id)
            if action.endswith("Claim"):
                if not self._can_manage(inter, cfg):
                    await self._safe_reply(inter, f"{emoji.wrong} Apenas a equipe pode assumir o atendimento.", ephemeral=True)
                    return
                case["claimed_by"] = inter.user.id
                self._save_config(inter.guild.id, cfg)
                await self._safe_reply(inter, f"{emoji.correct} Atendimento assumido por {inter.user.mention}.", ephemeral=False)
                await self._log(inter.guild, cfg, f"Middleman `{case_id}` assumido por {inter.user.mention}.")
                return

            if not (is_owner or self._can_manage(inter, cfg)):
                await self._safe_reply(inter, f"{emoji.wrong} Apenas o cliente ou a equipe pode fechar este atendimento.", ephemeral=True)
                return
            case["status"] = "closed"
            case["closed_by"] = inter.user.id
            case["closed_at"] = disnake.utils.utcnow().isoformat()
            self._save_config(inter.guild.id, cfg)
            await self._send_components_reply(inter, self._closing_components(), ephemeral=False)
            await self._log(inter.guild, cfg, f"Middleman `{case_id}` fechado por {inter.user.mention}.")
            await self._close_case_channel(inter, case, case_id)
            return

    @commands.Cog.listener("on_dropdown")
    async def on_middleman_dropdown(self, inter: disnake.MessageInteraction):
        cid = getattr(inter.component, "custom_id", "") or ""
        if cid.startswith("Middleman_AddUserSelect:"):
            case_id = cid.split(":", 1)[1]
            if not await self._safe_defer(inter, ephemeral=True):
                return

            cfg = self._get_config(inter.guild.id)
            case = cfg.setdefault("cases", {}).get(case_id)
            if not case or case.get("status") != "open":
                await inter.followup.send(f"{emoji.wrong} Atendimento nao encontrado ou fechado.", ephemeral=True)
                return

            participants = {str(value) for value in case.get("participants", [])}
            allowed = (
                self._can_manage(inter, cfg)
                or str(case.get("user_id")) == str(inter.user.id)
                or str(inter.user.id) in participants
            )
            if not allowed:
                await inter.followup.send(f"{emoji.wrong} Voce nao pode adicionar usuarios neste middleman.", ephemeral=True)
                return

            channel_id = case.get("channel_id")
            channel = inter.guild.get_channel(int(channel_id)) if channel_id else inter.channel
            if not isinstance(channel, disnake.TextChannel):
                await inter.followup.send(f"{emoji.wrong} Canal do atendimento nao encontrado.", ephemeral=True)
                return

            added = []
            failed = []
            for selected in inter.values:
                member_id = getattr(selected, "id", selected)
                member = await self._resolve_member(inter.guild, member_id)
                if not member:
                    failed.append(str(member_id))
                    continue
                try:
                    text = await self._add_member_to_case(
                        guild=inter.guild,
                        channel=channel,
                        cfg=cfg,
                        case=case,
                        case_id=case_id,
                        member=member,
                        added_by=inter.user,
                    )
                    added.append(text)
                except disnake.HTTPException:
                    failed.append(str(member_id))

            response = "\n".join(added) if added else f"{emoji.wrong} Nenhum usuario foi adicionado."
            if failed:
                response += f"\n{emoji.warn} Nao consegui adicionar: `{', '.join(failed[:5])}`"
            await inter.followup.send(response, ephemeral=True)
            return

        if not cid.startswith("Middleman_Select"):
            return

        cfg = self._get_config(inter.guild.id)
        if not self._can_manage(inter, cfg):
            await inter.response.send_message(f"{emoji.wrong} Voce nao tem permissao para configurar o Middleman.", ephemeral=True)
            return

        if cid == "Middleman_SelectCategory":
            cfg["category_id"] = int(inter.values[0])
            text = f"Categoria definida para <#{inter.values[0]}>."
        elif cid == "Middleman_SelectLogs":
            cfg["logs_channel_id"] = int(inter.values[0])
            text = f"Canal de logs definido para <#{inter.values[0]}>."
        elif cid == "Middleman_SelectStaff":
            cfg["staff_roles"] = [int(value) for value in inter.values]
            text = "Equipe do Middleman atualizada."
        else:
            return

        self._save_config(inter.guild.id, cfg)
        await self._edit_admin_panel(inter, self.display_middleman_panel(inter))
        await inter.followup.send(f"{emoji.correct} {text}", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(MiddlemanPanel(bot))
