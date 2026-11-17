"""Offline release, deployment and scripted demonstration checks."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def manifest(path):
    return yaml.safe_load((ROOT / path).read_text())


def test_deployment_manifests_are_consistent_and_restricted():
    dep = manifest("deploy/k8s/deployment.yaml")
    service = manifest("deploy/k8s/service.yaml")
    policy = manifest("deploy/k8s/networkpolicy.yaml")
    pod = dep["spec"]["template"]
    spec = pod["spec"]
    container = spec["containers"][0]
    assert dep["apiVersion"] == "apps/v1" and dep["kind"] == "Deployment"
    assert dep["spec"]["selector"]["matchLabels"] == pod["metadata"]["labels"]
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["runAsUser"] == 10001
    assert spec["automountServiceAccountToken"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["env"][0]["valueFrom"]["secretKeyRef"]["key"] == "token"
    assert spec["volumes"][0]["emptyDir"] == {}
    assert service["kind"] == "Service"
    assert service["spec"]["selector"] == pod["metadata"]["labels"]
    assert service["spec"]["ports"][0]["targetPort"] == 8080
    assert policy["kind"] == "NetworkPolicy"
    assert policy["spec"]["podSelector"]["matchLabels"] == pod["metadata"]["labels"]
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert policy["spec"]["egress"] == []
    assert policy["spec"]["ingress"][0]["ports"][0]["port"] == 8080
    cloud = manifest("deploy/cloudrun/service.yaml")
    assert cloud["metadata"]["annotations"]["run.googleapis.com/ingress"] == "internal"
    cloud_container = cloud["spec"]["template"]["spec"]["containers"][0]
    assert cloud["apiVersion"] == "serving.knative.dev/v1" and cloud["kind"] == "Service"
    assert cloud_container["env"][0]["valueFrom"]["secretKeyRef"]["key"] == "latest"
    for item in (container, cloud_container):
        assert item["command"] == ["python", "-m", "uvicorn"]
        assert "ops_assist.a2a_server:create_app" in item["args"]
        assert "--factory" in item["args"] and "0.0.0.0" in item["args"]
        assert item["image"] == "example.invalid/ops-assist:1.0.0"


def test_demo_offline_and_simulated(tmp_path):
    (tmp_path / "sitecustomize.py").write_text(
        "import socket\n"
        "def deny(*args, **kwargs): raise AssertionError('network forbidden')\n"
        "socket.socket.connect = deny\n"
        "socket.socket.connect_ex = deny\n"
        "socket.create_connection = deny\n"
    )
    env = os.environ.copy()
    env.update(PYTHONPATH=str(tmp_path), OPS_ASSIST_TEST_ASYNC_TICK="1")
    result = subprocess.run(
        [str(ROOT / "scripts/demo.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    for text in (
        "Injected fictional fault: timeout",
        "Trace: get_logs observed the injected fault",
        "automatically approved",
        "rollback_deployment completed on injected demo client",
        "Trace: get_alerts for inc-2026-0416",
        '"status":"insufficient_data"',
        "metrics and logs have not been examined",
        "no real deployment or causal proof",
    ):
        assert text in result.stdout


def test_release_version_and_workshop():
    import ops_assist

    assert ops_assist.__version__ == "1.0.0"
    workshop = (ROOT / "ateliers/41-de-bout-en-bout/README.md").read_text()
    assert 60 <= len(workshop.splitlines()) <= 120
    assert "chapitre 42" in workshop and "hors ligne" in workshop
    assert (ROOT / "docs/known-limits.md").is_file()
