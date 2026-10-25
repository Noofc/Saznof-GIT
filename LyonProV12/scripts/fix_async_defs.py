import pathlib
import py_compile
import re

root = pathlib.Path('c:/Users/n2441/Downloads/Lyon bot/Lyon Pro')
changed = 0
for p in root.rglob('*.py'):
    text = p.read_text(encoding='utf-8')
    new_text = re.sub(r'\baLyon\s+(with|for|def)\b', r'async \1', text)
    new_text = new_text.replace('socketio.AsyncClient', 'socketio.AsyncClient')
    new_text = new_text.replace('Optional[socketio.AsyncClient]', 'Optional[socketio.AsyncClient]')
    if new_text != text:
        p.write_text(new_text, encoding='utf-8')
        print('fixed', p.relative_to(root))
        changed += 1

errors = 0
for p in root.rglob('*.py'):
    try:
        py_compile.compile(str(p), doraise=True)
    except py_compile.PyCompileError as e:
        print('ERROR', p.relative_to(root), e)
        errors += 1

print('summary:', changed, 'files updated,', errors, 'compile errors')
