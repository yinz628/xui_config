"""Payload parsing helpers for the web console.

Keep this as a thin wrapper around the core implementation so both the web UI
and the generator pipeline share the same subscription parsing behavior.
"""

from xui_port_pool_generator.subscription_payloads import extract_proxies_from_payload

__all__ = ["extract_proxies_from_payload"]

