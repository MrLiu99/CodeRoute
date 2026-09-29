import json


def read_config(text):
    """Parse JSON configuration text; blank input should mean an empty config."""
    return json.loads(text)
