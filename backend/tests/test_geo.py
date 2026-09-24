from starlette.datastructures import Headers

from backend.app.services.geo import (
    country_flag,
    country_from_headers,
    country_from_ip,
    country_name,
    normalize_country,
)


def test_normalize_country_accepts_iso_codes():
    assert normalize_country("us") == "US"
    assert normalize_country("  de ") == "DE"
    assert normalize_country("XX") is None
    assert normalize_country("T1") is None
    assert normalize_country("USA") is None
    assert normalize_country("") is None
    assert normalize_country(None) is None


def test_country_from_headers_reads_proxy_country():
    headers = Headers({"cf-ipcountry": "br"})
    assert country_from_headers(headers) == "BR"


def test_country_from_headers_ignores_unknown():
    headers = Headers({"cf-ipcountry": "XX"})
    assert country_from_headers(headers) is None


def test_private_ips_are_not_looked_up():
    assert country_from_ip("127.0.0.1") is None
    assert country_from_ip("10.0.0.4") is None
    assert country_from_ip("192.168.1.10") is None
    assert country_from_ip("not-an-ip") is None
    assert country_from_ip(None) is None


def test_country_display():
    assert country_name("US") == "United States"
    assert country_name("ZZ") == "ZZ"
    assert country_flag("US") == "🇺🇸"
    assert country_flag(None) == ""
