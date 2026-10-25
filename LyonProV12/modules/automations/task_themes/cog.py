import disnake
from disnake.ext import commands

from functions.database import database as db
from functions.emoji import emoji
from functions.message import message, embed_message
from functions.utils import utils
from . import helpers


def _now() -> int:
    return int(disnake.utils.utcnow().timestamp())


def _colors_kwargs() -> dict:
    colors = db.get_document("custom_colors") or {}
    if colors.get("primary"):
        return {"accent_colour": disnake.Colour(int(colors["primary"].replace("#", ""), 16))}
    return {}


class ThemeModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(
            title="Criar tema de tasks",
            custom_id="TaskThemes_CreateThemeModal",
            components=[
                disnake.ui.TextInput(label="Nome do tema", custom_id="name", placeholder="Ex.: Marketing", max_length=80),
                disnake.ui.TextInput(
                    label="Descricao",
                    custom_id="description",
                    placeholder="Ex.: Posts, campanhas, parcerias e criativos",
                    required=False,
                    style=disnake.TextInputStyle.paragraph,
                    max_length=300,
                ),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(with_message=False)
        data = helpers.load_data()
        helpers.find_or_create_theme(
            data,
            inter.text_values.get("name"),
            inter.text_values.get("description", ""),
        )
        helpers.save_data(data)
        await inter.edit_original_message(components=TaskThemesCog.Painel(), flags=disnake.MessageFlags(is_components_v2=True))


class TaskModal(disnake.ui.Modal):
    def __init__(self):
        super().__init__(
            title="Criar task",
            custom_id="TaskThemes_CreateTaskModal",
            components=[
                disnake.ui.TextInput(label="Tema", custom_id="theme", placeholder="Ex.: Marketing", max_length=80),
                disnake.ui.TextInput(label="Titulo da task", custom_id="title", placeholder="Ex.: Criar campanha de restock", max_length=120),
                disnake.ui.TextInput(
                    label="Descricao",
                    custom_id="description",
                    placeholder="Detalhes, responsavel, link ou checklist rapido",
                    required=False,
                    style=disnake.TextInputStyle.paragraph,
                    max_length=900,
                ),
                disnake.ui.TextInput(label="Prazo", custom_id="due", placeholder="Ex.: 25/05 18:00", required=False, max_length=40),
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(with_message=False)
        data = helpers.load_data()
        theme = helpers.find_or_create_theme(data, inter.text_values.get("theme"))
        task_id = utils.gerar_id(8)
        theme.setdefault("tasks", {})[task_id] = {
            "id": task_id,
            "title": inter.text_values.get("title", "Task").strip()[:120],
            "description": inter.text_values.get("description", "").strip(),
            "due": inter.text_values.get("due", "").strip(),
            "done": False,
            "created_by": inter.author.id,
            "created_at": _now(),
        }
        helpers.save_data(data)
        await inter.edit_original_message(components=TaskThemesCog.Painel(), flags=disnake.MessageFlags(is_components_v2=True))


class TaskThemesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _summary() -> str:
        data = helpers.load_data()
        st = helpers.stats(data)
        lines = [
            f"{emoji.folder} **Temas:** `{st['themes']}`",
            f"{emoji.receipt} **Tasks:** `{st['tasks']}`",
            f"{emoji.clock} **Pendentes:** `{st['pending']}`",
            f"{emoji.correct} **Concluidas:** `{st['done']}`",
        ]

        for theme in list(data.get("themes", {}).values())[:6]:
            tasks = theme.get("tasks") or {}
            pending = sum(1 for task in tasks.values() if not task.get("done"))
            lines.append(f"- `{theme.get('name')}`: `{pending}` pendente(s)")
        return "\n".join(lines)

    @staticmethod
    def Painel() -> list[disnake.ui.Container]:
        return [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.receipt} Tasks por Temas\n-# Painel > Automacoes > **Tasks**"),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay("Organize tarefas internas por tema para staff, loja, marketing, comunidade e operacao."),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.TextDisplay(TaskThemesCog._summary()),
                disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                disnake.ui.ActionRow(
                    disnake.ui.Button(label="Criar Tema", style=disnake.ButtonStyle.blurple, emoji=emoji.folder, custom_id="TaskThemes_CreateTheme"),
                    disnake.ui.Button(label="Criar Task", style=disnake.ButtonStyle.green, emoji=emoji.plus, custom_id="TaskThemes_CreateTask"),
                    disnake.ui.Button(label="Ver Tasks", style=disnake.ButtonStyle.grey, emoji=emoji.search, custom_id="TaskThemes_ListTasks"),
                ),
                **_colors_kwargs(),
            ),
        ]

    @staticmethod
    def PainelEmbed() -> tuple[disnake.Embed, list[disnake.ui.ActionRow]]:
        embed = disnake.Embed(title="Tasks por Temas", description=TaskThemesCog._summary())
        colors = db.get_document("custom_colors") or {}
        if colors.get("primary"):
            embed.color = disnake.Colour(int(colors["primary"].replace("#", ""), 16))
        return embed, [
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.ActionRow(
                disnake.ui.Button(label="Criar Tema", style=disnake.ButtonStyle.blurple, emoji=emoji.folder, custom_id="TaskThemes_CreateTheme"),
                disnake.ui.Button(label="Criar Task", style=disnake.ButtonStyle.green, emoji=emoji.plus, custom_id="TaskThemes_CreateTask"),
                disnake.ui.Button(label="Ver Tasks", style=disnake.ButtonStyle.grey, emoji=emoji.search, custom_id="TaskThemes_ListTasks"),
            ),
        ]

    @staticmethod
    def ListPanel() -> list[disnake.ui.Container]:
        data = helpers.load_data()
        pairs = helpers.all_tasks(data)
        options = []
        lines = []
        for theme, task in pairs[:25]:
            done = bool(task.get("done"))
            prefix = "OK" if done else "Pendente"
            title = task.get("title", "Task")
            lines.append(f"- `{prefix}` **{theme.get('name')}**: {title}")
            options.append(
                disnake.SelectOption(
                    label=title[:80],
                    value=f"{theme.get('id')}:{task.get('id')}",
                    description=f"{theme.get('name')} | {'concluida' if done else 'pendente'}"[:100],
                    emoji=emoji.correct if done else emoji.clock,
                )
            )

        content = "\n".join(lines) if lines else "Nenhuma task criada ainda."
        children = [
            disnake.ui.TextDisplay(f"# {emoji.search} Tasks"),
            disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
            disnake.ui.TextDisplay(content[:1900]),
        ]
        if options:
            children.extend(
                [
                    disnake.ui.Separator(spacing=disnake.SeparatorSpacing.small),
                    disnake.ui.ActionRow(
                        disnake.ui.StringSelect(
                            custom_id="TaskThemes_SelectTask",
                            placeholder="Selecione uma task para alternar concluida/pendente",
                            options=options,
                        )
                    ),
                ]
            )
        return [
            disnake.ui.Container(*children, **_colors_kwargs()),
        ]

    @commands.Cog.listener("on_button_click")
    async def on_task_theme_button(self, inter: disnake.MessageInteraction):
        cid = inter.component.custom_id
        if not cid.startswith("TaskThemes_"):
            return

        if cid == "TaskThemes_CreateTheme":
            await inter.response.send_modal(ThemeModal())
            return
        if cid == "TaskThemes_CreateTask":
            await inter.response.send_modal(TaskModal())
            return

        mode = (db.get_document("custom_mode") or {}).get("mode", "components")
        if mode == "embed":
            await embed_message.wait(inter, send=False)
        else:
            await message.wait(inter, send=False)

        if cid == "TaskThemes_ListTasks":
            await inter.edit_original_message(components=self.ListPanel(), flags=disnake.MessageFlags(is_components_v2=True))
        elif cid == "TaskThemes_Back":
            if mode == "embed":
                embed, components = self.PainelEmbed()
                await inter.edit_original_message(content=None, embed=embed, components=components)
            else:
                await inter.edit_original_message(components=self.Painel(), flags=disnake.MessageFlags(is_components_v2=True))

    @commands.Cog.listener("on_dropdown")
    async def on_task_theme_dropdown(self, inter: disnake.MessageInteraction):
        if inter.component.custom_id != "TaskThemes_SelectTask":
            return
        await inter.response.defer(with_message=False)
        value = inter.values[0]
        theme_id, task_id = value.split(":", 1)
        data = helpers.load_data()
        task = ((data.get("themes", {}).get(theme_id) or {}).get("tasks") or {}).get(task_id)
        if task:
            task["done"] = not bool(task.get("done"))
            task["updated_at"] = _now()
            task["updated_by"] = inter.author.id
            helpers.save_data(data)
        await inter.edit_original_message(components=self.ListPanel(), flags=disnake.MessageFlags(is_components_v2=True))
