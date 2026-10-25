#!/usr/bin/env python3
from _path import RECEIPTS_ASSETS_DIR
from functions.receipt_generator import ReceiptGenerator
from datetime import datetime

if __name__ == '__main__':
    generator = ReceiptGenerator()
    items = [
        {"product_name": "VIP Premium Mensal", "campo_name": "Campo Principal", "quantity": 1, "price": 49.99},
        {"product_name": "Boost Nitro", "campo_name": "Servidor XYZ", "quantity": 1, "price": 19.99}
    ]
    receipt = generator.generate_receipt(
        user_name="João Silva",
        user_handle="joao_silva",
        items=items,
        total_price=69.98,
        order_id="ABC123XYZ789",
        guild_name="SYSTEM BOT STORE"
    )
    output_path = RECEIPTS_ASSETS_DIR / 'comprovante_visual.png'
    with open(output_path, 'wb') as f:
        f.write(receipt.getvalue())
    print(f'✅ Comprovante gerado em: {output_path}')
