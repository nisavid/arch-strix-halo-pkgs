from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import sys

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from gemma4_server_smoke import multimodal_content, validate_multimodal_response


def _image_data_urls(mode: str) -> list[str]:
    content = multimodal_content(SimpleNamespace(mode=mode))
    urls = []
    for item in content:
        if item.get("type") == "image_url":
            image_url = item.get("image_url") or {}
            urls.append(image_url["url"])
    return urls


def test_gemma4_image_smoke_payloads_are_valid_pngs():
    for mode in ("image", "multi-image", "image-dynamic", "multimodal-tool"):
        for url in _image_data_urls(mode):
            prefix = "data:image/png;base64,"
            assert url.startswith(prefix)
            payload = base64.b64decode(url.removeprefix(prefix), validate=True)
            image = Image.open(BytesIO(payload))
            image.load()
            assert image.size[0] >= 1
            assert image.size[1] >= 1


def test_gemma4_multimodal_response_accepts_short_descriptive_caption():
    response = {
        "choices": [
            {
                "message": {
                    "content": "Solid bright blue color.",
                },
            },
        ],
    }

    assert validate_multimodal_response(response)["content"] == "Solid bright blue color."
