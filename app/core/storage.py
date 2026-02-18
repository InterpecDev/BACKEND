import os
from pathlib import Path

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

def ensure_dirs():
    Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(STORAGE_DIR, "chapters")).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(STORAGE_DIR, "dictamenes")).mkdir(parents=True, exist_ok=True)

def chapter_dir(chapter_id: int) -> str:
    p = os.path.join(STORAGE_DIR, "chapters", str(chapter_id))
    Path(p).mkdir(parents=True, exist_ok=True)
    return p
