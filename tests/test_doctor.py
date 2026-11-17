import json
import subprocess

import pytest

from ops_assist import cli
from ops_assist.doctor import Probes, diagnose


class Fake(Probes):
    def __init__(self, system="Linux", machine="x86_64", gpu=False):
        self.os = system, machine
        self.gpu = gpu
        self.calls = []

    def system(self):
        return self.os

    def cpu_count(self):
        return 8

    def processor(self):
        return "fictional cpu"

    def read(self, path):
        if path.endswith("cpuinfo"):
            return "model name : fictional cpu\n"
        return "MemTotal: 16000000 kB\nMemAvailable: 8000000 kB\n"

    def which(self, name):
        assert name == "nvidia-smi"
        return "/fake/nvidia-smi" if self.gpu else None

    def run(self, args):
        self.calls.append(args)
        if args[0] == "sysctl":
            return "16000000000" if args[-1] == "hw.memsize" else "fictional silicon"
        if "memory.free" in args[1]:
            return "8000 MiB\n"
        return "fictional gpu, 10000 MiB\n"


def test_linux_cpu_ram_no_gpu_and_local():
    result = diagnose(Fake())
    assert result["cpu"] == {"count": 8, "model": "fictional cpu"}
    assert result["ram"] == {"total_bytes": 16384000000, "available_bytes": 8192000000}
    assert result["gpu"]["status"] == "none"
    assert result["advice"]["profile"] == "local"
    assert "0.5–0.6 GB" in result["advice"]["reason"] and "6.2 GB" in result["advice"]["reason"]


def test_gpu_uses_free_not_total_and_exact_queries():
    fake = Fake(gpu=True)
    result = diagnose(fake)
    assert result["gpu"] == {
        "status": "gpu",
        "name": "fictional gpu",
        "total_bytes": 10000 * 1024**2,
        "free_bytes": 8000 * 1024**2,
    }
    assert result["advice"]["profile"] == "local"
    assert fake.calls == [
        ["/fake/nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        ["/fake/nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader"],
    ]
    original = fake.run
    fake.run = lambda args: "100 MiB\n" if "memory.free" in args[1] else original(args)
    assert diagnose(fake)["advice"]["profile"] == "api"


def test_apple_unified_and_macos_intel():
    result = diagnose(Fake("Darwin", "arm64"))
    assert result["cpu"]["model"] == "fictional silicon"
    assert result["ram"]["total_bytes"] == 16000000000
    assert result["gpu"]["status"] == "unified"
    assert result["advice"]["profile"] == "api"
    assert "unknown" in result["ram"]["available_bytes"]
    assert diagnose(Fake("Darwin", "x86_64"))["gpu"]["status"] == "none"


@pytest.mark.parametrize(
    "error", [OSError("denied"), subprocess.TimeoutExpired("fake", 2), ValueError("bad")]
)
def test_gpu_failure_is_unknown_and_no_optimistic_advice(error):
    fake = Fake(gpu=True)

    def fail(args):
        raise error

    fake.run = fail
    result = diagnose(fake)
    assert result["gpu"]["status"] == "unknown"
    assert type(error).__name__ in result["gpu"]["name"]
    assert result["advice"]["profile"] == "api"


def test_individual_probe_failures_and_unsupported():
    fake = Fake()

    def fail(*args):
        raise OSError("denied")

    fake.read = fake.cpu_count = fake.which = fail
    result = diagnose(fake)
    assert all(
        "denied" in str(value)
        for value in [
            result["cpu"]["count"],
            result["cpu"]["model"],
            result["ram"]["total_bytes"],
            result["ram"]["available_bytes"],
            result["gpu"]["name"],
        ]
    )
    result = diagnose(Fake("Other"))
    assert "unsupported" in result["ram"]["total_bytes"]
    assert result["cpu"]["model"] == "fictional cpu"
    assert result["advice"]["profile"] == "api"


def test_cli_output_without_settings(monkeypatch, capsys):
    import ops_assist.doctor as doctor

    monkeypatch.setattr(doctor, "Probes", Fake)
    monkeypatch.setenv("OPS_ASSIST_PROFILE", "invalid")
    assert cli.main(["doctor", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["advice"]["profile"] == "local"
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert all(x in out for x in ["CPU:", "RAM total bytes:", "GPU:", "Recommended profile: local"])


def test_multiple_gpus_selects_one_device_and_rejects_invalid_output():
    fake = Fake(gpu=True)
    fake.run = lambda args: (
        "1000 MiB\n8000 MiB\n"
        if "memory.free" in args[1]
        else "first, 10000 MiB\nsecond, 9000 MiB\n"
    )
    result = diagnose(fake)
    assert result["gpu"]["name"] == "second"
    assert result["gpu"]["total_bytes"] == 9000 * 1024**2
    assert result["advice"]["profile"] == "local"
    fake.run = lambda args: "invalid"
    result = diagnose(fake)
    assert result["gpu"]["status"] == "unknown"
    assert "ValueError" in result["gpu"]["name"]


def test_platform_failure_preserves_reason():
    fake = Fake()

    def fail():
        raise OSError("platform unavailable")

    fake.system = fail
    result = diagnose(fake)
    assert "platform unavailable" in result["ram"]["total_bytes"]
    assert result["advice"]["profile"] == "api"
