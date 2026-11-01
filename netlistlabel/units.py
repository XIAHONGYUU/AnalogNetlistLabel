"""Engineering-unit parsing.

Canonical units inside NetlistLabel:

* length: micrometres (um)
* capacitance: picofarads (pF)
* resistance: ohms
* counts (nf, m): integers
"""

from __future__ import annotations

import math
import re

_ENG = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "meg": 1e6,
    "g": 1e9,
    "t": 1e12,
}

_NUMBER_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([a-zA-Z]*)\s*$"
)


def _clean(value: object) -> str:
    return str(value).strip().replace("\u00b5", "u").replace("\u03bc", "u")


def _number_and_suffix(value: object, *, what: str) -> tuple[float, str]:
    text = _clean(value)
    match = _NUMBER_RE.match(text)
    if not match:
        raise ValueError(f"cannot parse {what}: {value!r}")
    return float(match.group(1)), match.group(2).lower()


def parse_eng(value: object, *, what: str = "value") -> float:
    if isinstance(value, bool):
        raise ValueError(f"cannot parse {what} from a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    number, suffix = _number_and_suffix(value, what=what)
    if not suffix:
        return number
    if suffix.startswith("meg"):
        return number * 1e6
    first = suffix[0]
    if first in _ENG:
        return number * _ENG[first]
    # Tolerate trailing units, e.g. "10um", "1.5pF", "2.2kohm".
    if len(suffix) >= 2 and suffix[1] in _ENG:
        return number * _ENG[suffix[1]]
    raise ValueError(f"unknown engineering suffix in {what}: {value!r}")


def parse_length_um(value: object, *, what: str = "length") -> float:
    number, suffix = _number_and_suffix(value, what=what)
    if not suffix:
        return number
    return parse_eng(value, what=what) * 1e6


def parse_cap_pf(value: object, *, what: str = "capacitance") -> float:
    number, suffix = _number_and_suffix(value, what=what)
    if not suffix:
        return number
    return parse_eng(value, what=what) * 1e12


def parse_res_ohm(value: object, *, what: str = "resistance") -> float:
    number, suffix = _number_and_suffix(value, what=what)
    if not suffix:
        return number
    return parse_eng(value, what=what)


def parse_int(value: object, *, what: str = "count", default: int = 1) -> int:
    if value is None or _clean(value) == "":
        return default
    number = parse_eng(value, what=what)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{what} must be a positive number, got {value!r}")
    if abs(number - round(number)) > 1e-9:
        raise ValueError(f"{what} must be an integer, got {value!r}")
    return int(round(number))


def fmt_um(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f} um"


def fmt_area(value_um2: float, digits: int = 1) -> str:
    if value_um2 >= 1e6:
        return f"{value_um2 / 1e6:.{digits}f} mm2"
    return f"{value_um2:.{digits}f} um2"
