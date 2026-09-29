import json

import pytest

from config_reader import read_config


@pytest.mark.parametrize("text", ["", " ", "\n\t"])
def test_blank_configuration(text):
    assert read_config(text) == {}


def test_valid_configuration():
    assert read_config('{"enabled": true}') == {"enabled": True}


def test_invalid_json_is_not_silenced():
    with pytest.raises(json.JSONDecodeError):
        read_config("{invalid")
