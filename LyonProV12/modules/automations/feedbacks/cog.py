import disnake
from disnake.ext import commands
from datetime import datetime, timedelta
from types import SimpleNamespace
from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from . import helpers

class FeedbackRewardModal(disnake.ui.Modal):
    def __init__(self):
        data = helpers.carregar_rewards()
        super().__init__(
            title="Recompensas de Feedback",
            custom_id="Feedbacks_RewardsModal",
            components=[
                disnake.ui.TextInput(label="Pontos por feedback", custom_id="points", value=str(data.get("points_per_feedback", 1)), max_length=6),
                disnake.ui.TextInput(label="Minimo de caracteres", custom_id="min_chars", value=str(data.get("min_chars", 8)), max_length=6),
                disnake.ui.TextInput(label="Bonus em saldo (opcional)", custom_id="saldo_bonus", value=str(data.get("saldo_bonus", 0)), required=False, max_length=10),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(with_message=False)
        data = helpers.carregar_rewards()
        try:
            data["points_per_feedback"] = max(0, int(inter.text_values.get("points", "1")))
            data["min_chars"] = max(1, int(inter.text_values.get("min_chars", "8")))
            data["saldo_bonus"] = max(0.0, float((inter.text_values.get("saldo_bonus") or "0").replace(",", ".")))
        except Exception:
            pass
        data["enabled"] = True
        helpers.salvar_rewards(data)
        mode = db.get_document("custom_mode").get("mode")
        if mode == "embed":
            embed, components = FeedbacksCog.PainelEmbed()
            await inter.edit_original_message(content=None, embed=embed, components=components)
        else:
            await inter.edit_original_message(components=FeedbacksCog.Painel())


class FeedbacksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @staticmethod
    def Painel() -> list[disnake.ui.Container]:
        config = helpers.carregar_config()
        rewards = helpers.carregar_rewards()
        ativado = config.get("ativado", False)
        
        canais_config = db.get_document("canais") or {}
        canal_feedback_id = canais_config.get("canal_de_feedback")

        canal_configurado = f"<#{canal_feedback_id}>" if canal_feedback_id else "Não configurado"

        resumo = (
            f"{emoji.on if ativado else emoji.off} **Status:** `{'Ativado' if ativado else 'Desativado'}`\n"
            f"{emoji.textc} **Canal de Feedbacks:** {canal_configurado}\n"
            f"{emoji.gift2} **Recompensas:** `{'Ativada' if rewards.get('enabled') else 'Desativada'}`\n"
            f"{emoji.coin} **Pontos por feedback:** `{rewards.get('points_per_feedback', 1)}`\n"
        )

        botoes_principais = [
            disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.power, custom_id="Feedbacks_ToggleAtivo"),
            disnake.ui.Button(label="Recompensas", style=disnake.ButtonStyle.grey, emoji=emoji.gift2, custom_id="Feedbacks_ConfigRewards"),
            disnake.ui.Button(label="Ranking", style=disnake.ButtonStyle.grey, emoji=emoji.trophy, custom_id="Feedbacks_RankingRewards"),
        ]
        
        primary_color_hex = db.get_document("custom_colors").get("primary")
        container_kwargs = {}
        if primary_color_hex:
            primary_color = int(primary_color_hex.replace("#", ""), 16)
            container_kwargs["accent_colour"] = disnake.Colour(primary_color)

        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Painel > Automações > **Feedbacks**"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("O bot irá monitorar feedbacks negativos no canal configurado e alertar a staff."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(resumo),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(*botoes_principais),
                **container_kwargs,
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="VoltarAutomações"),
            )
        ]

    @staticmethod
    def PainelEmbed() -> tuple[disnake.Embed, list[disnake.ui.ActionRow]]:
        config = helpers.carregar_config()
        rewards = helpers.carregar_rewards()
        ativado = config.get("ativado", False)
        
        canais_config = db.get_document("canais") or {}
        canal_feedback_id = canais_config.get("canal_de_feedback")

        canal_configurado = f"<#{canal_feedback_id}>" if canal_feedback_id else "Não configurado"

        resumo = (
            f"{emoji.on if ativado else emoji.off} **Status:** `{'Ativado' if ativado else 'Desativado'}`\n"
            f"{emoji.textc} **Canal de Feedbacks:** {canal_configurado}\n"
            f"{emoji.gift2} **Recompensas:** `{'Ativada' if rewards.get('enabled') else 'Desativada'}`\n"
            f"{emoji.coin} **Pontos por feedback:** `{rewards.get('points_per_feedback', 1)}`\n"
        )

        primary_color_hex = db.get_document("custom_colors").get("primary")
        embed = disnake.Embed(
            title=f"Feedbacks",
            description="O bot irá monitorar feedbacks negativos no canal configurado e alertar a staff."
        )
        if primary_color_hex:
            embed.color = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
        
        embed.add_field(name="Configurações", value=resumo, inline=False)

        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.power, custom_id="Feedbacks_ToggleAtivo"),
                disnake.ui.Button(label="Recompensas", style=disnake.ButtonStyle.grey, emoji=emoji.gift2, custom_id="Feedbacks_ConfigRewards"),
                disnake.ui.Button(label="Ranking", style=disnake.ButtonStyle.grey, emoji=emoji.trophy, custom_id="Feedbacks_RankingRewards"),
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="", style=disnake.ButtonStyle.grey, emoji=emoji.back, custom_id="VoltarAutomações"),
            )
        ]
        return embed, components

    @commands.Cog.listener("on_button_click")
    async def Feedback_Button_Listener(self, inter: disnake.MessageInteraction):
        custom_id = inter.component.custom_id
        if custom_id == "Feedbacks_ConfigRewards":
            await inter.response.send_modal(FeedbackRewardModal())
            return

        if custom_id == "Feedbacks_RankingRewards":
            await inter.response.defer(ephemeral=True)
            ranking = helpers.ranking_rewards(inter.guild.id if inter.guild else 0)
            text = "\n".join(
                f"`#{index}` <@{user_id}> - `{data.get('points', 0)}` pontos | `{data.get('feedbacks', 0)}` feedbacks"
                for index, (user_id, data) in enumerate(ranking, start=1)
            ) or "Nenhuma recompensa registrada ainda."
            await inter.followup.send(f"{emoji.trophy} **Ranking de Feedbacks**\n{text}", ephemeral=True)
            return

        if custom_id == "Feedbacks_ToggleAtivo":
            mode = db.get_document("custom_mode").get("mode")
            if mode == "embed":
                await embed_message.wait(inter, send=False)
            else:
                await message.wait(inter, send=False)
            
            config = helpers.carregar_config()
            config["ativado"] = not config.get("ativado", False)
            helpers.salvar_config(config)
            
            if mode == "embed":
                embed, components = self.PainelEmbed()
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await inter.edit_original_message(components=self.Painel())
        
        elif custom_id.startswith("feedback_"):
            await inter.response.defer()
            parts = custom_id.split(":")
            action = parts[0]
            original_message_id_str = parts[1]
            original_channel_id = int(parts[2])

            log = helpers.carregar_log()
            log_entry = log.get(original_message_id_str)
            mode = db.get_document("custom_mode").get("mode")

            if not log_entry:
                return 
            
            original_message_info = log_entry.get("original_message", {})

            mock_author = SimpleNamespace(id=original_message_info.get("author_id"), mention=original_message_info.get("author_mention"))
            mock_message = SimpleNamespace(
                id=int(original_message_id_str),
                content=original_message_info.get("content", "[Conteúdo não disponível]"),
                author=mock_author,
                jump_url=original_message_info.get("jump_url")
            )

            if log_entry.get("action_taken"):
                action_info = log_entry["action_taken"]
                action_type = action_info["type"]
                admin_id = action_info["admin_id"]
                try:
                    admin_user = await self.bot.fetch_user(admin_id)
                    if mode == "embed":
                        embed, components = helpers.criar_notificacao_embed_atualizada(mock_message, admin_user, action_type, original_channel_id)
                        await inter.edit_original_message(content=None, embed=embed, components=components)
                    else:
                        components = helpers.criar_notificacao_components_atualizada(mock_message, admin_user, action_type, original_channel_id)
                        await inter.edit_original_message(components=components)
                except disnake.NotFound:
                    if mode == "embed":
                        embed = disnake.Embed(description=f"{emoji.correct} Esta ação já foi tratada, mas o administrador que a realizou não foi encontrado.", color=disnake.Color.yellow())
                        await inter.edit_original_message(content=None, embed=embed, components=[])
                    else:
                        await inter.edit_original_message(components=[disnake.ui.Container(disnake.ui.TextDisplay(f"{emoji.correct} Esta ação já foi tratada, mas o administrador que a realizou não foi encontrado."))])
                return

            action_taken_successfully = False
            action_type = ""
            original_message = None

            if action == "feedback_delete":
                try:
                    original_channel = await self.bot.fetch_channel(original_channel_id)
                    original_message = await original_channel.fetch_message(int(original_message_id_str))
                    await original_message.delete()
                    action_taken_successfully = True
                    action_type = "deleted"
                except disnake.NotFound:
                    action_taken_successfully = True
                    action_type = "deletion_failed_not_found"
                except disnake.Forbidden:
                    action_taken_successfully = True
                    action_type = "deletion_failed_forbidden"

            elif action == "feedback_ignore":
                action_taken_successfully = True
                action_type = "ignored"

            if action_taken_successfully:
                
                log_entry["action_taken"] = {
                    "type": action_type,
                    "admin_id": inter.author.id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                helpers.salvar_log(log)
                
                message_to_update_with = original_message or mock_message

                notifications = log_entry.get("notifications", [])
                for notification in notifications:
                    try:
                        admin_user = await self.bot.fetch_user(notification["admin_id"])
                        dm_channel = await self.bot.fetch_channel(notification["dm_channel_id"])
                        dm_message = await dm_channel.fetch_message(notification["message_id"])

                        if notification["admin_id"] == inter.author.id:
                            # Use the interaction to edit the current user's message
                            if mode == "embed":
                                embed, components = helpers.criar_notificacao_embed_atualizada(message_to_update_with, inter.author, action_type, original_channel_id)
                                await inter.edit_original_message(content=None, embed=embed, components=components)
                            else:
                                components = helpers.criar_notificacao_components_atualizada(message_to_update_with, inter.author, action_type, original_channel_id)
                                await inter.edit_original_message(components=components)
                        else:
                            # Use regular edit for other admins' messages
                            if mode == "embed":
                                embed, components = helpers.criar_notificacao_embed_atualizada(message_to_update_with, inter.author, action_type, original_channel_id)
                                await dm_message.edit(content=None, embed=embed, components=components)
                            else:
                                components = helpers.criar_notificacao_components_atualizada(message_to_update_with, inter.author, action_type, original_channel_id)
                                await dm_message.edit(components=components)
                    except (disnake.NotFound, disnake.Forbidden):
                        print(f"Não foi possível atualizar a DM de feedback ID {notification.get('message_id')}")
                        continue
            
    async def _analisar_mensagem_feedback(self, message: disnake.Message):
        config = helpers.carregar_config()
        if not config.get("ativado", False) or message.author.bot:
            return

        canais_config = db.get_document("canais") or {}
        canal_feedback_id = canais_config.get("canal_de_feedback")
        
        if not canal_feedback_id or message.channel.id != int(canal_feedback_id):
            return

        await self._process_feedback_reward(message)
        
        try:
            instrucao = (
                "Tarefa: Classifique o feedback do usuário.\n"
                "Saída (formato OBRIGATÓRIO): responda EXATAMENTE com um destes rótulos: Positivo | Feedback Negativo | Alegação de Golpe | Alegação de Fraude | Neutro.\n"
                "Definições: Positivo (elogios), Feedback Negativo (reclamações), Alegação de Golpe (scam, não recebeu o que pagou), Alegação de Fraude (atividade criminosa mais ampla), Neutro (dúvidas, sugestões)."
            )
            prompt = f"{instrucao}\n\nMensagem do usuário: {message.content}\n\nResponda somente com um rótulo válido."
            classification = await helpers.chamar_ia(prompt, "Feedbacks")
            
            allowed = {"Positivo", "Feedback Negativo", "Alegação de Golpe", "Alegação de Fraude", "Neutro"}
            if classification not in allowed:
                return

            if classification in ["Feedback Negativo", "Alegação de Golpe", "Alegação de Fraude"]:
                await helpers.notificar_admins(self.bot, message, classification)

        except Exception as e:
            print(f"Erro ao analisar feedback: {e}")

    async def _process_feedback_reward(self, message: disnake.Message):
        try:
            awarded, _user_data = helpers.add_feedback_reward(
                guild_id=message.guild.id,
                user_id=message.author.id,
                message_id=message.id,
                content=message.content or "",
            )
            if not awarded:
                return
            rewards = helpers.carregar_rewards()
            saldo_bonus = float(rewards.get("saldo_bonus", 0) or 0)
            if saldo_bonus > 0:
                try:
                    from modules.loja.saldo.balance_manager import BalanceManager
                    BalanceManager.add_balance(
                        message.author.id,
                        saldo_bonus,
                        bonus=0,
                        deposit_id=f"feedback_{message.id}",
                        payment_method="feedback_reward",
                    )
                except Exception as exc:
                    print(f"[FeedbackRewards] Erro ao creditar saldo: {exc}")
            try:
                await message.add_reaction(emoji.correct)
            except Exception:
                pass
        except Exception as e:
            print(f"[FeedbackRewards] Erro ao registrar recompensa: {e}")

    @commands.Cog.listener("on_message")
    async def on_feedback_message(self, message: disnake.Message):
        await self._analisar_mensagem_feedback(message)

    @commands.Cog.listener("on_message_edit")
    async def on_feedback_message_edit(self, before: disnake.Message, after: disnake.Message):
        if (before.content or "").strip() == (after.content or "").strip():
            return
        await self._analisar_mensagem_feedback(after)

def setup(bot: commands.Bot):
    bot.add_cog(FeedbacksCog(bot))
