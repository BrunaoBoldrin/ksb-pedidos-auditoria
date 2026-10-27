"""Modelo e validação das configurações administrativas do diagnóstico."""

from dataclasses import dataclass
from math import isfinite


MIN_REVIEW_DAYS = 1
MAX_REVIEW_DAYS = 3650
MIN_TOLERANCE = 0.0
MAX_TOLERANCE = 1_000_000.0


@dataclass(frozen=True)
class SystemSettings:
    price_review_days: int = 90
    price_difference_tolerance: float = 0.01
    fiscal_difference_tolerance: float = 1.0

    def __post_init__(self):
        if (
            isinstance(self.price_review_days, bool)
            or not isinstance(self.price_review_days, int)
            or not MIN_REVIEW_DAYS <= self.price_review_days <= MAX_REVIEW_DAYS
        ):
            raise ValueError("O prazo de revisão deve estar entre 1 e 3650 dias.")
        for value in (self.price_difference_tolerance, self.fiscal_difference_tolerance):
            if not isfinite(value) or not MIN_TOLERANCE <= value <= MAX_TOLERANCE:
                raise ValueError("As tolerâncias devem estar entre 0 e 1.000.000.")


DEFAULT_SYSTEM_SETTINGS = SystemSettings()


def _safe_integer(value, default):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(parsed) or not parsed.is_integer():
        return default
    parsed = int(parsed)
    return parsed if MIN_REVIEW_DAYS <= parsed <= MAX_REVIEW_DAYS else default


def _safe_tolerance(value, default):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if isfinite(parsed) and MIN_TOLERANCE <= parsed <= MAX_TOLERANCE else default


def normalize_system_settings(values=None):
    if isinstance(values, SystemSettings):
        return values
    values = values or {}
    return SystemSettings(
        price_review_days=_safe_integer(
            values.get("price_review_days"), DEFAULT_SYSTEM_SETTINGS.price_review_days
        ),
        price_difference_tolerance=_safe_tolerance(
            values.get("price_difference_tolerance"),
            DEFAULT_SYSTEM_SETTINGS.price_difference_tolerance,
        ),
        fiscal_difference_tolerance=_safe_tolerance(
            values.get("fiscal_difference_tolerance"),
            DEFAULT_SYSTEM_SETTINGS.fiscal_difference_tolerance,
        ),
    )
