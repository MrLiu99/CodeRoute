import json
from dataclasses import asdict, is_dataclass
from pathlib import Path


class Tracer:
    def __init__(self, run_dir):
        self.root = Path(run_dir)
        self.events = []

    def record(self, event):
        self.events.append(event)
        with (self.root / "trajectory.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def save(self, name, data):
        if is_dataclass(data):
            data = asdict(data)
        (self.root / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
