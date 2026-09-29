"""Materialize ten small, authored repair fixtures. No model or network calls."""
import json
from pathlib import Path


CASES = [
    ("01_blank_config", "easy", "read_config must return {} for blank or whitespace-only strings. Preserve normal JSON parsing and errors for malformed nonblank input.",
     {"config_reader.py": "import json\n\ndef read_config(text):\n    return json.loads(text)\n"},
     "from config_reader import read_config\n\ndef test_blank():\n    assert read_config('') == {}\n\ndef test_valid():\n    assert read_config('{\"x\": 1}') == {'x': 1}\n",
     "import json\nimport pytest\nfrom config_reader import read_config\n\n@pytest.mark.parametrize('text', [' ', '\\n\\t', '  \\n'])\ndef test_whitespace(text):\n    assert read_config(text) == {}\n\ndef test_invalid():\n    with pytest.raises(json.JSONDecodeError): read_config('bad')\n",
     [("config_reader.py", "    return json.loads(text)", "    if not text.strip():\n        return {}\n    return json.loads(text)")]),
    ("02_zero_bound", "easy", "clamp accepts optional lower/upper bounds. Zero is a valid bound; only None means absent. Preserve values already within bounds.",
     {"bounds.py": "def clamp(value, lower=None, upper=None):\n    if lower and value < lower:\n        value = lower\n    if upper and value > upper:\n        value = upper\n    return value\n"},
     "from bounds import clamp\n\ndef test_zero_lower():\n    assert clamp(-3, lower=0) == 0\n\ndef test_normal():\n    assert clamp(4, 1, 8) == 4\n",
     "from bounds import clamp\n\ndef test_zero_upper():\n    assert clamp(3, upper=0) == 0\n\ndef test_absent():\n    assert clamp(-5) == -5\n\ndef test_negative_bound():\n    assert clamp(-8, lower=-3) == -3\n",
     [("bounds.py", "if lower and", "if lower is not None and"), ("bounds.py", "if upper and", "if upper is not None and")]),
    ("03_pagination", "easy", "page_items uses one-based page numbers. Page 1 starts at the first item. Keep the existing validation for nonpositive page or size, and return [] beyond the end.",
     {"pagination.py": "def page_items(items, page, size):\n    if page < 1 or size < 1:\n        raise ValueError('positive page and size required')\n    start = page * size\n    return items[start:start + size]\n"},
     "from pagination import page_items\n\ndef test_first():\n    assert page_items([1,2,3,4], 1, 2) == [1,2]\n",
     "import pytest\nfrom pagination import page_items\n\ndef test_later():\n    assert page_items([1,2,3,4,5], 3, 2) == [5]\n    assert page_items([1], 4, 2) == []\n\n@pytest.mark.parametrize('page,size', [(0,2),(1,0),(-1,2)])\ndef test_invalid(page,size):\n    with pytest.raises(ValueError): page_items([1], page, size)\n",
     [("pagination.py", "start = page * size", "start = (page - 1) * size")]),
    ("04_mutable_default", "easy", "add_tag must create a fresh list when tags is omitted. When a list is explicitly supplied, append to and return that same list.",
     {"tags.py": "def add_tag(tag, tags=[]):\n    tags.append(tag)\n    return tags\n"},
     "from tags import add_tag\n\ndef test_independent():\n    assert add_tag('a') == ['a']\n    assert add_tag('b') == ['b']\n",
     "from tags import add_tag\n\ndef test_explicit_list():\n    values = ['start']\n    result = add_tag('next', values)\n    assert result is values\n    assert values == ['start', 'next']\n\ndef test_empty_list():\n    values = []\n    assert add_tag('x', values) is values\n",
     [("tags.py", "def add_tag(tag, tags=[]):", "def add_tag(tag, tags=None):\n    if tags is None:\n        tags = []")]),
    ("05_falsey_cache", "medium", "Cache.get_or_compute must return cached values even when they are 0, False, empty string, or None. Compute only for absent keys and cache the computed result.",
     {"cache.py": "class Cache:\n    def __init__(self):\n        self.data = {}\n\n    def get_or_compute(self, key, compute):\n        value = self.data.get(key)\n        if not value:\n            value = compute()\n            self.data[key] = value\n        return value\n"},
     "from cache import Cache\n\ndef test_cached_zero():\n    cache = Cache()\n    cache.data['x'] = 0\n    assert cache.get_or_compute('x', lambda: 99) == 0\n",
     "import pytest\nfrom cache import Cache\n\n@pytest.mark.parametrize('value', [False, '', None])\ndef test_falsey(value):\n    cache = Cache()\n    cache.data['x'] = value\n    def forbidden(): raise AssertionError('computed cached key')\n    assert cache.get_or_compute('x', forbidden) == value\n\ndef test_miss_once():\n    cache = Cache()\n    calls = []\n    def compute():\n        calls.append(1)\n        return 0\n    assert cache.get_or_compute('x', compute) == 0\n    assert cache.get_or_compute('x', compute) == 0\n    assert len(calls) == 1\n",
     [("cache.py", "if not value:", "if key not in self.data:")]),
    ("06_stable_unique", "easy", "unique returns hashable items in first-occurrence order, removes duplicates, and does not modify the input sequence.",
     {"unique.py": "def unique(items):\n    return sorted(set(items))\n"},
     "from unique import unique\n\ndef test_order():\n    assert unique([3,1,3,2]) == [3,1,2]\n",
     "from unique import unique\n\ndef test_mixed():\n    assert unique(['x', 1, 'x', None]) == ['x', 1, None]\n\ndef test_input_preserved():\n    items = [2,1,2]\n    assert unique(items) == [2,1]\n    assert items == [2,1,2]\n    assert unique([]) == []\n",
     [("unique.py", "sorted(set(items))", "list(dict.fromkeys(items))")]),
    ("07_retry_errors", "medium", "retry retries OSError up to attempts total calls, returns the first successful result, and re-raises the last OSError if exhausted. Other exceptions must propagate immediately. attempts below 1 remains invalid.",
     {"retry.py": "def retry(operation, attempts=3):\n    if attempts < 1:\n        raise ValueError('attempts must be positive')\n    for index in range(attempts):\n        try:\n            return operation()\n        except ValueError:\n            if index == attempts - 1:\n                raise\n"},
     "from retry import retry\n\ndef test_transient():\n    calls = []\n    def operation():\n        calls.append(1)\n        if len(calls) == 1: raise OSError('temporary')\n        return 'ok'\n    assert retry(operation) == 'ok'\n    assert len(calls) == 2\n",
     "import pytest\nfrom retry import retry\n\n@pytest.mark.parametrize('error,count', [(OSError,3),(ValueError,1),(TypeError,1)])\ndef test_attempts(error,count):\n    calls=[]\n    def operation():\n        calls.append(1)\n        raise error('broken')\n    with pytest.raises(error): retry(operation,3)\n    assert len(calls)==count\n\ndef test_invalid():\n    with pytest.raises(ValueError): retry(lambda: 1,0)\n",
     [("retry.py", "except ValueError:", "except OSError:")]),
    ("08_weighted_mean", "medium", "weighted_mean divides the sum of value*weight by the sum of weights. Mismatched/empty inputs and a zero total weight must raise ValueError. Zero individual weights are allowed.",
     {"stats.py": "def weighted_mean(values, weights):\n    if len(values) != len(weights) or not values:\n        raise ValueError('nonempty equal lengths required')\n    return sum(v * w for v, w in zip(values, weights)) / len(values)\n"},
     "import pytest\nfrom stats import weighted_mean\n\ndef test_weighted():\n    assert weighted_mean([10,20],[1,3]) == pytest.approx(17.5)\n",
     "import pytest\nfrom stats import weighted_mean\n\n@pytest.mark.parametrize('values,weights', [([],[]),([1],[1,2]),([1,2],[0,0])])\ndef test_invalid(values,weights):\n    with pytest.raises(ValueError): weighted_mean(values,weights)\n\ndef test_zero_item():\n    assert weighted_mean([99,4],[0,2]) == 4\n",
     [("stats.py", "    return sum(v * w", "    if sum(weights) == 0:\n        raise ValueError('zero total weight')\n    return sum(v * w"), ("stats.py", "/ len(values)", "/ sum(weights)")]),
    ("09_invoice_units", "medium", "invoice_total takes item prices in cents and returns total dollars including tax. tax_amount takes dollars and a decimal rate; preserve this helper contract. Empty invoices total zero.",
     {"invoice.py": "from taxes import tax_amount\n\ndef invoice_total(prices_cents, rate):\n    subtotal = sum(prices_cents)\n    return subtotal / 100 + tax_amount(subtotal, rate)\n",
      "taxes.py": "def tax_amount(dollars, rate):\n    return dollars * rate\n"},
     "import pytest\nfrom invoice import invoice_total\n\ndef test_invoice():\n    assert invoice_total([1000,500],0.1) == pytest.approx(16.5)\n",
     "import pytest\nfrom invoice import invoice_total\nfrom taxes import tax_amount\n\ndef test_helper_contract():\n    assert tax_amount(12,0.25) == 3\n\ndef test_totals():\n    assert invoice_total([],0.2) == 0\n    assert invoice_total([199,101],0) == 3\n    assert invoice_total([100],0.2) == pytest.approx(1.2)\n",
     [("invoice.py", "tax_amount(subtotal, rate)", "tax_amount(subtotal / 100, rate)")]),
    ("10_cancel_inventory", "medium", "Inventory.cancel restores the seats from a cancelled booking. Cancelling an unknown or already-cancelled booking is a no-op. Keep booking capacity checks and reject duplicate booking IDs without changing inventory.",
     {"inventory.py": "class Inventory:\n    def __init__(self, capacity):\n        self.available = capacity\n        self.bookings = {}\n\n    def book(self, booking_id, seats):\n        if booking_id in self.bookings or seats < 1 or seats > self.available:\n            raise ValueError('invalid booking')\n        self.bookings[booking_id] = seats\n        self.available -= seats\n\n    def cancel(self, booking_id):\n        seats = self.bookings.pop(booking_id, 0)\n        self.available -= seats\n"},
     "from inventory import Inventory\n\ndef test_restore():\n    inventory=Inventory(5)\n    inventory.book('a',2)\n    inventory.cancel('a')\n    assert inventory.available == 5\n",
     "import pytest\nfrom inventory import Inventory\n\ndef test_multiple_and_repeat():\n    inventory=Inventory(5)\n    inventory.book('a',2)\n    inventory.book('b',1)\n    inventory.cancel('a')\n    inventory.cancel('a')\n    inventory.cancel('unknown')\n    assert inventory.available==4\n    assert inventory.bookings=={'b':1}\n\ndef test_invalid_booking():\n    inventory=Inventory(3)\n    inventory.book('a',2)\n    with pytest.raises(ValueError): inventory.book('a',1)\n    with pytest.raises(ValueError): inventory.book('b',2)\n    assert inventory.available==1\n",
     [("inventory.py", "        seats = self.bookings.pop(booking_id, 0)\n        self.available -= seats", "        seats = self.bookings.pop(booking_id, 0)\n        self.available += seats")]),
]


def generate(root):
    root = Path(root)
    for name, difficulty, issue, sources, visible, hidden, fixes in CASES:
        case = root / name
        repo = case / "repo"
        (repo / "tests").mkdir(parents=True, exist_ok=True)
        (case / "holdout").mkdir(exist_ok=True)
        for path, content in sources.items():
            (repo / path).write_text(content, encoding="utf-8")
        (repo / "tests" / "test_public.py").write_text(visible, encoding="utf-8")
        (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
        (case / "holdout" / "test_acceptance.py").write_text(hidden, encoding="utf-8")
        (case / "issue.txt").write_text(issue, encoding="utf-8")
        (case / "case.json").write_text(json.dumps({"id": name, "difficulty": difficulty,
            "reference_edits": [{"path": p, "old": old, "new": new} for p, old, new in fixes]}, indent=2), encoding="utf-8")
    print(f"Generated {len(CASES)} authored cases at {root}")


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1] / "benchmarks")
