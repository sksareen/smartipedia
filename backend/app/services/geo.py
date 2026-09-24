"""Country lookup for article attribution.

The IP is used only in memory, then discarded. What we persist is a two-letter
ISO country code — enough to see where articles are coming from, not enough
to identify a person.

Lookup order:
1. Trusted proxy headers (Cloudflare / CloudFront / Caddy geo), if present
2. Local MaxMind-compatible Country database (never leaves the box)

This product includes GeoLite2 data created by MaxMind, available from
https://www.maxmind.com.
"""

from __future__ import annotations

import contextvars
import ipaddress
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

# Proxy headers that already contain a country code. Checked in order.
_COUNTRY_HEADERS = (
    "cf-ipcountry",
    "cloudfront-viewer-country",
    "x-country-code",
    "x-geo-country",
)

_DB_CANDIDATES = (
    os.environ.get("GEOIP_DB_PATH"),
    "/app/data/GeoLite2-Country.mmdb",
    str(Path(__file__).resolve().parents[3] / "data" / "GeoLite2-Country.mmdb"),
)

_GEOIP_URL = (
    "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/"
    "GeoLite2-Country.mmdb"
)

_reader = None
_reader_failed = False


@dataclass(frozen=True, slots=True)
class Origin:
    country: str | None = None
    client_type: str | None = None
    ua_family: str | None = None
    surface: str | None = None


_origin: contextvars.ContextVar[Origin] = contextvars.ContextVar(
    "request_origin", default=Origin()
)


def current_origin() -> Origin:
    return _origin.get()


def set_origin(origin: Origin) -> contextvars.Token:
    return _origin.set(origin)


def reset_origin(token: contextvars.Token) -> None:
    _origin.reset(token)


def normalize_country(code: str | None) -> str | None:
    """Accept only a two-letter ISO code. 'XX' / 'T1' mean unknown / Tor."""
    if not code:
        return None
    cleaned = code.strip().upper()
    if cleaned in {"XX", "T1", "ZZ"} or not _COUNTRY_RE.match(cleaned):
        return None
    return cleaned


def country_name(code: str | None) -> str | None:
    if not code:
        return None
    return COUNTRY_NAMES.get(code, code)


def country_flag(code: str | None) -> str:
    """Regional-indicator flag emoji, or empty if we don't have a country."""
    if not code or len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code.upper())


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_link_local
        or addr.is_unspecified
    )


def country_from_headers(headers) -> str | None:
    """Read a country code a reverse proxy already computed."""
    getter = headers.get if hasattr(headers, "get") else lambda k: headers.get(k)
    for name in _COUNTRY_HEADERS:
        found = normalize_country(getter(name))
        if found:
            return found
    return None


def ensure_geoip_db() -> Path | None:
    """Return the MMDB path, downloading once if the image wasn't baked with it."""
    for candidate in _DB_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    dest = Path(os.environ.get("GEOIP_DB_PATH") or "/app/data/GeoLite2-Country.mmdb")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        import urllib.request
        log.info("downloading GeoIP country database to %s", dest)
        urllib.request.urlretrieve(_GEOIP_URL, dest)
        if dest.is_file() and dest.stat().st_size > 1000:
            return dest
    except Exception:
        log.exception("GeoIP country database download failed")
    return None


def _get_reader():
    global _reader, _reader_failed
    if _reader is not None or _reader_failed:
        return _reader
    try:
        import maxminddb
    except ImportError:
        _reader_failed = True
        return None
    for candidate in _DB_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            _reader = maxminddb.open_database(str(path))
            return _reader
        except Exception:
            log.exception("failed to open GeoIP database at %s", path)
    _reader_failed = True
    return None


def country_from_ip(ip: str | None) -> str | None:
    if not ip or not _is_public_ip(ip):
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        record = reader.get(ip)
    except Exception:
        return None
    if not record:
        return None
    country = record.get("country") or {}
    return normalize_country(country.get("iso_code"))


def country_for_request(headers, ip: str | None) -> str | None:
    return country_from_headers(headers) or country_from_ip(ip)


# ISO 3166-1 alpha-2 display names. Missing codes fall back to the code itself.
COUNTRY_NAMES: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina",
    "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Åland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso",
    "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi", "BJ": "Benin",
    "BL": "Saint Barthélemy", "BM": "Bermuda", "BN": "Brunei", "BO": "Bolivia",
    "BQ": "Caribbean Netherlands", "BR": "Brazil", "BS": "Bahamas",
    "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus",
    "BZ": "Belize", "CA": "Canada", "CC": "Cocos Islands",
    "CD": "DR Congo", "CF": "Central African Republic", "CG": "Congo",
    "CH": "Switzerland", "CI": "Côte d'Ivoire", "CK": "Cook Islands",
    "CL": "Chile", "CM": "Cameroon", "CN": "China", "CO": "Colombia",
    "CR": "Costa Rica", "CU": "Cuba", "CV": "Cape Verde", "CW": "Curaçao",
    "CX": "Christmas Island", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea",
    "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji",
    "FK": "Falkland Islands", "FM": "Micronesia", "FO": "Faroe Islands",
    "FR": "France", "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada",
    "GE": "Georgia", "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana",
    "GI": "Gibraltar", "GL": "Greenland", "GM": "Gambia", "GN": "Guinea",
    "GP": "Guadeloupe", "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia", "GT": "Guatemala", "GU": "Guam",
    "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard Island", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel",
    "IM": "Isle of Man", "IN": "India", "IO": "British Indian Ocean Territory",
    "IQ": "Iraq", "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JE": "Jersey",
    "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya",
    "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros",
    "KN": "Saint Kitts and Nevis", "KP": "North Korea", "KR": "South Korea",
    "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos",
    "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein",
    "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libya", "MA": "Morocco",
    "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro", "MF": "Saint Martin",
    "MG": "Madagascar", "MH": "Marshall Islands", "MK": "North Macedonia",
    "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia", "MO": "Macao",
    "MP": "Northern Mariana Islands", "MQ": "Martinique", "MR": "Mauritania",
    "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius", "MV": "Maldives",
    "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger", "NF": "Norfolk Island",
    "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands", "NO": "Norway",
    "NP": "Nepal", "NR": "Nauru", "NU": "Niue", "NZ": "New Zealand", "OM": "Oman",
    "PA": "Panama", "PE": "Peru", "PF": "French Polynesia",
    "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PM": "Saint Pierre and Miquelon", "PN": "Pitcairn",
    "PR": "Puerto Rico", "PS": "Palestine", "PT": "Portugal", "PW": "Palau",
    "PY": "Paraguay", "QA": "Qatar", "RE": "Réunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia",
    "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden",
    "SG": "Singapore", "SH": "Saint Helena", "SI": "Slovenia",
    "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia", "SL": "Sierra Leone",
    "SM": "San Marino", "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SS": "South Sudan", "ST": "São Tomé and Príncipe", "SV": "El Salvador",
    "SX": "Sint Maarten", "SY": "Syria", "SZ": "Eswatini",
    "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand",
    "TJ": "Tajikistan", "TK": "Tokelau", "TL": "Timor-Leste",
    "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey",
    "TT": "Trinidad and Tobago", "TV": "Tuvalu", "TW": "Taiwan",
    "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "U.S. Outlying Islands", "US": "United States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Vatican City",
    "VC": "Saint Vincent and the Grenadines", "VE": "Venezuela",
    "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands",
    "VN": "Vietnam", "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa",
    "YE": "Yemen", "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia",
    "ZW": "Zimbabwe",
}
