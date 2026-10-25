"""
Sistema de personalização de QR Code
"""
import disnake
from disnake.ext import commands
from functions.database import database as db
from functions.emoji import emoji
import aiohttp
import io
import json
from pathlib import Path
from urllib.parse import quote

try:
    from PIL import Image, ImageDraw, ImageChops
except Exception:
    Image = None
    ImageDraw = None
    ImageChops = None


DEFAULT_QR_LOGO_URL = (
    "https://cdn.discordapp.com/attachments/1477680025557012563/"
    "1508533045341327380/Sem_Titulo-2q.png?"
    "ex=6a19d6e1&is=6a188561&hm=2805733634c520b6247bf2b99c6be500050a5a4db1a4e8d21e37b5c2307a2f3a"
)
DEFAULT_QR_LOGO_PATH = Path(__file__).resolve().parents[3] / "assets" / "qr" / "default_qr_logo.png"
DEFAULT_QR_CONFIG = {
    "enabled": True,
    "color": "#000000",
    "background_color": "#FFFFFF",
    "logo_url": "",
    "logo_size": 0.12,
    "corner_style": "square",
}
MAX_PAYMENT_LOGO_RATIO = 0.12


def get_qr_config() -> dict:
    raw = db.get_document("loja_qr_customization")
    raw = raw if isinstance(raw, dict) else {}
    config = DEFAULT_QR_CONFIG.copy()
    for key in ("color", "background_color", "logo_url", "logo_size", "corner_style"):
        if key in raw and raw.get(key) is not None:
            config[key] = raw.get(key)
    config["enabled"] = raw.get("enabled", DEFAULT_QR_CONFIG["enabled"])
    config["logo_url"] = str(config.get("logo_url") or "").strip()
    try:
        config["logo_size"] = min(max(float(config.get("logo_size", DEFAULT_QR_CONFIG["logo_size"])), 0.05), 0.18)
    except Exception:
        config["logo_size"] = DEFAULT_QR_CONFIG["logo_size"]
    config["uses_default_logo"] = not bool(config["logo_url"])
    config["effective_logo_url"] = config["logo_url"] or DEFAULT_QR_LOGO_URL
    return config


class QRCustomizationModal(disnake.ui.Modal):
    def __init__(self):
        data = get_qr_config()
        
        components = [
            disnake.ui.TextInput(
                label="Cor do QR Code (Hex)",
                custom_id="color",
                value=data.get("color", "#000000"),
                placeholder="Ex: #000000 para preto",
                max_length=7,
                required=True
            ),
            disnake.ui.TextInput(
                label="Cor de Fundo (Hex)",
                custom_id="background_color",
                value=data.get("background_color", "#FFFFFF"),
                placeholder="Ex: #FFFFFF para branco",
                max_length=7,
                required=True
            ),
            disnake.ui.TextInput(
                label="URL do Logo (opcional)",
                custom_id="logo_url",
                value=data.get("logo_url", ""),
                placeholder="Vazio = logo padrao Lyon Pro",
                required=False
            ),
            disnake.ui.TextInput(
                label="Tamanho do Logo (0.05 a 0.18)",
                custom_id="logo_size",
                value=str(data.get("logo_size", 0.12)),
                placeholder="0.12 = recomendado para pagamento",
                max_length=4,
                required=False
            ),
            disnake.ui.TextInput(
                label="Estilo dos Cantos",
                custom_id="corner_style",
                value=data.get("corner_style", "square"),
                placeholder="square, rounded ou dots",
                max_length=10,
                required=True
            )
        ]
        
        super().__init__(title="Personalizar QR Code", components=components)
    
    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer()
        
        # Validar cores hex
        color = inter.text_values["color"]
        bg_color = inter.text_values["background_color"]
        
        if not color.startswith("#") or len(color) != 7:
            await inter.followup.send(
                f"{emoji.wrong} Cor do QR inválida! Use formato hex: #000000",
                ephemeral=True
            )
            return
        
        if not bg_color.startswith("#") or len(bg_color) != 7:
            await inter.followup.send(
                f"{emoji.wrong} Cor de fundo inválida! Use formato hex: #FFFFFF",
                ephemeral=True
            )
            return
        
        # Validar tamanho do logo
        try:
            logo_size = float(inter.text_values.get("logo_size", 0.12))
            if logo_size < 0.05 or logo_size > 0.18:
                raise ValueError
        except ValueError:
            await inter.followup.send(
                f"{emoji.wrong} Tamanho do logo invalido! Use valores entre 0.05 e 0.18 para manter o QR legivel.",
                ephemeral=True
            )
            return
        
        # Validar estilo dos cantos
        corner_style = inter.text_values["corner_style"].lower()
        if corner_style not in ["square", "rounded", "dots"]:
            await inter.followup.send(
                f"{emoji.wrong} Estilo de cantos inválido! Use: square, rounded ou dots",
                ephemeral=True
            )
            return
        
        # Salvar configurações
        data = db.get_document("loja_qr_customization")
        data["color"] = color
        data["background_color"] = bg_color
        data["logo_url"] = (inter.text_values.get("logo_url") or "").strip()
        data["logo_size"] = logo_size
        data["corner_style"] = corner_style
        data["enabled"] = True
        
        db.save_document("loja_qr_customization", data)
        
        # Gerar preview
        await inter.followup.send(
            f"{emoji.correct} Personalização de QR Code salva com sucesso!\n"
            f"As novas configurações serão aplicadas aos próximos QR Codes gerados.",
            ephemeral=True
        )


