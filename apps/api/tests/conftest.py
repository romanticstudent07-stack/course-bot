import sys
from pathlib import Path

# apps/api в sys.path — тесты запускаются из корня репо или из apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
