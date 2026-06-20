"""Encode/decode a plant as a compact, URL-safe share token.

A token is ``base64url(gzip(json(plant.to_dict())))`` -- enough to reconstruct the plant from
a link with no server-side storage. `decode` is deliberately defensive: a ``?p=`` value is
untrusted input, so every malformed or oversized token raises `ValueError` rather than
crashing the page or expanding without bound (a gzip bomb).
"""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import zlib

from technoeconomics.model.plant import Plant

_GZIP_WBITS = 16 + zlib.MAX_WBITS  # zlib window-bits flag selecting the gzip container
_MAX_TOKEN = 16 * 1024  # a plant compresses to ~1 KB; cap the encoded input
_MAX_JSON = 256 * 1024  # cap the decompressed payload (gzip-bomb guard)


def encode(plant: Plant) -> str:
    """Encode a plant as a URL-safe share token.

    Args:
        plant: The plant to encode.

    Returns:
        A ``base64url(gzip(json(...)))`` token suitable for a ``?p=`` query value.
    """
    raw = json.dumps(plant.to_dict(), separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(gzip.compress(raw)).decode("ascii")


def decode(token: str) -> Plant:
    """Reconstruct a plant from a share token.

    Args:
        token: A token produced by [`encode`][technoeconomics.web.share.encode].

    Returns:
        The reconstructed plant.

    Raises:
        ValueError: If the token is malformed, oversized, or not a valid plant.
    """
    if len(token) > _MAX_TOKEN:
        raise ValueError("share token too large")
    try:
        compressed = base64.urlsafe_b64decode(token)
    except (binascii.Error, ValueError) as e:
        raise ValueError("invalid share token") from e
    raw = _gunzip(compressed, _MAX_JSON)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError("invalid share payload") from e
    try:
        return Plant.from_dict(data)
    except Exception as e:  # noqa: BLE001 -- untrusted input: any failure is a bad token
        raise ValueError("invalid plant in share payload") from e


def _gunzip(data: bytes, limit: int) -> bytes:
    """Decompress gzip `data`, rejecting anything that would exceed `limit` bytes.

    Args:
        data: gzip-compressed bytes.
        limit: Maximum allowed decompressed size.

    Returns:
        The decompressed bytes.

    Raises:
        ValueError: If `data` is not valid gzip, or would decompress past `limit`.
    """
    decompressor = zlib.decompressobj(wbits=_GZIP_WBITS)
    try:
        out = decompressor.decompress(data, limit)
    except zlib.error as e:
        raise ValueError("invalid share payload") from e
    if (
        not decompressor.eof
    ):  # input remained, so the output hit `limit` (or is truncated)
        raise ValueError("share payload too large or truncated")
    return out
