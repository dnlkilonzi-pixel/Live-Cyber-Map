"""Unit tests for GeoIPService.

Tests cover: enrich, get_random_ip_for_country, get_random_country,
get_random_ip, get_country_info, _resolve_country_code, _complete_ip,
and _is_valid_ip.
"""

from __future__ import annotations

import pytest

from app.services.geoip import GeoIPService


@pytest.fixture
def svc() -> GeoIPService:
    return GeoIPService()


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------

def test_enrich_known_prefix_returns_correct_country(svc):
    # 8.8.x.x is a US prefix
    result = svc.enrich("8.8.8.8")
    assert result["country"] == "United States"
    assert result["country_code"] == "US"


def test_enrich_returns_lat_lng_close_to_centroid(svc):
    result = svc.enrich("8.8.8.8")
    # Jitter is ±2°; US centroid lat≈37.09, lng≈-95.71
    assert abs(result["lat"] - 37.09) <= 3
    assert abs(result["lng"] - (-95.71)) <= 3


def test_enrich_unknown_ip_falls_back_to_us(svc):
    result = svc.enrich("0.0.0.1")
    assert result["country_code"] == "US"


def test_enrich_result_has_all_keys(svc):
    result = svc.enrich("1.180.0.1")
    assert set(result.keys()) == {"lat", "lng", "country", "country_code"}


def test_enrich_china_prefix(svc):
    # 1.180.x.x → CN
    result = svc.enrich("1.180.10.5")
    assert result["country_code"] == "CN"


# ---------------------------------------------------------------------------
# get_random_ip_for_country
# ---------------------------------------------------------------------------

def test_get_random_ip_for_known_country_is_valid_ipv4(svc):
    ip = svc.get_random_ip_for_country("RU")
    parts = ip.split(".")
    assert len(parts) == 4
    for p in parts:
        assert 0 <= int(p) <= 255


def test_get_random_ip_for_unknown_country_falls_back_to_us(svc):
    # Unknown code → falls back to US prefixes
    ip = svc.get_random_ip_for_country("XX")
    parts = ip.split(".")
    assert len(parts) == 4


def test_get_random_ip_for_north_korea(svc):
    # KP has only 2 prefixes; make sure we still get a valid IP
    ip = svc.get_random_ip_for_country("KP")
    parts = ip.split(".")
    assert len(parts) == 4


# ---------------------------------------------------------------------------
# get_random_country
# ---------------------------------------------------------------------------

def test_get_random_country_has_required_keys(svc):
    country = svc.get_random_country()
    for key in ("name", "lat", "lng", "country_code"):
        assert key in country


def test_get_random_country_returns_copy(svc):
    c1 = svc.get_random_country()
    c1["name"] = "MUTATED"
    c2 = svc.get_random_country()
    # The mutation should not affect the internal table
    assert GeoIPService._COUNTRIES.get(c2["country_code"], {}).get("name") != "MUTATED"


# ---------------------------------------------------------------------------
# get_random_ip
# ---------------------------------------------------------------------------

def test_get_random_ip_is_valid_ipv4(svc):
    ip = svc.get_random_ip()
    parts = ip.split(".")
    assert len(parts) == 4
    for p in parts:
        assert 0 <= int(p) <= 255


# ---------------------------------------------------------------------------
# get_country_info
# ---------------------------------------------------------------------------

def test_get_country_info_known(svc):
    info = svc.get_country_info("DE")
    assert info is not None
    assert info["name"] == "Germany"


def test_get_country_info_unknown_returns_none(svc):
    assert svc.get_country_info("ZZ") is None


# ---------------------------------------------------------------------------
# _resolve_country_code
# ---------------------------------------------------------------------------

def test_resolve_by_two_octet_prefix(svc):
    # 1.180 maps to CN in the prefix table
    code = svc._resolve_country_code("1.180.0.1")
    assert code == "CN"


def test_resolve_by_single_octet_prefix(svc):
    # 8.x.x.x → US
    code = svc._resolve_country_code("8.99.0.1")
    assert code == "US"


def test_resolve_unknown_falls_back_to_us(svc):
    code = svc._resolve_country_code("0.0.0.0")
    assert code == "US"


# ---------------------------------------------------------------------------
# _complete_ip
# ---------------------------------------------------------------------------

def test_complete_ip_single_octet_prefix():
    ip = GeoIPService._complete_ip("10")
    parts = ip.split(".")
    assert len(parts) == 4
    assert parts[0] == "10"


def test_complete_ip_two_octet_prefix():
    ip = GeoIPService._complete_ip("192.168")
    parts = ip.split(".")
    assert len(parts) == 4
    assert parts[0] == "192"
    assert parts[1] == "168"


def test_complete_ip_already_full():
    ip = GeoIPService._complete_ip("1.2.3.4")
    assert ip == "1.2.3.4"


# ---------------------------------------------------------------------------
# _is_valid_ip
# ---------------------------------------------------------------------------

def test_is_valid_ip_typical_addresses():
    assert GeoIPService._is_valid_ip("192.168.1.1") is True
    assert GeoIPService._is_valid_ip("0.0.0.0") is True
    assert GeoIPService._is_valid_ip("255.255.255.255") is True
    assert GeoIPService._is_valid_ip("10.0.0.1") is True


def test_is_valid_ip_rejects_out_of_range():
    assert GeoIPService._is_valid_ip("256.0.0.0") is False
    assert GeoIPService._is_valid_ip("999.999.999.999") is False


def test_is_valid_ip_rejects_malformed():
    assert GeoIPService._is_valid_ip("1.2.3") is False
    assert GeoIPService._is_valid_ip("abc.def.ghi.jkl") is False
    assert GeoIPService._is_valid_ip("") is False
    assert GeoIPService._is_valid_ip("1.2.3.4.5") is False
