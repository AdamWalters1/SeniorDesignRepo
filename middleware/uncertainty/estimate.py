"""Initial uncertainty policy for proof-of-concept data."""

from __future__ import annotations

from math import sqrt

SPEED_OF_LIGHT_MPS = 299_792_458.0


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


def range_resolution_m(bandwidth_hz: float) -> float:
    """Return the smallest distance a radar can separate: c / (2 * bandwidth).

    Two objects closer together than this blur into one detection. It is used
    as the range uncertainty because each measured distance can be off by up to
    about one resolution cell. It covers range only, not direction.
    """
    if bandwidth_hz <= 0:
        raise ValueError("Bandwidth must be positive")
    return round(SPEED_OF_LIGHT_MPS / (2 * bandwidth_hz), 2)