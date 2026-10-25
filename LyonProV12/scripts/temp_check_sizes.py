from PIL import Image
import os
base = r'c:/Users/n2441/Downloads/Lyon bot/Lyon Pro'
files = ['sample_receipt.png','sample_receipt2.png','sample_receipt_fixed.png','sample_receipt_restored.png','sample_receipt_small.png']
for f in files:
    p = os.path.join(base,f)
    if os.path.exists(p):
        with Image.open(p) as im:
            print(f, im.size)
    else:
        print(f, 'missing')