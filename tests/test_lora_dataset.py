import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "ateliers/24-lora/make_dataset.py"
spec = importlib.util.spec_from_file_location("make_dataset", PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_dataset_is_deterministic_disjoint_and_uses_replay():
    data = module.make_dataset()
    assert data == module.make_dataset()
    assert len(data["train"]) == 21
    assert len(data["test"]) == 7
    train = {row["text"] for row in data["train"]}
    test = {row["text"] for row in data["test"]}
    assert len(train) == 21 and len(test) == 7 and train.isdisjoint(test)
    assert {row["label"] for row in data["train"]} == {
        "http_errors",
        "cache_misses",
        "tls_failures",
        "disk_usage",
        "latency",
    }
    assert {row["label"] for row in data["test"]} == {row["label"] for row in data["train"]}
    assert any("TLSHandshakeFailuresHigh" in row["text"] for row in data["test"])
    assert all(set(row) == {"text", "label"} for rows in data.values() for row in rows)


def test_dataset_command_outputs_json():
    result = subprocess.run([sys.executable, str(PATH)], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == module.make_dataset()
