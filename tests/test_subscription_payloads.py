import base64

from xui_port_pool_generator.subscription_payloads import extract_proxies_from_payload


def test_extract_proxies_from_clash_yaml_payload() -> None:
    proxies = extract_proxies_from_payload(
        """
proxies:
  - name: HK 01
    type: ss
    server: hk.example.com
    port: 443
    cipher: aes-128-gcm
    password: pw
""".strip()
    )

    assert len(proxies) == 1
    assert proxies[0]["type"] == "ss"
    assert proxies[0]["server"] == "hk.example.com"


def test_extract_proxies_from_uri_lines_payload() -> None:
    proxies = extract_proxies_from_payload(
        """

ss://YWVzLTEyOC1nY206cHc=@hk.example.com:443#HK%2001

""".strip()
    )

    assert len(proxies) == 1
    assert proxies[0]["name"] == "HK 01"
    assert proxies[0]["type"] == "ss"


def test_extract_proxies_from_base64_blob_payload() -> None:
    raw = "ss://YWVzLTEyOC1nY206cHc=@hk.example.com:443#HK%2001\n"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    proxies = extract_proxies_from_payload(encoded)

    assert len(proxies) == 1
    assert proxies[0]["name"] == "HK 01"


def test_extract_proxies_returns_empty_for_invalid_payload() -> None:
    proxies = extract_proxies_from_payload("not a subscription")
    assert proxies == []

