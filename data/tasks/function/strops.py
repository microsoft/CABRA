import codecs


def _rotate_chars(s: str, n: int) -> str:
    result = []
    for c in s:
        if c.islower():
            result.append(chr((ord(c) - ord('a') + n) % 26 + ord('a')))
        elif c.isupper():
            result.append(chr((ord(c) - ord('A') + n) % 26 + ord('A')))
        else:
            result.append(c)
    return "".join(result)


# ── unary (str → str) ────────────────────────────────────────────────────────

def rot13(s: str) -> str:
    return codecs.encode(s, 'rot_13')

def reverse(s: str) -> str:
    return s[::-1]

def swap_case(s: str) -> str:
    return s.swapcase()

def char_rotate(s: str) -> str:
    return _rotate_chars(s, 1)

def char_rotate_by_3(s: str) -> str:
    return _rotate_chars(s, 3)

def mirror(s: str) -> str:
    result = []
    for c in s:
        if c.islower() and 'a' <= c <= 'z':
            result.append(chr(ord('z') - (ord(c) - ord('a'))))
        elif c.isupper() and 'A' <= c <= 'Z':
            result.append(chr(ord('Z') - (ord(c) - ord('A'))))
        else:
            result.append(c)
    return "".join(result)


# ── binary (str, str → str) ──────────────────────────────────────────────────

def interleave(a: str, b: str) -> str:
    """Alternate chars from a and b, clipped to min length: 'abcd'+'efgh' → 'aecg'."""
    n = min(len(a), len(b))
    return "".join(a[i] if i % 2 == 0 else b[i // 2] for i in range(n))

def swap_halves(a: str, b: str) -> str:
    """Second half of a + first half of b, clipped to shorter: 'abcd'+'efgh' → 'cdef'."""
    n = min(len(a), len(b))
    mid = n // 2
    return a[mid:n] + b[:mid]

def zip_chars(a: str, b: str) -> str:
    """Pick from a at even indices, b at odd, clipped to shorter: 'abcd'+'ef' → 'af'."""
    n = min(len(a), len(b))
    return "".join(a[i] if i % 2 == 0 else b[i] for i in range(n))

def alternate_chars(a: str, b: str) -> str:
    """Even-indexed chars of a + odd-indexed chars of b: 'abcd'+'efgh' → 'acfh'."""
    return a[::2] + b[1::2]

def xor_chars(a: str, b: str) -> str:
    """XOR ordinals mod 26, map to lowercase letters, clipped to shorter."""
    n = min(len(a), len(b))
    return "".join(chr(ord('a') + (ord(a[i]) ^ ord(b[i])) % 26) for i in range(n))
