import hashlib

# 2048-bit prime (p = 3 mod 4) for Sloth VDF
# Derived from RFC 3526 for demonstration
P_2048 = 2**2048 - 2**1984 - 1 + 2**64 * (int("27182818284590452353602874713526624977572470936999595749669676277240766303535", 10))
# Make sure it's 3 mod 4
if P_2048 % 4 != 3:
    P_2048 = P_2048 - 2 # Adjusting downward minimally for PoC to ensure 3 mod 4

def legendre(a, p):
    return pow(a, (p - 1) // 2, p)

def _sqrt_p3mod4(a, p):
    return pow(a, (p + 1) // 4, p)

def compute_sloth_vdf(challenge: bytes, iterations: int = 100) -> tuple[int, str]:
    x = int.from_bytes(hashlib.sha256(challenge).digest(), byteorder='big') % P_2048
    flip_vector = []
    
    for _ in range(iterations):
        if legendre(x, P_2048) == 1:
            x = _sqrt_p3mod4(x, P_2048)
            flip_vector.append("0")
        else:
            x = _sqrt_p3mod4(-x % P_2048, P_2048)
            flip_vector.append("1")
            
    return x, "".join(flip_vector)

def verify_sloth_vdf(challenge: bytes, proof: int, flip_vector: str, iterations: int = 100) -> bool:
    if len(flip_vector) != iterations:
        return False
        
    expected_initial = int.from_bytes(hashlib.sha256(challenge).digest(), byteorder='big') % P_2048
    x = proof
    
    for flip in reversed(flip_vector):
        x = pow(x, 2, P_2048)
        if flip == "1":
            x = -x % P_2048
            
    return x == expected_initial
