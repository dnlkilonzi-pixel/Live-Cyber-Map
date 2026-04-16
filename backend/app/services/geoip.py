"""In-memory GeoIP service.

All geographic data is stored in-memory — no external database files required.
Provides country lookup, random IP generation per country, and enrichment helpers.
"""

from __future__ import annotations

import random
import re
from typing import Dict, List, Optional


class GeoIPService:
    """Resolves IP addresses to geographic locations using an in-memory dataset.

    The dataset contains ~50 countries with realistic (but fake) IP prefixes
    that are only used for simulation purposes.
    """

    # ------------------------------------------------------------------
    # Country data: {country_code: {name, lat, lng, prefixes}}
    # Each prefix is a /8 or /16-style stub used to construct fake IPs.
    # ------------------------------------------------------------------
    _COUNTRIES: Dict[str, Dict] = {
        "US": {
            "name": "United States",
            "country_code": "US",
            "lat": 37.09,
            "lng": -95.71,
            "prefixes": [
                "8.8",
                "17.0",
                "23.0",
                "34.0",
                "52.0",
                "54.0",
                "104.16",
                "192.168",
                "198.51",
                "203.0",
            ],
        },
        "CN": {
            "name": "China",
            "country_code": "CN",
            "lat": 35.86,
            "lng": 104.19,
            "prefixes": [
                "1.180",
                "27.0",
                "36.0",
                "58.0",
                "60.0",
                "101.0",
                "111.0",
                "114.0",
                "116.0",
                "119.0",
            ],
        },
        "RU": {
            "name": "Russia",
            "country_code": "RU",
            "lat": 61.52,
            "lng": 105.31,
            "prefixes": [
                "5.8",
                "31.13",
                "46.0",
                "77.0",
                "83.0",
                "95.0",
                "185.0",
                "194.0",
                "195.0",
                "213.0",
            ],
        },
        "DE": {
            "name": "Germany",
            "country_code": "DE",
            "lat": 51.16,
            "lng": 10.45,
            "prefixes": [
                "5.35",
                "46.114",
                "78.0",
                "80.0",
                "85.0",
                "91.0",
                "134.0",
                "141.0",
                "145.0",
                "217.0",
            ],
        },
        "GB": {
            "name": "United Kingdom",
            "country_code": "GB",
            "lat": 55.37,
            "lng": -3.43,
            "prefixes": [
                "2.96",
                "5.101",
                "31.55",
                "51.0",
                "62.0",
                "81.0",
                "86.0",
                "92.0",
                "212.0",
                "217.32",
            ],
        },
        "FR": {
            "name": "France",
            "country_code": "FR",
            "lat": 46.22,
            "lng": 2.21,
            "prefixes": [
                "2.12",
                "5.187",
                "37.0",
                "78.192",
                "82.0",
                "90.0",
                "176.0",
                "194.2",
                "213.32",
                "217.108",
            ],
        },
        "BR": {
            "name": "Brazil",
            "country_code": "BR",
            "lat": -14.23,
            "lng": -51.92,
            "prefixes": [
                "18.228",
                "45.160",
                "138.97",
                "143.0",
                "177.0",
                "179.0",
                "186.0",
                "187.0",
                "189.0",
                "200.0",
            ],
        },
        "IN": {
            "name": "India",
            "country_code": "IN",
            "lat": 20.59,
            "lng": 78.96,
            "prefixes": [
                "1.6",
                "14.0",
                "27.116",
                "43.0",
                "49.0",
                "59.90",
                "103.0",
                "106.0",
                "115.0",
                "117.0",
            ],
        },
        "JP": {
            "name": "Japan",
            "country_code": "JP",
            "lat": 36.20,
            "lng": 138.25,
            "prefixes": [
                "1.72",
                "14.128",
                "27.80",
                "43.240",
                "49.96",
                "60.32",
                "101.128",
                "106.128",
                "110.0",
                "122.0",
            ],
        },
        "KR": {
            "name": "South Korea",
            "country_code": "KR",
            "lat": 35.90,
            "lng": 127.76,
            "prefixes": [
                "1.208",
                "14.32",
                "27.96",
                "39.0",
                "49.144",
                "58.224",
                "61.32",
                "110.32",
                "118.32",
                "121.128",
            ],
        },
        "AU": {
            "name": "Australia",
            "country_code": "AU",
            "lat": -25.27,
            "lng": 133.77,
            "prefixes": [
                "1.128",
                "14.192",
                "27.32",
                "43.224",
                "49.176",
                "58.160",
                "101.160",
                "103.0",
                "110.144",
                "121.0",
            ],
        },
        "CA": {
            "name": "Canada",
            "country_code": "CA",
            "lat": 56.13,
            "lng": -106.34,
            "prefixes": [
                "24.0",
                "47.0",
                "64.0",
                "66.0",
                "70.0",
                "99.0",
                "142.0",
                "174.0",
                "184.0",
                "206.0",
            ],
        },
        "NL": {
            "name": "Netherlands",
            "country_code": "NL",
            "lat": 52.13,
            "lng": 5.29,
            "prefixes": [
                "5.57",
                "31.0",
                "37.32",
                "45.0",
                "62.163",
                "82.161",
                "109.0",
                "145.0",
                "185.107",
                "194.109",
            ],
        },
        "IL": {
            "name": "Israel",
            "country_code": "IL",
            "lat": 31.04,
            "lng": 34.85,
            "prefixes": [
                "5.22",
                "31.154",
                "46.116",
                "77.124",
                "79.176",
                "84.228",
                "89.138",
                "91.108",
                "194.90",
                "212.143",
            ],
        },
        "IR": {
            "name": "Iran",
            "country_code": "IR",
            "lat": 32.42,
            "lng": 53.68,
            "prefixes": [
                "2.144",
                "5.52",
                "37.98",
                "46.224",
                "78.38",
                "79.127",
                "82.99",
                "91.98",
                "185.55",
                "194.225",
            ],
        },
        "KP": {
            "name": "North Korea",
            "country_code": "KP",
            "lat": 40.33,
            "lng": 127.51,
            "prefixes": ["175.45", "210.52"],
        },
        "UA": {
            "name": "Ukraine",
            "country_code": "UA",
            "lat": 48.37,
            "lng": 31.16,
            "prefixes": [
                "5.58",
                "31.28",
                "37.52",
                "46.98",
                "77.52",
                "91.196",
                "109.86",
                "176.36",
                "185.65",
                "213.156",
            ],
        },
        "PL": {
            "name": "Poland",
            "country_code": "PL",
            "lat": 51.91,
            "lng": 19.14,
            "prefixes": [
                "5.173",
                "31.60",
                "37.44",
                "46.204",
                "83.0",
                "89.64",
                "109.173",
                "145.128",
                "178.235",
                "213.25",
            ],
        },
        "IT": {
            "name": "Italy",
            "country_code": "IT",
            "lat": 41.87,
            "lng": 12.56,
            "prefixes": [
                "2.32",
                "5.90",
                "37.160",
                "46.36",
                "79.16",
                "82.56",
                "87.0",
                "93.32",
                "151.0",
                "213.192",
            ],
        },
        "ES": {
            "name": "Spain",
            "country_code": "ES",
            "lat": 40.46,
            "lng": -3.74,
            "prefixes": [
                "2.136",
                "5.56",
                "37.36",
                "46.27",
                "80.32",
                "83.44",
                "88.0",
                "95.16",
                "176.64",
                "213.97",
            ],
        },
        "MX": {
            "name": "Mexico",
            "country_code": "MX",
            "lat": 23.63,
            "lng": -102.55,
            "prefixes": [
                "5.189",
                "31.222",
                "45.167",
                "77.219",
                "131.0",
                "148.0",
                "177.240",
                "187.128",
                "189.128",
                "201.0",
            ],
        },
        "AR": {
            "name": "Argentina",
            "country_code": "AR",
            "lat": -38.41,
            "lng": -63.61,
            "prefixes": [
                "23.129",
                "45.164",
                "131.108",
                "138.0",
                "143.0",
                "177.32",
                "181.0",
                "186.128",
                "190.0",
                "200.32",
            ],
        },
        "SE": {
            "name": "Sweden",
            "country_code": "SE",
            "lat": 60.12,
            "lng": 18.64,
            "prefixes": [
                "5.44",
                "31.208",
                "46.246",
                "78.64",
                "81.228",
                "85.224",
                "90.224",
                "178.73",
                "194.140",
                "217.209",
            ],
        },
        "NO": {
            "name": "Norway",
            "country_code": "NO",
            "lat": 60.47,
            "lng": 8.46,
            "prefixes": [
                "2.148",
                "37.18",
                "46.9",
                "78.91",
                "81.0",
                "84.202",
                "88.86",
                "178.164",
                "193.0",
                "217.144",
            ],
        },
        "FI": {
            "name": "Finland",
            "country_code": "FI",
            "lat": 61.92,
            "lng": 25.74,
            "prefixes": [
                "5.100",
                "37.233",
                "46.163",
                "78.27",
                "82.102",
                "87.92",
                "91.152",
                "185.28",
                "193.65",
                "217.30",
            ],
        },
        "RO": {
            "name": "Romania",
            "country_code": "RO",
            "lat": 45.94,
            "lng": 24.96,
            "prefixes": [
                "5.12",
                "31.14",
                "37.120",
                "46.97",
                "79.112",
                "86.32",
                "89.32",
                "109.163",
                "188.24",
                "213.233",
            ],
        },
        "CZ": {
            "name": "Czech Republic",
            "country_code": "CZ",
            "lat": 49.81,
            "lng": 15.47,
            "prefixes": [
                "2.56",
                "31.30",
                "37.188",
                "46.13",
                "77.75",
                "81.19",
                "85.160",
                "109.81",
                "185.8",
                "217.197",
            ],
        },
        "TR": {
            "name": "Turkey",
            "country_code": "TR",
            "lat": 38.96,
            "lng": 35.24,
            "prefixes": [
                "5.24",
                "31.223",
                "37.75",
                "78.160",
                "85.96",
                "88.228",
                "176.220",
                "185.76",
                "193.140",
                "213.14",
            ],
        },
        "PK": {
            "name": "Pakistan",
            "country_code": "PK",
            "lat": 30.37,
            "lng": 69.34,
            "prefixes": [
                "5.62",
                "27.255",
                "39.32",
                "43.224",
                "58.27",
                "103.240",
                "110.93",
                "113.196",
                "119.152",
                "122.168",
            ],
        },
        "NG": {
            "name": "Nigeria",
            "country_code": "NG",
            "lat": 9.08,
            "lng": 8.67,
            "prefixes": [
                "41.58",
                "41.73",
                "41.184",
                "41.203",
                "105.0",
                "154.0",
                "156.0",
                "197.0",
                "212.60",
                "41.138",
            ],
        },
        "ZA": {
            "name": "South Africa",
            "country_code": "ZA",
            "lat": -30.55,
            "lng": 22.93,
            "prefixes": [
                "41.0",
                "105.224",
                "154.0",
                "160.0",
                "162.0",
                "165.0",
                "196.0",
                "197.80",
                "212.0",
                "41.56",
            ],
        },
        "KE": {
            "name": "Kenya",
            "country_code": "KE",
            "lat": -0.02,
            "lng": 37.90,
            "prefixes": [
                "41.139",
                "41.204",
                "105.160",
                "154.122",
                "196.200",
                "197.136",
                "212.22",
                "41.206",
                "197.148",
                "41.174",
            ],
        },
        "EG": {
            "name": "Egypt",
            "country_code": "EG",
            "lat": 26.82,
            "lng": 30.80,
            "prefixes": [
                "41.33",
                "80.76",
                "88.84",
                "196.202",
                "197.32",
                "62.240",
                "78.54",
                "213.128",
                "41.35",
                "197.34",
            ],
        },
        "SA": {
            "name": "Saudi Arabia",
            "country_code": "SA",
            "lat": 23.88,
            "lng": 45.07,
            "prefixes": [
                "5.1",
                "31.224",
                "37.164",
                "46.51",
                "78.140",
                "82.148",
                "91.74",
                "185.115",
                "212.30",
                "213.210",
            ],
        },
        "AE": {
            "name": "UAE",
            "country_code": "AE",
            "lat": 23.42,
            "lng": 53.84,
            "prefixes": [
                "5.36",
                "31.192",
                "37.186",
                "46.235",
                "78.100",
                "82.196",
                "89.32",
                "185.93",
                "212.26",
                "213.42",
            ],
        },
        "SG": {
            "name": "Singapore",
            "country_code": "SG",
            "lat": 1.35,
            "lng": 103.81,
            "prefixes": [
                "1.32",
                "14.0",
                "27.124",
                "43.252",
                "49.228",
                "58.185",
                "101.96",
                "103.252",
                "110.164",
                "116.192",
            ],
        },
        "ID": {
            "name": "Indonesia",
            "country_code": "ID",
            "lat": -0.78,
            "lng": 113.92,
            "prefixes": [
                "1.32",
                "14.224",
                "27.108",
                "36.64",
                "43.248",
                "49.204",
                "103.0",
                "110.136",
                "114.122",
                "118.96",
            ],
        },
        "TH": {
            "name": "Thailand",
            "country_code": "TH",
            "lat": 15.87,
            "lng": 100.99,
            "prefixes": [
                "1.0",
                "14.208",
                "27.100",
                "49.228",
                "58.9",
                "101.108",
                "103.28",
                "110.168",
                "113.53",
                "118.172",
            ],
        },
        "VN": {
            "name": "Vietnam",
            "country_code": "VN",
            "lat": 14.05,
            "lng": 108.27,
            "prefixes": [
                "1.52",
                "14.160",
                "27.64",
                "42.112",
                "58.186",
                "101.0",
                "103.0",
                "113.160",
                "116.100",
                "125.234",
            ],
        },
        "PH": {
            "name": "Philippines",
            "country_code": "PH",
            "lat": 12.87,
            "lng": 121.77,
            "prefixes": [
                "1.20",
                "14.96",
                "27.112",
                "43.232",
                "49.144",
                "58.68",
                "103.2",
                "110.54",
                "112.198",
                "120.28",
            ],
        },
        "NZ": {
            "name": "New Zealand",
            "country_code": "NZ",
            "lat": -40.90,
            "lng": 174.88,
            "prefixes": [
                "1.40",
                "14.0",
                "43.228",
                "49.240",
                "58.28",
                "101.98",
                "103.12",
                "110.52",
                "118.90",
                "121.96",
            ],
        },
        "CH": {
            "name": "Switzerland",
            "country_code": "CH",
            "lat": 46.81,
            "lng": 8.22,
            "prefixes": [
                "5.148",
                "31.10",
                "46.14",
                "77.56",
                "81.62",
                "85.0",
                "91.198",
                "178.194",
                "194.150",
                "217.26",
            ],
        },
        "AT": {
            "name": "Austria",
            "country_code": "AT",
            "lat": 47.51,
            "lng": 14.55,
            "prefixes": [
                "5.28",
                "31.18",
                "37.191",
                "46.16",
                "78.41",
                "80.108",
                "87.160",
                "91.115",
                "178.190",
                "213.164",
            ],
        },
        "BE": {
            "name": "Belgium",
            "country_code": "BE",
            "lat": 50.50,
            "lng": 4.46,
            "prefixes": [
                "2.8",
                "31.5",
                "37.62",
                "46.20",
                "81.82",
                "83.100",
                "91.183",
                "176.224",
                "194.78",
                "212.239",
            ],
        },
        "PT": {
            "name": "Portugal",
            "country_code": "PT",
            "lat": 39.39,
            "lng": -8.22,
            "prefixes": [
                "2.80",
                "31.4",
                "37.98",
                "46.47",
                "78.130",
                "82.10",
                "85.241",
                "91.207",
                "176.79",
                "194.65",
            ],
        },
        "DK": {
            "name": "Denmark",
            "country_code": "DK",
            "lat": 56.26,
            "lng": 9.50,
            "prefixes": [
                "2.104",
                "31.3",
                "37.230",
                "46.30",
                "77.66",
                "80.62",
                "87.48",
                "109.238",
                "185.38",
                "212.242",
            ],
        },
        "HU": {
            "name": "Hungary",
            "country_code": "HU",
            "lat": 47.16,
            "lng": 19.50,
            "prefixes": [
                "2.50",
                "31.46",
                "37.191",
                "46.107",
                "78.92",
                "80.98",
                "89.132",
                "176.52",
                "188.142",
                "213.169",
            ],
        },
        "MY": {
            "name": "Malaysia",
            "country_code": "MY",
            "lat": 4.21,
            "lng": 101.97,
            "prefixes": [
                "1.8",
                "14.192",
                "27.104",
                "43.244",
                "49.236",
                "58.26",
                "103.0",
                "110.140",
                "115.132",
                "120.188",
            ],
        },
        "TW": {
            "name": "Taiwan",
            "country_code": "TW",
            "lat": 23.69,
            "lng": 120.96,
            "prefixes": [
                "1.160",
                "14.0",
                "27.96",
                "42.0",
                "49.159",
                "58.80",
                "101.0",
                "103.30",
                "111.0",
                "114.33",
            ],
        },
        "HK": {
            "name": "Hong Kong",
            "country_code": "HK",
            "lat": 22.39,
            "lng": 114.10,
            "prefixes": [
                "1.36",
                "14.0",
                "27.112",
                "43.248",
                "58.176",
                "103.16",
                "110.176",
                "116.48",
                "118.140",
                "122.100",
            ],
        },
    }

    def __init__(self) -> None:
        self._country_codes: List[str] = list(self._COUNTRIES.keys())
        # Pre-build a prefix → country_code lookup for fast IP resolution
        self._prefix_map: Dict[str, str] = {}
        for code, info in self._COUNTRIES.items():
            for prefix in info["prefixes"]:
                self._prefix_map[prefix] = code

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(self, ip: str) -> Dict:
        """Return geographic info for *ip*.

        Matching is done by longest prefix match against the in-memory table.
        Falls back to the United States if no prefix matches.
        """
        country_code = self._resolve_country_code(ip)
        country = self._COUNTRIES[country_code]
        # Add small jitter so map pins don't stack on the same point
        lat_jitter = random.uniform(-2.0, 2.0)
        lng_jitter = random.uniform(-2.0, 2.0)
        return {
            "lat": round(country["lat"] + lat_jitter, 4),
            "lng": round(country["lng"] + lng_jitter, 4),
            "country": country["name"],
            "country_code": country_code,
        }

    def get_random_ip_for_country(self, country_code: str) -> str:
        """Return a random fake IP that looks like it belongs to *country_code*."""
        country = self._COUNTRIES.get(country_code, self._COUNTRIES["US"])
        prefix = random.choice(country["prefixes"])
        return self._complete_ip(prefix)

    def get_random_country(self) -> Dict:
        """Return a random country dict."""
        code = random.choice(self._country_codes)
        return self._COUNTRIES[code].copy()

    def get_random_ip(self) -> str:
        """Return a random IP from any country in the dataset."""
        code = random.choice(self._country_codes)
        return self.get_random_ip_for_country(code)

    def get_country_info(self, country_code: str) -> Optional[Dict]:
        """Return the full country dict or None if not found."""
        return self._COUNTRIES.get(country_code)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_country_code(self, ip: str) -> str:
        """Find the best-matching country for *ip* via prefix lookup."""
        parts = ip.split(".")
        # Try /16 prefix first (e.g. "192.168"), then /8 (e.g. "192")
        for depth in (2, 1):
            prefix = ".".join(parts[:depth])
            if prefix in self._prefix_map:
                return self._prefix_map[prefix]
        return "US"  # default fallback

    @staticmethod
    def _complete_ip(prefix: str) -> str:
        """Fill remaining octets with random values to form a complete IPv4."""
        octets = prefix.split(".")
        while len(octets) < 4:
            octets.append(str(random.randint(1, 254)))
        return ".".join(octets)

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        pattern = re.compile(
            r"^(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
            r"(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
            r"(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
            r"(25[0-5]|2[0-4]\d|[01]?\d\d?)$"
        )
        return bool(pattern.match(ip))


# Module-level singleton
geoip_service = GeoIPService()
