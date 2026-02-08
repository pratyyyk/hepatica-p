from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image


def maybe_convert_dicom(image_bytes: bytes, content_type: str) -> bytes:
    if not content_type.startswith("application/dicom"):
        return image_bytes

    try:
        import pydicom

        ds = pydicom.dcmread(BytesIO(image_bytes))
        arr = ds.pixel_array.astype(np.float32)
        arr = arr - arr.min()
        if arr.max() > 0:
            arr = arr / arr.max()
        arr = (arr * 255).astype(np.uint8)

        img = Image.fromarray(arr)
        if img.mode != "RGB":
            img = img.convert("RGB")

        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:
        raise ValueError("Unable to decode DICOM payload") from exc
