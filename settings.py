"""Portable defaults. Environment variables may point outside the repository."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = Path(os.environ.get('BIKE_RAW_DIR', ROOT / 'data' / 'raw')).expanduser().resolve()
WORK = Path(os.environ.get('BIKE_WORK_DIR', ROOT / 'outputs')).expanduser().resolve()
FONT = os.environ.get('BIKE_FONT', 'Malgun Gothic')
