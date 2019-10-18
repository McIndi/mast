def _s(s):
    if isinstance(s, str):
        return s
    elif isinstance(s, bytes):
        return s.decode()
    else:
        return str(s)

def _b(b):
    if isinstance(b, str):
        return b.encode()
    elif isinstance(b, bytes):
        return b
    else:
        return bytes(b)
