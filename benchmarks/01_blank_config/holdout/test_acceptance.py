import json
import pytest
from config_reader import read_config

@pytest.mark.parametrize('text', [' ', '\n\t', '  \n'])
def test_whitespace(text):
    assert read_config(text) == {}

def test_invalid():
    with pytest.raises(json.JSONDecodeError): read_config('bad')
