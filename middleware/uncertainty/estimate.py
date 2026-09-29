"""Initial uncertainty policy for proof-of-concept data."""

from __future__ import annotations

from math import sqrt


def estimate_uncertainty_m(
    power: float,
    *,
    reference_uncertainty_m: float = 25.0,
    minimum_m: float = 3.0,
    maximum_m: float = 100.0,
) -> float:
    """Return a bounded placeholder estimate based on relative detection power.

    This is a test policy, not a validated radar-error model. It provides a
    varying value for pipeline development and must be replaced or calibrated
    using simulation resolution and ground truth before results are reported.
    """
    if power <= 0:
        return maximum_m
    estimate = reference_uncertainty_m / sqrt(power)
    return round(min(max(estimate, minimum_m), maximum_m), 2)
