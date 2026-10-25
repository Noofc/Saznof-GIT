from datetime import datetime

from _path import RECEIPTS_ASSETS_DIR
from functions.receipt_generator import ReceiptGenerator


rg = ReceiptGenerator()
buf = rg.generate_receipt(
    user_name="5429",
    user_handle="5429",
    user_avatar_path="",
    items=[{"product_name": "dwdaad", "campo_name": "fesfefst", "quantity": 1, "price": 19.90}],
    total_price=19.90,
    subtotal=19.90,
    guild_name="Lyon Apps",
    guild_icon_path="",
    footer_text="Powered by Lyon Pro",
    coupon_code=None,
    timestamp=datetime(2026, 5, 7, 13, 38),
)

output_path = RECEIPTS_ASSETS_DIR / "test_receipt.png"
with open(output_path, "wb") as f:
    f.write(buf.getvalue())

print(f"wrote {output_path}")
