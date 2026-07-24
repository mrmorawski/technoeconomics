"""Encode/decode an [`Envelope`][technoeconomics.web.envelope.Envelope] as a URL-safe token.

A token is ``base64url(gzip(json(envelope)))`` -- enough to reconstruct a shared model from a
link with no server-side storage. The envelope is the same ``{preset, overlay, enabled}`` the
client edits and solves, so loading a share is just an overlay over the named preset's default.

`decode` is deliberately defensive: a ``?p=`` value is untrusted input, so every malformed,
stale, or oversized token raises `ValueError` rather than crashing the page or expanding without
bound (a gzip bomb). `TypeAdapter(Envelope)` validates the envelope's *shape*; that the overlay
paths exist and its values are in bounds is enforced at solve against the preset's spec.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import zlib

from pydantic import TypeAdapter, ValidationError

from technoeconomics.web.envelope import Envelope

_GZIP_WBITS = 16 + zlib.MAX_WBITS  # zlib window-bits flag selecting the gzip container
_MAX_TOKEN = (
    16 * 1024
)  # an overlay compresses to well under this; cap the encoded input
_MAX_JSON = 256 * 1024  # cap the decompressed payload (gzip-bomb guard)

_envelope = TypeAdapter(Envelope)


def encode(envelope: Envelope) -> str:
    """Encode an envelope as a URL-safe token.

    Args:
        envelope: The envelope to encode.

    Returns:
        A ``base64url(gzip(json(...)))`` token suitable for a ``?p=`` query value.
    """
    raw = _envelope.dump_json(envelope)
    return base64.urlsafe_b64encode(gzip.compress(raw)).decode("ascii")


def decode(token: str) -> Envelope:
    """Reconstruct an envelope from a token.

    Args:
        token: A token produced by [`encode`][technoeconomics.web.share.encode].

    Returns:
        The reconstructed envelope (shape-validated, not solve-validated).

    Raises:
        ValueError: If the token is malformed, oversized, or not a well-formed envelope.
    """
    if len(token) > _MAX_TOKEN:
        raise ValueError("share token too large")
    try:
        compressed = base64.urlsafe_b64decode(token)
    except (binascii.Error, ValueError) as e:
        raise ValueError("invalid share token") from e
    raw = _gunzip(compressed, _MAX_JSON)
    try:
        return _envelope.validate_json(raw)
    except ValidationError as e:
        raise ValueError("invalid share payload") from e


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
