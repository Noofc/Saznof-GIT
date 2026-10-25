#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from _path import RECEIPTS_ASSETS_DIR
from functions.receipt_generator import ReceiptGenerator
from datetime import datetime

def generate_sample_receipt():
    """Gera um comprovante de exemplo com ID do pedido"""
    generator = ReceiptGenerator()

    # Dados de exemplo realistas
    user_name = "João Silva"
    user_handle = "joao_silva"
    items = [
        {"product_name": "VIP Premium Mensal", "campo_name": "Campo Principal", "quantity": 1, "price": 49.99},
        {"product_name": "Boost Nitro", "campo_name": "Servidor XYZ", "quantity": 2, "price": 19.99}
    ]
    total_price = 89.97
    order_id = "ABC123XYZ789"

    # Gerar comprovante
    receipt_buffer = generator.generate_receipt(
        user_name=user_name,
        user_handle=user_handle,
        items=items,
        total_price=total_price,
        order_id=order_id,
        guild_name="Lyon Pro Store"
    )

    # Salvar imagem
    output_path = RECEIPTS_ASSETS_DIR / "comprovante_exemplo.png"
    with open(output_path, "wb") as f:
        f.write(receipt_buffer.getvalue())

    print("✅ Comprovante de exemplo gerado!")
    print(f"📁 Arquivo salvo: {output_path}")
    print(f"📊 Tamanho: {len(receipt_buffer.getvalue())} bytes")
    print(f"🆔 ID do pedido: {order_id}")
    print(f"💰 Valor total: R$ {total_price:.2f}")
    print("\n📋 Itens no carrinho:")
    for item in items:
        print(f"   • {item['quantity']}x {item['product_name']} | {item['campo_name']} - R$ {item['price']:.2f}")

if __name__ == "__main__":
    generate_sample_receipt()
