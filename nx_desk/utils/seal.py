import hashlib
import hmac
import secrets

NONCE = 16
TAG = 16


def _stream(key: bytes, nonce: bytes, size: int) -> bytes:
    return hashlib.shake_256(b"seal" + key + nonce).digest(size)


def _mix(key: bytes, nonce: bytes, data: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, _stream(key=key, nonce=nonce, size=len(data)), strict=True))


def _tag(key: bytes, body: bytes) -> bytes:
    return hmac.new(key, b"tag" + body, hashlib.sha256).digest()[:TAG]


# Two-way: the text comes back with the same key. It hides the text from a reader of the file, but
# not from one who can also read the key.
def seal(key: bytes, text: str) -> str:
    nonce = secrets.token_bytes(NONCE)
    data = text.encode(encoding="utf-8")
    body = nonce + _mix(key=key, nonce=nonce, data=data)

    return (body + _tag(key=key, body=body)).hex()


def unseal(key: bytes, sealed: str) -> str:
    try:
        raw = bytes.fromhex(sealed)
    except ValueError:
        raise ValueError("the sealed text is not hex") from None

    if len(raw) < NONCE + TAG:
        raise ValueError("the sealed text is too short")

    body, tag = raw[:-TAG], raw[-TAG:]

    if not hmac.compare_digest(tag, _tag(key=key, body=body)):
        raise ValueError("the sealed text does not match its key")

    nonce, data = body[:NONCE], body[NONCE:]

    return _mix(key=key, nonce=nonce, data=data).decode(encoding="utf-8")
