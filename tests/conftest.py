import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# config.py does os.environ["SSD_PATH"] at import time -- fall back to a
# harmless default so tests don't depend on a real .env being present.
os.environ.setdefault("SSD_PATH", os.path.dirname(os.path.abspath(__file__)))