class QRCodeGenerator:
    """Gerador de QR Code personalizado"""

    @staticmethod
    def get_config() -> dict:
        return get_qr_config()

    @staticmethod
    def is_enabled() -> bool:
        return bool(get_qr_config().get("enabled", True))

    @staticmethod
    def _read_file_bytes(path: Path) -> bytes | None:
        try:
            if path.exists() and path.is_file():
                return path.read_bytes()
        except Exception:
            pass
        return None

    @staticmethod
    async def _download_logo(url: str) -> bytes | None:
        if not url or not url.lower().startswith(("http://", "https://")):
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception as exc:
            print(f"[QRCode] Nao consegui baixar logo personalizada: {exc}")
        return None

    @staticmethod
    async def _prepare_config(config: dict | None = None) -> dict:
        prepared = get_qr_config()
        if isinstance(config, dict):
            prepared.update({k: v for k, v in config.items() if v is not None})

        logo_bytes = None
        logo_url = str(prepared.get("logo_url") or "").strip()
        if logo_url:
            if logo_url.lower().startswith(("http://", "https://")):
                logo_bytes = await QRCodeGenerator._download_logo(logo_url)
            else:
                logo_bytes = QRCodeGenerator._read_file_bytes(Path(logo_url))

        if not logo_bytes:
            logo_bytes = QRCodeGenerator._read_file_bytes(DEFAULT_QR_LOGO_PATH)

        prepared["_logo_bytes"] = logo_bytes
        prepared["uses_default_logo"] = not bool(logo_url)
        prepared["effective_logo_url"] = logo_url or DEFAULT_QR_LOGO_URL
        return prepared

    @staticmethod
    def _trim_logo(logo):
        if ImageChops is None:
            return logo
        try:
            rgb = logo.convert("RGB")
            bg = Image.new("RGB", rgb.size, (255, 255, 255))
            diff = ImageChops.difference(rgb, bg)
            bbox = diff.getbbox()
            if bbox:
                pad = max(min(logo.size) // 40, 6)
                left = max(bbox[0] - pad, 0)
                top = max(bbox[1] - pad, 0)
                right = min(bbox[2] + pad, logo.size[0])
                bottom = min(bbox[3] + pad, logo.size[1])
                return logo.crop((left, top, right, bottom))
        except Exception:
            pass
        return logo

    @staticmethod
    def _paste_logo(image, config: dict):
        logo_bytes = config.get("_logo_bytes")
        if not logo_bytes:
            return image

        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            logo = QRCodeGenerator._trim_logo(logo)
            max_ratio = min(max(float(config.get("logo_size", 0.22)), 0.1), 0.36)
            max_side = max(24, int(image.size[0] * max_ratio))
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            logo.thumbnail((max_side, max_side), resample)

            padding = max(8, int(max_side * 0.16))
            box_w = logo.size[0] + padding * 2
            box_h = logo.size[1] + padding * 2
            x = (image.size[0] - box_w) // 2
            y = (image.size[1] - box_h) // 2

            draw = ImageDraw.Draw(image)
            try:
                draw.rounded_rectangle(
                    [x, y, x + box_w, y + box_h],
                    radius=max(8, padding),
                    fill=QRCodeGenerator._hex_color(config.get("background_color"), "#FFFFFF"),
                )
            except Exception:
                draw.rectangle(
                    [x, y, x + box_w, y + box_h],
                    fill=QRCodeGenerator._hex_color(config.get("background_color"), "#FFFFFF"),
                )

            image.paste(logo, (x + padding, y + padding), logo)
        except Exception as exc:
            print(f"[QRCode] Nao consegui aplicar logo no QR: {exc}")
        return image

    _EC_FORMAT_BITS = {"M": 0, "L": 1, "H": 2, "Q": 3}
    _RS_BLOCK_OFFSET = {"L": 0, "M": 1, "Q": 2, "H": 3}
    _RS_BLOCK_TABLE = (
        (1, 26, 19), (1, 26, 16), (1, 26, 13), (1, 26, 9),
        (1, 44, 34), (1, 44, 28), (1, 44, 22), (1, 44, 16),
        (1, 70, 55), (1, 70, 44), (2, 35, 17), (2, 35, 13),
        (1, 100, 80), (2, 50, 32), (2, 50, 24), (4, 25, 9),
        (1, 134, 108), (2, 67, 43), (2, 33, 15, 2, 34, 16), (2, 33, 11, 2, 34, 12),
        (2, 86, 68), (4, 43, 27), (4, 43, 19), (4, 43, 15),
        (2, 98, 78), (4, 49, 31), (2, 32, 14, 4, 33, 15), (4, 39, 13, 1, 40, 14),
        (2, 121, 97), (2, 60, 38, 2, 61, 39), (4, 40, 18, 2, 41, 19), (4, 40, 14, 2, 41, 15),
        (2, 146, 116), (3, 58, 36, 2, 59, 37), (4, 36, 16, 4, 37, 17), (4, 36, 12, 4, 37, 13),
        (2, 86, 68, 2, 87, 69), (4, 69, 43, 1, 70, 44), (6, 43, 19, 2, 44, 20), (6, 43, 15, 2, 44, 16),
        (4, 101, 81), (1, 80, 50, 4, 81, 51), (4, 50, 22, 4, 51, 23), (3, 36, 12, 8, 37, 13),
        (2, 116, 92, 2, 117, 93), (6, 58, 36, 2, 59, 37), (4, 46, 20, 6, 47, 21), (7, 42, 14, 4, 43, 15),
        (4, 133, 107), (8, 59, 37, 1, 60, 38), (8, 44, 20, 4, 45, 21), (12, 33, 11, 4, 34, 12),
        (3, 145, 115, 1, 146, 116), (4, 64, 40, 5, 65, 41), (11, 36, 16, 5, 37, 17), (11, 36, 12, 5, 37, 13),
        (5, 109, 87, 1, 110, 88), (5, 65, 41, 5, 66, 42), (5, 54, 24, 7, 55, 25), (11, 36, 12, 7, 37, 13),
        (5, 122, 98, 1, 123, 99), (7, 73, 45, 3, 74, 46), (15, 43, 19, 2, 44, 20), (3, 45, 15, 13, 46, 16),
        (1, 135, 107, 5, 136, 108), (10, 74, 46, 1, 75, 47), (1, 50, 22, 15, 51, 23), (2, 42, 14, 17, 43, 15),
        (5, 150, 120, 1, 151, 121), (9, 69, 43, 4, 70, 44), (17, 50, 22, 1, 51, 23), (2, 42, 14, 19, 43, 15),
        (3, 141, 113, 4, 142, 114), (3, 70, 44, 11, 71, 45), (17, 47, 21, 4, 48, 22), (9, 39, 13, 16, 40, 14),
        (3, 135, 107, 5, 136, 108), (3, 67, 41, 13, 68, 42), (15, 54, 24, 5, 55, 25), (15, 43, 15, 10, 44, 16),
        (4, 144, 116, 4, 145, 117), (17, 68, 42), (17, 50, 22, 6, 51, 23), (19, 46, 16, 6, 47, 17),
        (2, 139, 111, 7, 140, 112), (17, 74, 46), (7, 54, 24, 16, 55, 25), (34, 37, 13),
        (4, 151, 121, 5, 152, 122), (4, 75, 47, 14, 76, 48), (11, 54, 24, 14, 55, 25), (16, 45, 15, 14, 46, 16),
        (6, 147, 117, 4, 148, 118), (6, 73, 45, 14, 74, 46), (11, 54, 24, 16, 55, 25), (30, 46, 16, 2, 47, 17),
        (8, 132, 106, 4, 133, 107), (8, 75, 47, 13, 76, 48), (7, 54, 24, 22, 55, 25), (22, 45, 15, 13, 46, 16),
        (10, 142, 114, 2, 143, 115), (19, 74, 46, 4, 75, 47), (28, 50, 22, 6, 51, 23), (33, 46, 16, 4, 47, 17),
        (8, 152, 122, 4, 153, 123), (22, 73, 45, 3, 74, 46), (8, 53, 23, 26, 54, 24), (12, 45, 15, 28, 46, 16),
        (3, 147, 117, 10, 148, 118), (3, 73, 45, 23, 74, 46), (4, 54, 24, 31, 55, 25), (11, 45, 15, 31, 46, 16),
        (7, 146, 116, 7, 147, 117), (21, 73, 45, 7, 74, 46), (1, 53, 23, 37, 54, 24), (19, 45, 15, 26, 46, 16),
        (5, 145, 115, 10, 146, 116), (19, 75, 47, 10, 76, 48), (15, 54, 24, 25, 55, 25), (23, 45, 15, 25, 46, 16),
        (13, 145, 115, 3, 146, 116), (2, 74, 46, 29, 75, 47), (42, 54, 24, 1, 55, 25), (23, 45, 15, 28, 46, 16),
        (17, 145, 115), (10, 74, 46, 23, 75, 47), (10, 54, 24, 35, 55, 25), (19, 45, 15, 35, 46, 16),
        (17, 145, 115, 1, 146, 116), (14, 74, 46, 21, 75, 47), (29, 54, 24, 19, 55, 25), (11, 45, 15, 46, 46, 16),
        (13, 145, 115, 6, 146, 116), (14, 74, 46, 23, 75, 47), (44, 54, 24, 7, 55, 25), (59, 46, 16, 1, 47, 17),
        (12, 151, 121, 7, 152, 122), (12, 75, 47, 26, 76, 48), (39, 54, 24, 14, 55, 25), (22, 45, 15, 41, 46, 16),
        (6, 151, 121, 14, 152, 122), (6, 75, 47, 34, 76, 48), (46, 54, 24, 10, 55, 25), (2, 45, 15, 64, 46, 16),
        (17, 152, 122, 4, 153, 123), (29, 74, 46, 14, 75, 47), (49, 54, 24, 10, 55, 25), (24, 45, 15, 46, 46, 16),
        (4, 152, 122, 18, 153, 123), (13, 74, 46, 32, 75, 47), (48, 54, 24, 14, 55, 25), (42, 45, 15, 32, 46, 16),
        (20, 147, 117, 4, 148, 118), (40, 75, 47, 7, 76, 48), (43, 54, 24, 22, 55, 25), (10, 45, 15, 67, 46, 16),
        (19, 148, 118, 6, 149, 119), (18, 75, 47, 31, 76, 48), (34, 54, 24, 34, 55, 25), (20, 45, 15, 61, 46, 16),
    )
    _QR_ALIGN = {
        1: [],
        2: [6, 18],
        3: [6, 22],
        4: [6, 26],
        5: [6, 30],
        6: [6, 34],
        7: [6, 22, 38],
        8: [6, 24, 42],
        9: [6, 26, 46],
        10: [6, 28, 50],
        11: [6, 30, 54],
        12: [6, 32, 58],
        13: [6, 34, 62],
        14: [6, 26, 46, 66],
        15: [6, 26, 48, 70],
        16: [6, 26, 50, 74],
        17: [6, 30, 54, 78],
        18: [6, 30, 56, 82],
        19: [6, 30, 58, 86],
        20: [6, 34, 62, 90],
        21: [6, 28, 50, 72, 94],
        22: [6, 26, 50, 74, 98],
        23: [6, 30, 54, 78, 102],
        24: [6, 28, 54, 80, 106],
        25: [6, 32, 58, 84, 110],
        26: [6, 30, 58, 86, 114],
        27: [6, 34, 62, 90, 118],
        28: [6, 26, 50, 74, 98, 122],
        29: [6, 30, 54, 78, 102, 126],
        30: [6, 26, 52, 78, 104, 130],
        31: [6, 30, 56, 82, 108, 134],
        32: [6, 34, 60, 86, 112, 138],
        33: [6, 30, 58, 86, 114, 142],
        34: [6, 34, 62, 90, 118, 146],
        35: [6, 30, 54, 78, 102, 126, 150],
        36: [6, 24, 50, 76, 102, 128, 154],
        37: [6, 28, 54, 80, 106, 132, 158],
        38: [6, 32, 58, 84, 110, 136, 162],
        39: [6, 26, 54, 82, 110, 138, 166],
        40: [6, 30, 58, 86, 114, 142, 170],
    }

    @staticmethod
    def _hex_color(value: str, fallback: str) -> str:
        value = str(value or "").strip()
        if len(value) == 7 and value.startswith("#"):
            try:
                int(value[1:], 16)
                return value
            except Exception:
                pass
        return fallback

    @staticmethod
    def _gf_tables():
        exp = [0] * 512
        log = [0] * 256
        x = 1
        for i in range(255):
            exp[i] = x
            log[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11D
        for i in range(255, 512):
            exp[i] = exp[i - 255]
        return exp, log

    @staticmethod
    def _gf_mul(x: int, y: int, exp: list[int], log: list[int]) -> int:
        if x == 0 or y == 0:
            return 0
        return exp[log[x] + log[y]]

    @staticmethod
    def _rs_generator(degree: int, exp: list[int], log: list[int]) -> list[int]:
        poly = [1]
        for i in range(degree):
            nxt = [0] * (len(poly) + 1)
            for j, coef in enumerate(poly):
                nxt[j] ^= coef
                nxt[j + 1] ^= QRCodeGenerator._gf_mul(coef, exp[i], exp, log)
            poly = nxt
        return poly

    @staticmethod
    def _rs_remainder(data: list[int], degree: int, exp: list[int], log: list[int]) -> list[int]:
        gen = QRCodeGenerator._rs_generator(degree, exp, log)
        result = [0] * degree
        for value in data:
            factor = value ^ result[0]
            result = result[1:] + [0]
            for i in range(degree):
                result[i] ^= QRCodeGenerator._gf_mul(gen[i + 1], factor, exp, log)
        return result

    @staticmethod
    def _bch(value: int, poly: int, shift: int) -> int:
        result = value << shift
        while result.bit_length() >= poly.bit_length():
            result ^= poly << (result.bit_length() - poly.bit_length())
        return (value << shift) | result

    @staticmethod
    def _mask(mask: int, row: int, col: int) -> bool:
        if mask == 0:
            return (row + col) % 2 == 0
        if mask == 1:
            return row % 2 == 0
        if mask == 2:
            return col % 3 == 0
        if mask == 3:
            return (row + col) % 3 == 0
        if mask == 4:
            return (row // 2 + col // 3) % 2 == 0
        if mask == 5:
            return (row * col) % 2 + (row * col) % 3 == 0
        if mask == 6:
            return ((row * col) % 2 + (row * col) % 3) % 2 == 0
        return ((row + col) % 2 + (row * col) % 3) % 2 == 0

    @staticmethod
    def _penalty(matrix: list[list[bool]]) -> int:
        size = len(matrix)
        score = 0
        lines = matrix + [[matrix[r][c] for r in range(size)] for c in range(size)]
        for line in lines:
            run_color = line[0]
            run_len = 1
            for value in line[1:]:
                if value == run_color:
                    run_len += 1
                else:
                    if run_len >= 5:
                        score += 3 + run_len - 5
                    run_color = value
                    run_len = 1
            if run_len >= 5:
                score += 3 + run_len - 5
        for r in range(size - 1):
            for c in range(size - 1):
                color = matrix[r][c]
                if matrix[r][c + 1] == color and matrix[r + 1][c] == color and matrix[r + 1][c + 1] == color:
                    score += 3
        patterns = ([1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1])
        for line in lines:
            ints = [1 if v else 0 for v in line]
            for i in range(len(ints) - 10):
                if ints[i:i + 11] in patterns:
                    score += 40
        dark = sum(1 for row in matrix for value in row if value)
        percent = dark * 100 // (size * size)
        score += abs(percent - 50) // 5 * 10
        return score

    @staticmethod
    def _block_groups(version: int, ecc_level: str) -> list[tuple[int, int, int]] | None:
        ecc_level = str(ecc_level or "M").upper()
        offset = QRCodeGenerator._RS_BLOCK_OFFSET.get(ecc_level)
        if offset is None:
            offset = QRCodeGenerator._RS_BLOCK_OFFSET["M"]

        index = (version - 1) * 4 + offset
        if index < 0 or index >= len(QRCodeGenerator._RS_BLOCK_TABLE):
            return None

        raw_groups = QRCodeGenerator._RS_BLOCK_TABLE[index]
        groups: list[tuple[int, int, int]] = []
        for i in range(0, len(raw_groups), 3):
            count, total_len, data_len = raw_groups[i:i + 3]
            groups.append((count, data_len, total_len - data_len))
        return groups

    @staticmethod
    def _generate_local_qr(data: str, config: dict | None = None) -> bytes | None:
        if Image is None or ImageDraw is None:
            return None

        config = config or {}
        ecc_level = str(config.get("_ecc_level") or "M").upper()
        if ecc_level not in QRCodeGenerator._EC_FORMAT_BITS:
            ecc_level = "M"

        raw = str(data).encode("utf-8")
        version = None
        block_groups = None
        for candidate in range(1, 41):
            groups = QRCodeGenerator._block_groups(candidate, ecc_level)
            if not groups:
                continue
            capacity = sum(count * data_len for count, data_len, _ in groups)
            length_bits = 8 if candidate <= 9 else 16
            required_bits = 4 + length_bits + len(raw) * 8
            if required_bits <= capacity * 8:
                version = candidate
                block_groups = groups
                break
        if version is None or block_groups is None:
            return None

        capacity = sum(count * data_len for count, data_len, _ in block_groups)
        bits: list[int] = []

        def append(value: int, length: int):
            for i in range(length - 1, -1, -1):
                bits.append((value >> i) & 1)

        append(0b0100, 4)
        append(len(raw), 8 if version <= 9 else 16)
        for byte in raw:
            append(byte, 8)
        append(0, min(4, capacity * 8 - len(bits)))
        while len(bits) % 8:
            bits.append(0)

        data_codewords = []
        for i in range(0, len(bits), 8):
            value = 0
            for bit in bits[i:i + 8]:
                value = (value << 1) | bit
            data_codewords.append(value)
        for pad in [0xEC, 0x11] * capacity:
            if len(data_codewords) >= capacity:
                break
            data_codewords.append(pad)

        exp, log = QRCodeGenerator._gf_tables()
        blocks = []
        index = 0
        for count, data_len, ecc_len in block_groups:
            for _ in range(count):
                block = data_codewords[index:index + data_len]
                index += data_len
                blocks.append((block, QRCodeGenerator._rs_remainder(block, ecc_len, exp, log)))

        codewords: list[int] = []
        for i in range(max(len(block) for block, _ in blocks)):
            for block, _ in blocks:
                if i < len(block):
                    codewords.append(block[i])
        for i in range(max(len(ecc) for _, ecc in blocks)):
            for _, ecc in blocks:
                if i < len(ecc):
                    codewords.append(ecc[i])

        data_bits = []
        for byte in codewords:
            for i in range(7, -1, -1):
                data_bits.append((byte >> i) & 1)

        size = 21 + 4 * (version - 1)
        matrix: list[list[bool | None]] = [[None] * size for _ in range(size)]
        reserved = [[False] * size for _ in range(size)]

        def set_module(row: int, col: int, value: bool, reserve: bool = True):
            if 0 <= row < size and 0 <= col < size:
                matrix[row][col] = value
                if reserve:
                    reserved[row][col] = True

        def add_finder(row: int, col: int):
            for dr in range(-1, 8):
                for dc in range(-1, 8):
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < size and 0 <= cc < size:
                        value = 0 <= dr <= 6 and 0 <= dc <= 6 and (
                            dr in {0, 6} or dc in {0, 6} or (2 <= dr <= 4 and 2 <= dc <= 4)
                        )
                        set_module(rr, cc, value)

        add_finder(0, 0)
        add_finder(0, size - 7)
        add_finder(size - 7, 0)

        for i in range(8, size - 8):
            value = i % 2 == 0
            set_module(6, i, value)
            set_module(i, 6, value)

        for row in QRCodeGenerator._QR_ALIGN[version]:
            for col in QRCodeGenerator._QR_ALIGN[version]:
                if (row <= 8 and col <= 8) or (row <= 8 and col >= size - 9) or (row >= size - 9 and col <= 8):
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        set_module(row + dr, col + dc, max(abs(dr), abs(dc)) in {0, 2})

        set_module(4 * version + 9, 8, True)
        for i in range(9):
            set_module(8, i, False)
            set_module(i, 8, False)
        for i in range(size - 8, size):
            set_module(8, i, False)
            set_module(i, 8, False)
        if version >= 7:
            for i in range(18):
                row = i // 3
                col = size - 11 + i % 3
                set_module(row, col, False)
                set_module(col, row, False)

        bit_index = 0
        row = size - 1
        direction = -1
        col = size - 1
        while col > 0:
            if col == 6:
                col -= 1
            while True:
                for dc in (0, 1):
                    cc = col - dc
                    if not reserved[row][cc]:
                        matrix[row][cc] = bool(data_bits[bit_index]) if bit_index < len(data_bits) else False
                        bit_index += 1
                row += direction
                if row < 0 or row >= size:
                    row -= direction
                    direction = -direction
                    break
            col -= 2

        def add_format(target: list[list[bool]], mask: int):
            ec_bits = QRCodeGenerator._EC_FORMAT_BITS[ecc_level]
            fmt = QRCodeGenerator._bch((ec_bits << 3) | mask, 0x537, 10) ^ 0x5412
            for i in range(15):
                bit = bool((fmt >> i) & 1)
                if i < 6:
                    target[i][8] = bit
                elif i < 8:
                    target[i + 1][8] = bit
                else:
                    target[size - 15 + i][8] = bit

                if i < 8:
                    target[8][size - i - 1] = bit
                elif i == 8:
                    target[8][7] = bit
                else:
                    target[8][14 - i] = bit
            target[size - 8][8] = True

        def add_version(target: list[list[bool]]):
            if version < 7:
                return
            ver = QRCodeGenerator._bch(version, 0x1F25, 12)
            for i in range(18):
                bit = bool((ver >> i) & 1)
                row_a = i // 3
                col_a = size - 11 + i % 3
                target[row_a][col_a] = bit
                target[col_a][row_a] = bit

        best = None
        best_score = None
        for mask in range(8):
            candidate = [[bool(value) for value in row_values] for row_values in matrix]
            for r in range(size):
                for c in range(size):
                    if not reserved[r][c] and QRCodeGenerator._mask(mask, r, c):
                        candidate[r][c] = not candidate[r][c]
            add_format(candidate, mask)
            add_version(candidate)
            score = QRCodeGenerator._penalty(candidate)
            if best_score is None or score < best_score:
                best_score = score
                best = candidate

        if best is None:
            return None

        fg = QRCodeGenerator._hex_color(config.get("color"), "#000000")
        bg = QRCodeGenerator._hex_color(config.get("background_color"), "#FFFFFF")
        scale = 10
        border = 4
        img_size = (size + border * 2) * scale
        image = Image.new("RGB", (img_size, img_size), bg)
        draw = ImageDraw.Draw(image)
        corner_style = str(config.get("corner_style") or "square").lower()
        for r in range(size):
            for c in range(size):
                if best[r][c]:
                    x0 = (c + border) * scale
                    y0 = (r + border) * scale
                    if corner_style == "dots":
                        draw.ellipse([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=fg)
                    elif corner_style == "rounded":
                        try:
                            draw.rounded_rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], radius=scale // 3, fill=fg)
                        except Exception:
                            draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=fg)
                    else:
                        draw.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=fg)
        image = QRCodeGenerator._paste_logo(image, config)
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    
    @staticmethod
    async def generate_custom_qr(data: str) -> bytes:
        """
        Gera um QR Code personalizado usando a API qrcode-monkey
        """
        config = await QRCodeGenerator._prepare_config()

        if not config.get("enabled"):
            # Se não estiver habilitado, usar QR simples
            return await QRCodeGenerator.generate_simple_qr(data)

        # QR de pagamento precisa ser lido antes de ser bonito. Usamos correcao
        # alta quando couber, limitamos a logo e removemos a logo em payloads
        # grandes para evitar falha no app do banco.
        safe_config = config.copy()
        safe_config["corner_style"] = "square"
        safe_config["logo_size"] = min(
            max(float(safe_config.get("logo_size") or DEFAULT_QR_CONFIG["logo_size"]), 0.05),
            MAX_PAYMENT_LOGO_RATIO,
        )

        attempts = []
        if safe_config.get("_logo_bytes"):
            attempts.extend(("H", "Q", "M"))
        attempts.extend(("M_NO_LOGO", "L_NO_LOGO"))

        for attempt in attempts:
            local_config = safe_config.copy()
            if attempt.endswith("_NO_LOGO"):
                local_config["_ecc_level"] = attempt.split("_", 1)[0]
                local_config["_logo_bytes"] = None
            else:
                local_config["_ecc_level"] = attempt

            local_qr = QRCodeGenerator._generate_local_qr(data, local_config)
            if local_qr:
                return local_qr
        
        # Preparar configurações para a API
        qr_config = {
            "data": data,
            "config": {
                "body": "square",
                "eye": "frame0",
                "eyeBall": "ball0",
                "erf1": [],
                "erf2": [],
                "erf3": [],
                "brf1": [],
                "brf2": [],
                "brf3": [],
                "bodyColor": config.get("color", "#000000"),
                "bgColor": config.get("background_color", "#FFFFFF"),
                "eye1Color": config.get("color", "#000000"),
                "eye2Color": config.get("color", "#000000"),
                "eye3Color": config.get("color", "#000000"),
                "eyeBall1Color": config.get("color", "#000000"),
                "eyeBall2Color": config.get("color", "#000000"),
                "eyeBall3Color": config.get("color", "#000000"),
                "gradientColor1": "",
                "gradientColor2": "",
                "gradientType": "linear",
                "gradientOnEyes": False
            },
            "size": 600,
            "download": False,
            "file": "png"
        }
        
        # Adicionar logo apenas no fallback externo e ainda em modo limpo.
        if config.get("effective_logo_url") and safe_config.get("_logo_bytes"):
            qr_config["config"]["logo"] = config["effective_logo_url"]
            qr_config["config"]["logoMode"] = "clean"
            
        try:
            # Criar connector SSL que ignora verificação de certificado
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    "https://api.qrcode-monkey.com/qr/custom",
                    json=qr_config,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        
                        # Se retornou imagem diretamente
                        if 'image' in content_type:
                            return await response.read()
                        
                        # Se retornou JSON com URL da imagem
                        try:
                            result = await response.json()
                            if "imageUrl" in result:
                                async with session.get(result["imageUrl"]) as img_response:
                                    if img_response.status == 200:
                                        return await img_response.read()
                        except:
                            # Se falhou ao parsear JSON, tentar ler como bytes
                            return await response.read()
        except Exception as e:
            print(f"Erro ao gerar QR personalizado: {e}")
        
        # Fallback para QR simples se houver erro
        return await QRCodeGenerator.generate_simple_qr(data)
    
    @staticmethod
    async def generate_simple_qr(data: str) -> bytes:
        """
        Gera um QR Code simples usando API alternativa
        """
        local_qr = QRCodeGenerator._generate_local_qr(
            data,
            {
                "_ecc_level": "M",
                "_logo_bytes": None,
                "color": "#000000",
                "background_color": "#FFFFFF",
                "corner_style": "square",
            },
        )
        if local_qr:
            return local_qr

        local_qr = QRCodeGenerator._generate_local_qr(
            data,
            {
                "_ecc_level": "L",
                "_logo_bytes": None,
                "color": "#000000",
                "background_color": "#FFFFFF",
                "corner_style": "square",
            },
        )
        if local_qr:
            return local_qr

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote(str(data), safe='')}"
                ) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception as e:
            print(f"Erro ao gerar QR simples: {e}")
        
        return None
    
    @staticmethod
    def panel(inter: disnake.Interaction) -> dict:
        """Painel de personalização de QR Code"""
        mode = db.get_document("custom_mode").get("mode")
        if mode == "components":
            return QRCodeGenerator._panel_components(inter)
        return QRCodeGenerator._panel_embed(inter)
    
    @staticmethod
    def _panel_components(inter: disnake.Interaction) -> dict:
        data = get_qr_config()
        
        color_data = db.get_document("custom_colors")
        primary_color_hex = color_data.get("primary")
        
        container_kwargs = {}
        if primary_color_hex:
            container_kwargs["accent_colour"] = disnake.Colour(int(primary_color_hex.replace("#", ""), 16))
        
        # Status
        status = f"{emoji.on} Ativado" if data.get("enabled") else f"{emoji.off} Desativado"
        logo_status = "Logo personalizada" if data.get("logo_url") else "Logo padrao Lyon Pro"
        
        config_text = (
            f"**Status:** {status}\n"
            f"**Cor Principal:** {data.get('color', '#000000')}\n"
            f"**Cor de Fundo:** {data.get('background_color', '#FFFFFF')}\n"
            f"**Estilo dos Cantos:** {data.get('corner_style', 'square')}\n"
            f"**Logo:** {logo_status}"
        )
        
        return {"components": [
            disnake.ui.Container(
                disnake.ui.TextDisplay(f"# {emoji.lyon}\n-# Loja > Personalizar > **QR Code**"),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(
                    "Personalize a aparência dos QR Codes de pagamento.\n"
                    "Adicione cores, logo e estilos personalizados."
                ),
                disnake.ui.Separator(),
                disnake.ui.TextDisplay(config_text),
                disnake.ui.Separator(),
                disnake.ui.MediaGallery(
                    disnake.MediaGalleryItem(media=data.get("effective_logo_url") or DEFAULT_QR_LOGO_URL)
                ),
                disnake.ui.Separator(),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        label="Configurar",
                        style=disnake.ButtonStyle.blurple,
                        emoji=emoji.config,
                        custom_id="Loja_QRCode_Config"
                    ),
                    disnake.ui.Button(
                        label="Ativar" if not data.get("enabled") else "Desativar",
                        style=disnake.ButtonStyle.green if not data.get("enabled") else disnake.ButtonStyle.red,
                        emoji=emoji.on if not data.get("enabled") else emoji.off,
                        custom_id="Loja_QRCode_Toggle"
                    ),
                    disnake.ui.Button(
                        label="Testar",
                        style=disnake.ButtonStyle.grey,
                        emoji=emoji.science if hasattr(emoji, "science") else "🧪",
                        custom_id="Loja_QRCode_Test"
                    )
                ),
                **container_kwargs
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Loja_Personalizar"
                )
            )
        ]}
    
    @staticmethod
    def _panel_embed(inter: disnake.Interaction):
        data = get_qr_config()
        
        embed = disnake.Embed(
            title=f"{emoji.lyon} Personalização de QR Code",
            description="Configure a aparência dos QR Codes",
            color=disnake.Color.from_rgb(0, 202, 164)
        )
        
        embed.add_field(
            name="Status",
            value=f"{emoji.on if data.get('enabled') else emoji.off} {'Ativado' if data.get('enabled') else 'Desativado'}",
            inline=True
        )
        
        embed.add_field(
            name="Cores",
            value=f"Principal: {data.get('color', '#000000')}\nFundo: {data.get('background_color', '#FFFFFF')}",
            inline=True
        )
        
        embed.add_field(
            name="Estilo",
            value=data.get("corner_style", "square"),
            inline=True
        )
        embed.add_field(
            name="Logo",
            value="Personalizada" if data.get("logo_url") else "Padrão Lyon Pro",
            inline=True,
        )
        embed.set_thumbnail(url=data.get("effective_logo_url") or DEFAULT_QR_LOGO_URL)
        
        components = [
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="Configurar",
                    style=disnake.ButtonStyle.blurple,
                    emoji=emoji.config,
                    custom_id="Loja_QRCode_Config"
                ),
                disnake.ui.Button(
                    label="Ativar" if not data.get("enabled") else "Desativar",
                    style=disnake.ButtonStyle.green if not data.get("enabled") else disnake.ButtonStyle.red,
                    emoji=emoji.on if not data.get("enabled") else emoji.off,
                    custom_id="Loja_QRCode_Toggle"
                ),
                disnake.ui.Button(
                    label="Testar",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.science if hasattr(emoji, "science") else "🧪",
                    custom_id="Loja_QRCode_Test"
                )
            ),
            disnake.ui.ActionRow(
                disnake.ui.Button(
                    label="",
                    style=disnake.ButtonStyle.grey,
                    emoji=emoji.back,
                    custom_id="Loja_Personalizar"
                )
            )
        ]
        
        return {"embed": embed, "components": components}
