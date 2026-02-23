"""Dynamic rate calculation using Perlin noise."""

from noise import pnoise1


def calculate_dynamic_rate(
    elapsed_seconds: float,
    base_rate: int,
    min_rate: int,
    max_rate: int,
    time_scale: float = 0.01,
) -> int:
    """
    Calculate dynamic rate using Perlin noise.

    Args:
        elapsed_seconds: Time elapsed since start
        base_rate: Base rate per second
        min_rate: Minimum rate per second
        max_rate: Maximum rate per second
        time_scale: Controls how quickly the rate changes (lower = slower changes)

    Returns:
        Current rate per second
    """
    noise_value = pnoise1(elapsed_seconds * time_scale)
    normalized = (noise_value + 1) / 2
    rate = int(min_rate + normalized * (max_rate - min_rate))
    return rate
