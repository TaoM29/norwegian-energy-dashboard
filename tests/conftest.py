import sys
from pathlib import Path

# Add repo root to Python path so `import app_core...` works in tests
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
