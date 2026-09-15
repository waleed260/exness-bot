"""Small broker-independent recovery policies."""


def backoff_delays(max_attempts, base_seconds, cap_seconds=60):
    """Return bounded exponential delays between reconnect attempts."""
    if max_attempts <= 1:
        return []
    base = max(0.0, float(base_seconds))
    cap = max(base, float(cap_seconds))
    return [min(cap, base * (2 ** index)) for index in range(max_attempts - 1)]
