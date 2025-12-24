import os
import sys

# Делаем так, чтобы `import llm_judge` всегда работал,
# даже если pytest запущен не из backend-root.
THIS_DIR = os.path.dirname(__file__)
BACKEND_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))  # .../backend (где лежит llm_judge)

if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)
