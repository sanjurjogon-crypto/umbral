from __future__ import annotations

import ssl
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    """Return an SSLContext backed by certifi (critical for frozen macOS PyInstaller bundles)."""
    try:
        import certifi

        ca_file = certifi.where()
        if ca_file and Path(ca_file).is_file():
            return ssl.create_default_context(cafile=ca_file)
    except Exception:
        pass
    mac_cert = Path("/etc/ssl/cert.pem")
    if mac_cert.is_file():
        return ssl.create_default_context(cafile=str(mac_cert))
    return ssl.create_default_context()
