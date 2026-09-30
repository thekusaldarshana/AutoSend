"""Photos attached to messages are copied into AutoSend's own folder so moving the original can't break a send."""
from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from . import paths

IMAGE_TYPES = "Pictures (*.jpg *.jpeg *.png *.webp)"


def import_image(src: str) -> str:
    dst = paths.media_dir() / f"{int(time.time())}-{uuid.uuid4().hex[:6]}{Path(src).suffix.lower()}"
    shutil.copyfile(src, dst)
    return str(dst)
