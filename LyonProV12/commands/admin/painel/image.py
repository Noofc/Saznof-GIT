import aiohttp
import io
import pathlib

import disnake


def get_panel_image_path() -> pathlib.Path:
    base_dir = pathlib.Path(__file__).resolve().parents[3]
    return base_dir / "database" / "emojis" / "assets" / "painellyonapplications.png"


async def load_panel_image_file() -> disnake.File | None:
    image_path = get_panel_image_path()

    if image_path.exists():
        return disnake.File(str(image_path), filename="painellyonapplications.png")

    image_url = "https://i.ibb.co/tw2k3MqB/Picsart-26-08-15-14-57-50-031.jpg"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return None
                image_buffer = io.BytesIO(await resp.read())
                image_buffer.seek(0)
                return disnake.File(image_buffer, filename="painellyonapplications.png")
    except Exception:
        return None
