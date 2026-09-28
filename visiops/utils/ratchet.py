import ctypes
import hmac
import hashlib
import logging
from ctypes import wintypes

try:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.VirtualLock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.VirtualLock.restype = wintypes.BOOL
    kernel32.VirtualUnlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.VirtualUnlock.restype = wintypes.BOOL
    kernel32.RtlSecureZeroMemory.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.RtlSecureZeroMemory.restype = ctypes.c_void_p
except Exception:
    kernel32 = None
    logging.warning("Non-Windows OS: VirtualLock disabled.")

class SecureRatchetKey:
    def __init__(self, initial_key_bytes: bytes):
        self.size = len(initial_key_bytes)
        self._buffer = bytearray(initial_key_bytes)
        self._c_array = (ctypes.c_char * self.size).from_buffer(self._buffer)
        self.address = ctypes.addressof(self._c_array)
        if kernel32:
            kernel32.VirtualLock(self.address, self.size)

    def get_key(self) -> bytes:
        return bytes(self._buffer)

    def ratchet(self, record_hash: bytes) -> None:
        # V8 Forward Secrecy Protocol
        msg = b"VISIOPS-ratchet-v1|" + record_hash
        next_key = hmac.new(bytes(self._buffer), msg, hashlib.sha256).digest()
        self._buffer[:] = next_key

    def zeroize(self) -> None:
        if kernel32:
            kernel32.RtlSecureZeroMemory(self.address, self.size)
            kernel32.VirtualUnlock(self.address, self.size)
        else:
            for i in range(self.size):
                self._buffer[i] = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zeroize()
