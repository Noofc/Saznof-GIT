from PIL import Image, ImageDraw
import os

def apply_rounded_corners(input_path: str, output_path: str, radius: int = 25, background_color: tuple = (40, 40, 40)):
    """
    Aplica cantos arredondados a uma imagem e salva o resultado.
    
    Args:
        input_path (str): Caminho da imagem de entrada
        output_path (str): Caminho da imagem de saída
        radius (int): Raio de arredondamento em pixels (padrão: 25)
        background_color (tuple): Cor RGB do fundo (padrão: cinza escuro)
    """
    
    if not os.path.exists(input_path):
        print(f"Erro: Arquivo '{input_path}' não encontrado.")
        return False
    
    img = Image.open(input_path).convert("RGB")
    width, height = img.size
    
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, width, height], radius=radius, fill=255)
    
    output_img = Image.new("RGB", (width, height), background_color)
    output_img.paste(img, (0, 0), mask)
    
    output_img.save(output_path, "PNG")
    print(f"✅ Imagem salva com sucesso em: {output_path}")
    print(f"   Dimensões: {width}x{height}")
    print(f"   Raio de arredondamento: {radius}px")
    return True


if __name__ == "__main__":
    input_file = "entrada.png"
    output_file = "saida.png"
    radius_value = 25
    
    apply_rounded_corners(input_file, output_file, radius=radius_value)
