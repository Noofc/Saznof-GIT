import json
import os
import sys
# garantir que o diretório do projeto esteja no sys.path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from functions.emojis import emojis

# Ler config
cfg_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
cfg_path = os.path.abspath(cfg_path)
with open(cfg_path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

bot_token = cfg.get('bot', {}).get('token') or cfg.get('botToken')
app_id = cfg.get('bot', {}).get('id') or cfg.get('botID')

if not bot_token or not app_id:
    print('Pro token ou App ID não encontrados em config.json')
    raise LyonExit(1)

print('Iniciando sync seguro de emojis...')
emo = emojis(bot_token, app_id)
result = emo.Lyon_add_missing()
print('Resultado:', result)
