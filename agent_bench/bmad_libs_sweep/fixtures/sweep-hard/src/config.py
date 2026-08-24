"""Configuration module."""

DEFAULT_CONFIG = {
    "default_limit": 100,
    "rate_window": 60,
}

def load_config(path):
    """Load config from YAML. Deprecated: use new schema after story 3-1."""
    return DEFAULT_CONFIG
