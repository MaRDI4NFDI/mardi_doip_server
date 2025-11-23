"""TLS helpers for wrapping sockets."""

from __future__ import annotations

import ssl
import socket


def wrap_socket(sock: socket.socket, hostname: str, use_tls: bool, verify_tls: bool) -> socket.socket:
    """Optionally wrap a socket with TLS.

    Args:
        sock: Connected TCP socket.
        hostname: Server hostname for SNI/verification.
        use_tls: Whether to wrap with TLS.
        verify_tls: Whether to verify certificates/hostname.

    Returns:
        TLS-wrapped socket or the original socket if TLS is disabled.
    """
    if not use_tls:
        return sock
    context = ssl.create_default_context()
    if not verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context.wrap_socket(sock, server_hostname=hostname)
