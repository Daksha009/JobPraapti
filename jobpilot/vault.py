"""Windows account-bound secret storage. Plaintext never leaves process memory."""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from filelock import FileLock
from .registry import PLATFORMS

SECRET_KEYS = {"GEMINI_API_KEY"} | {
    f"{platform}_{field}"
    for platform in (name.upper() for name in PLATFORMS)
    for field in ("EMAIL", "PASSWORD")
}


class Blob(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _crypt(payload: bytes, decrypt=False) -> bytes:
    if os.name != "nt":
        raise RuntimeError(
            "The encrypted vault requires Windows DPAPI on this installation"
        )
    buffer = ctypes.create_string_buffer(payload)
    source = Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    if not function(
        ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)
    ):
        raise RuntimeError(
            "Cannot unlock the credential vault with this Windows account"
        )
    try:
        return ctypes.string_at(output.data, output.length)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(output.data)


class Vault:
    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(_crypt(self.path.read_bytes(), decrypt=True))

    def update(self, values: dict[str, str], *, replace=False):
        if not isinstance(values, dict) or set(values) - SECRET_KEYS:
            raise ValueError("Unsupported credential fields")
        if any(
            not isinstance(value, str) or len(value) > 4096 for value in values.values()
        ):
            raise ValueError("Credentials must be strings under 4096 characters")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock"):
            current = {} if replace else self.read()
            for key, value in values.items():
                if value:
                    current[key] = value if key.endswith("_PASSWORD") else value.strip()
                else:
                    current.pop(key, None)
            ciphertext = _crypt(json.dumps(current).encode())
            temporary = self.path.with_suffix(".tmp")
            temporary.write_bytes(ciphertext)
            temporary.replace(self.path)


def migrate_env(vault: Vault, env_path: Path):
    """Move existing plaintext secrets into DPAPI without displaying their values."""
    from dotenv import dotenv_values

    if not env_path.exists():
        return
    values = {
        key: value
        for key, value in dotenv_values(env_path).items()
        if key in SECRET_KEYS and value and not value.startswith("your_")
    }
    # Keep values already supplied to the vault in preference to old .env entries.
    vault.update(values | vault.read())
    lines = env_path.read_text(encoding="utf-8").splitlines()
    kept = [
        line
        for line in lines
        if line.partition("=")[0].strip().removeprefix("export ") not in SECRET_KEYS
    ]
    temporary = env_path.with_suffix(".tmp")
    temporary.write_text(
        "# Credentials are stored in the Windows-encrypted local vault.\n"
        + "\n".join(kept)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(env_path)


if __name__ == "__main__":
    import sys
    from .config import DATA_DIR, BASE_DIR

    vault = Vault(DATA_DIR / "credentials.dpapi")
    try:
        supplied = json.loads(sys.stdin.readline())
        vault.update(supplied, replace="--replace" in sys.argv)
        migrate_env(vault, BASE_DIR / ".env")
        print(
            "Credentials encrypted for the current Windows account; plaintext .env entries removed."
        )
    except Exception:
        print(
            "Credential import failed. No secret values were printed.", file=sys.stderr
        )
        sys.exit(1)
