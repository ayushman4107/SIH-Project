import ctypes
import hashlib
import hmac
import logging
from ctypes import wintypes

# Load Windows Kernel32 DLL
try:
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    
    # Define VirtualLock: BOOL VirtualLock(LPVOID lpAddress, SIZE_T dwSize);
    kernel32.VirtualLock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.VirtualLock.restype = wintypes.BOOL
    
    # Define VirtualUnlock: BOOL VirtualUnlock(LPVOID lpAddress, SIZE_T dwSize);
    kernel32.VirtualUnlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.VirtualUnlock.restype = wintypes.BOOL
    
    # Define RtlSecureZeroMemory: PVOID RtlSecureZeroMemory(PVOID ptr, SIZE_T cnt);
    kernel32.RtlSecureZeroMemory.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.RtlSecureZeroMemory.restype = ctypes.c_void_p
except Exception:
    kernel32 = None
    logging.warning(
        "CRITICAL SECURITY DEGRADATION: Non-Windows OS detected or Kernel32 unavailable. "
        "Secure zeroization and page-locking are bypassed. Keys may persist in heap memory "
        "or swap files, compromising forward secrecy."
    )


class SecureRatchetKey:
    """
    A mutable, page-locked memory buffer for cryptographic keys on Windows.
    Minimizes the exposure window of keys in CPython's heap memory.
    """
    def __init__(self, initial_key_bytes: bytes):
        self.size = len(initial_key_bytes)
        # Create a mutable bytearray
        self._buffer = bytearray(initial_key_bytes)
        
        # Get the direct memory address of the bytearray's underlying C buffer
        self._c_array = (ctypes.c_char * self.size).from_buffer(self._buffer)
        self.address = ctypes.addressof(self._c_array)
        
        # Lock the memory page to prevent it from being swapped to the Windows pagefile (disk)
        if kernel32:
            success = kernel32.VirtualLock(self.address, self.size)
            if not success:
                logging.warning(
                    "VirtualLock failed. The process working set limit may have been reached. "
                    "Keys may be paged to disk."
                )

    def get_key(self) -> bytes:
        """
        Note: Accessing this creates an immutable copy in Python space. 
        It should only be held in memory for the duration of the HMAC call.
        """
        return bytes(self._buffer)

    def ratchet(self, current_signature: bytes) -> None:
        """Derives the next key and securely overwrites the current buffer."""
        # 1. Derive next key in a separate scope using standard HKDF-style HMAC
        next_key = hmac.new(
            self.get_key(),
            b"sentinel-ratchet-v1" + current_signature,
            hashlib.sha256
        ).digest()
        
        # 2. Overwrite the Python bytearray explicitly
        self._buffer[:] = next_key
        
    def zeroize(self) -> None:
        """Securely zero out the RAM and unlock the page."""
        if kernel32:
            # RtlSecureZeroMemory guarantees the compiler will not optimize this away
            kernel32.RtlSecureZeroMemory(self.address, self.size)
            kernel32.VirtualUnlock(self.address, self.size)
        else:
            # Fallback for non-Windows (or missing permissions)
            for i in range(self.size):
                self._buffer[i] = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.zeroize()
