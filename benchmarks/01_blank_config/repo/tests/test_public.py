from config_reader import read_config

def test_blank():
    assert read_config('') == {}

def test_valid():
    assert read_config('{"x": 1}') == {'x': 1}
