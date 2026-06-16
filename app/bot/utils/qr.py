"""Generate a PNG QR code from a string."""
from __future__ import annotations

from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def make_qr_png(data: str, *, box_size: int = 10, border: int = 2) -> BytesIO:
    """Return a `BytesIO` containing a PNG render of the QR code."""
    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    bio = BytesIO()
    bio.name = "qr.png"
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio
