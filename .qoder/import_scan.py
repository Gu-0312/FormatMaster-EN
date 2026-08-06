import importlib, sys, os, glob
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication
app = QApplication([])

modules = []
for base in ['gui_qt', 'core', 'utils', 'app']:
    for path in glob.glob(f'{base}/**/*.py', recursive=True):
        if '__pycache__' in path or path.endswith('__init__.py'):
            continue
        mod = path[:-3].replace(os.sep, '.')
        modules.append(mod)

fails = []
for m in sorted(modules):
    try:
        importlib.import_module(m)
    except Exception as e:
        fails.append((m, type(e).__name__, str(e)))

if fails:
    print(f"=== {len(fails)} IMPORT FAILURES ===")
    for m, t, e in fails:
        print(f"{m}: {t}: {e}")
else:
    print(f"All {len(modules)} modules import OK")
