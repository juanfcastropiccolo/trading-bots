"""Generador de billetera EVM (Ethereum y compatibles) en Python puro, sin dependencias.

Genera una clave privada aleatoria (os.urandom) y deriva la dirección pública
con secp256k1 + keccak-256. Se puede importar en MetaMask / Rabby / Trust Wallet
con "Importar cuenta -> clave privada".
"""
import os
import sys

# ---------- keccak-256 (Ethereum, NO es sha3-256 de hashlib) ----------
_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
]
_MASK = (1 << 64) - 1


def _rol(x, n):
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(st):
    for rc in _RC:
        c = [st[x][0] ^ st[x][1] ^ st[x][2] ^ st[x][3] ^ st[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        st = [[st[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(st[x][y], _ROT[x][y])
        st = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        st[0][0] ^= rc
    return st


def keccak256(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data) + b"\x01"
    padded += b"\x00" * ((rate - len(padded) % rate) % rate)
    padded[-1] |= 0x80
    st = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), rate):
        blk = padded[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(blk[8 * i:8 * i + 8], "little")
            st[i % 5][i // 5] ^= lane
        st = _keccak_f(st)
    out = b""
    for i in range(4):
        out += st[i % 5][i // 5].to_bytes(8, "little")
    return out


# ---------- secp256k1 ----------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)


def _mul(k, pt):
    r = None
    while k:
        if k & 1:
            r = _add(r, pt)
        pt = _add(pt, pt)
        k >>= 1
    return r


def to_checksum(addr_hex: str) -> str:
    h = keccak256(addr_hex.encode()).hex()
    return "0x" + "".join(c.upper() if int(h[i], 16) >= 8 else c for i, c in enumerate(addr_hex))


def address_from_priv(priv: int) -> str:
    x, y = _mul(priv, G)
    pub = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return to_checksum(keccak256(pub)[-20:].hex())


def selftest():
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert address_from_priv(1) == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
    assert address_from_priv(2) == "0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF"


if __name__ == "__main__":
    selftest()
    while True:
        priv = int.from_bytes(os.urandom(32), "big")
        if 1 <= priv < N:
            break
    print("CLAVE PRIVADA (secreta):", "0x" + priv.to_bytes(32, "big").hex())
    print("DIRECCION (publica):    ", address_from_priv(priv))
