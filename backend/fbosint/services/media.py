"""Image storage, perceptual hashing and duplicate detection.

No facial recognition and no identification of people is performed. GPS
coordinates in EXIF are deliberately NOT extracted (only their presence is
noted) to avoid locating individuals.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import ExifTags, Image, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 50_000_000  # decompression-bomb guard

ALLOWED_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "GIF": ("image/gif", "gif"), "WEBP": ("image/webp", "webp"), "BMP": ("image/bmp", "bmp")}
EXIF_KEEP = {"Make", "Model", "Software", "DateTime", "DateTimeOriginal", "DateTimeDigitized", "Artist", "Copyright", "ImageDescription", "Orientation", "LensModel", "XResolution", "YResolution"}
GPS_TAG = 34853


class MediaError(ValueError):
    pass


@dataclass
class ImageInfo:
    sha256: str
    mime_type: str
    ext: str
    width: int
    height: int
    phash: str
    dhash: str
    metadata: dict


_DCT_CACHE: dict[int, np.ndarray] = {}


def _dct_matrix(n: int) -> np.ndarray:
    if n not in _DCT_CACHE:
        k = np.arange(n).reshape(-1, 1)
        i = np.arange(n).reshape(1, -1)
        m = np.sqrt(2 / n) * np.cos(np.pi * (2 * i + 1) * k / (2 * n))
        m[0, :] = np.sqrt(1 / n)
        _DCT_CACHE[n] = m
    return _DCT_CACHE[n]


def _bits_to_hex(bits: np.ndarray) -> str:
    value = 0
    for b in bits.flatten():
        value = (value << 1) | int(b)
    return f"{value:016x}"


def phash(img: Image.Image) -> str:
    g = img.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    a = np.asarray(g, dtype=np.float64)
    d = _dct_matrix(32)
    coeffs = d @ a @ d.T
    low = coeffs[:8, :8]
    med = np.median(low)
    return _bits_to_hex(low > med)


def dhash(img: Image.Image) -> str:
    g = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    return _bits_to_hex(a[:, 1:] > a[:, :-1])


def hamming(a: str, b: str) -> int:
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _exif(img: Image.Image) -> dict:
    out: dict = {}
    try:
        exif = img.getexif()
    except Exception:
        return out
    for tag_id, value in exif.items():
        if tag_id == GPS_TAG:
            out["gps_data_present"] = True
            out["gps_extracted"] = False
            continue
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if name in EXIF_KEEP:
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            out[name] = str(value)[:200]
    try:
        sub = exif.get_ifd(0x8769)
        for tag_id, value in sub.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if name in EXIF_KEEP:
                out[name] = str(value)[:200]
    except Exception:
        pass
    return out


def analyse_image(data: bytes) -> ImageInfo:
    if not data:
        raise MediaError("empty_file")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise MediaError("not_a_valid_image") from exc
    fmt = img.format or ""
    if fmt not in ALLOWED_FORMATS:
        raise MediaError("unsupported_image_format")
    mime, ext = ALLOWED_FORMATS[fmt]
    meta = _exif(img)
    meta["format"] = fmt
    if getattr(img, "is_animated", False):
        meta["animated"] = True
    frame = img.convert("RGB")
    return ImageInfo(hashlib.sha256(data).hexdigest(), mime, ext, img.width, img.height, phash(frame), dhash(frame), meta)


def store_bytes(media_root: Path, investigation_id: int, info: ImageInfo, data: bytes) -> str:
    folder = media_root / str(investigation_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{info.sha256}.{info.ext}"
    path = folder / name
    if not path.exists():
        path.write_bytes(data)
    return f"{investigation_id}/{name}"


def group_duplicates(items: list[tuple[int, str, str]], threshold: int = 8) -> dict[int, int | None]:
    """items: (id, sha256, phash). Returns id -> group id (smallest member id) or None."""
    parent = {i: i for i, _, _ in items}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for idx, (i, sa, pa) in enumerate(items):
        for j, sb, pb in items[idx + 1:]:
            if (sa and sa == sb) or (pa and pb and hamming(pa, pb) <= threshold):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups: dict[int, list[int]] = {}
    for i, _, _ in items:
        groups.setdefault(find(i), []).append(i)
    result: dict[int, int | None] = {}
    for root, members in groups.items():
        for m in members:
            result[m] = min(members) if len(members) > 1 else None
    return result
