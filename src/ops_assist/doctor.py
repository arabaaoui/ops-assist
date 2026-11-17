"""Offline hardware probes and conservative profile advice."""

import http.client
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


class Probes:
    """System access kept behind an injectable interface."""

    def system(self):
        """Return the operating system and machine architecture."""
        return platform.system(), platform.machine()

    def cpu_count(self):
        """Return the logical CPU count."""
        return os.cpu_count()

    def processor(self):
        """Return the platform processor name."""
        return platform.processor()

    def read(self, path):
        """Read a local system file."""
        return Path(path).read_text(encoding="utf-8")

    def which(self, name):
        """Find a local executable."""
        return shutil.which(name)

    def run(self, args):
        """Run a bounded local hardware query."""
        return subprocess.run(args, capture_output=True, text=True, check=True, timeout=2).stdout

    def ollama(self):
        """Read a bounded response from the fixed loopback endpoint."""
        connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=2)
        try:
            connection.request("GET", "/api/ps")
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            data = response.read(65537)
            if len(data) > 65536:
                raise ValueError("response too large")
            return json.loads(data)
        finally:
            connection.close()


def _probe(fn):
    try:
        value = fn()
        if value is None or value == "":
            raise ValueError("not reported")
        return value
    except Exception as exc:
        return f"unknown ({type(exc).__name__}: {str(exc)[:200]})"


def _meminfo(probes, key):
    for line in probes.read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == key + ":" and parts[2] == "kB":
            return int(parts[1]) * 1024
    raise ValueError(f"{key} not reported")


def _cpu_model(probes, system):
    if system == "Linux":
        for line in probes.read("/proc/cpuinfo").splitlines():
            if ":" in line and line.split(":", 1)[0].strip() in ("model name", "Hardware"):
                return line.split(":", 1)[1].strip()[:200]
    if system == "Darwin":
        return probes.run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()[:200]
    return probes.processor()


def _gpu(probes, system, machine):
    if system == "Darwin" and machine.lower() in ("arm64", "aarch64"):
        return {
            "status": "unified",
            "name": "Apple Silicon (unified memory)",
            "total_bytes": None,
            "free_bytes": None,
        }
    executable = probes.which("nvidia-smi")
    if not executable:
        return {"status": "none", "name": "none", "total_bytes": None, "free_bytes": None}
    rows = probes.run([executable, "--query-gpu=name,memory.total", "--format=csv,noheader"])
    free_rows = probes.run([executable, "--query-gpu=memory.free", "--format=csv,noheader"])

    def mib(value):
        parts = value.strip().split()
        if len(parts) != 2 or parts[1] != "MiB":
            raise ValueError("invalid GPU memory")
        return int(parts[0]) * 1024**2

    parsed = []
    for row in rows.splitlines():
        name, total = row.rsplit(",", 1)
        parsed.append((name.strip()[:200], mib(total)))
    free = [mib(row) for row in free_rows.splitlines()]
    if not parsed or len(parsed) != len(free) or any(not name for name, _ in parsed):
        raise ValueError("invalid GPU output")
    # A model must fit on one device; do not sum multiple GPUs.
    index = max(range(len(free)), key=free.__getitem__)
    return {
        "status": "gpu",
        "name": parsed[index][0],
        "total_bytes": parsed[index][1],
        "free_bytes": free[index],
    }


def _accelerator(probes, system, machine):
    if system == "Darwin" and machine.lower() in ("arm64", "aarch64"):
        return {"backend": "Metal", "version": "unknown"}
    nvidia = probes.which("nvidia-smi")
    if nvidia:
        output = probes.run([nvidia, "--query-gpu=driver_version", "--format=csv,noheader"])
        versions = output.strip().splitlines()
        if not versions or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", versions[0].strip()):
            raise ValueError("invalid NVIDIA driver version")
        return {"backend": "CUDA", "version": versions[0].strip()[:100]}
    rocm = probes.which("rocm-smi")
    if rocm:
        output = probes.run([rocm, "--showdriverversion"])
        match = re.search(r"Driver version:\s*([^\s]+)", output, re.IGNORECASE)
        if not match:
            raise ValueError("invalid ROCm driver output")
        return {"backend": "ROCm", "version": match.group(1)[:100]}
    return {"backend": "none", "version": "unknown"}


def _ollama_models(probes):
    data = probes.ollama()
    models = data["models"]
    if not isinstance(models, list) or len(models) > 100:
        raise ValueError("invalid model list")
    result = []
    for model in models:
        name, size, vram = model["name"], model["size"], model["size_vram"]
        if (
            not isinstance(name, str)
            or not name
            or type(size) is not int
            or type(vram) is not int
            or size <= 0
            or not 0 <= vram <= size
        ):
            raise ValueError("invalid model data")
        device = "CPU" if vram == 0 else "GPU" if vram == size else "CPU/GPU"
        result.append({"name": name[:200], "device": device, "size": size, "size_vram": vram})
    return result


def diagnose(probes=None, *, ollama=False):
    """Return bounded hardware information and advice; probe failures become unknown."""
    probes = probes or Probes()
    platform_info = _probe(probes.system)
    system, machine = (
        platform_info
        if isinstance(platform_info, tuple) and len(platform_info) == 2
        else (str(platform_info)[:200], "unknown")
    )
    count = _probe(probes.cpu_count)
    model = _probe(lambda: _cpu_model(probes, system))
    if system == "Linux":
        total = _probe(lambda: _meminfo(probes, "MemTotal"))
        available = _probe(lambda: _meminfo(probes, "MemAvailable"))
    elif system == "Darwin":
        total = _probe(lambda: int(probes.run(["sysctl", "-n", "hw.memsize"]).strip()))
        available = "unknown (available RAM is not measured on macOS)"
    else:
        total = available = f"unknown (unsupported system: {str(system)[:100]})"
    gpu = _probe(lambda: _gpu(probes, system, machine))
    if isinstance(gpu, str):
        gpu = {"status": "unknown", "name": gpu, "total_bytes": None, "free_bytes": None}
    accelerator = _probe(lambda: _accelerator(probes, system, machine))
    if isinstance(accelerator, str):
        accelerator = {"backend": "unknown", "version": accelerator}
    ollama_result = _probe(lambda: _ollama_models(probes)) if ollama else "disabled"
    # 7B at 0.6 GB/B plus 2 GB for runtime and context, in decimal bytes.
    required = 6_200_000_000
    memory = gpu["free_bytes"] if gpu["status"] == "gpu" else available
    if gpu["status"] == "unknown":
        memory = None
    fits = isinstance(memory, int) and memory >= required
    reason = (
        "4-bit weights need about 0.5–0.6 GB per billion parameters; "
        "a 7B model needs about 4.2 GB plus 2 GB runtime/context overhead "
        "(6.2 GB total). "
    )
    reason += (
        f"Measured free {'GPU memory' if gpu['status'] == 'gpu' else 'RAM'}: "
        f"{memory / 1e9:.2f} GB. "
        if isinstance(memory, int)
        else "Usable free memory is unknown. "
    )
    reason += (
        "This may fit; speed and actual memory use vary."
        if fits
        else "The estimate does not establish a fit; use an API profile."
    )
    return {
        "cpu": {"count": count, "model": model},
        "ram": {"total_bytes": total, "available_bytes": available},
        "gpu": gpu,
        "accelerator": accelerator,
        "ollama": ollama_result,
        "advice": {"profile": "local" if fits else "api", "reason": reason},
    }
