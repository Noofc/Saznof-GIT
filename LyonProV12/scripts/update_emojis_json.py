import os
import json

src = r"C:\Users\n2441\Downloads\Emojis"
json_path = r"C:\Users\n2441\Downloads\Lyon bot\Lyon Pro\database\emojis\emojis.json"

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

changed = False
for name in os.listdir(src):
    full = os.path.join(src, name)
    if not os.path.isfile(full):
        continue
    base, ext = os.path.splitext(name)
    if base in data:
        continue
    # add new key with empty value to be filled after upload
    data[base] = ""
    changed = True

if changed:
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print('UPDATED')
else:
    print('NO_CHANGES')
