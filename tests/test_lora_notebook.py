import json
from pathlib import Path

from ops_assist.memory import SECRET

NOTEBOOK = Path(__file__).resolve().parents[1] / "ateliers/24-lora/lora_alert_classifier.ipynb"


def test_lora_notebook_is_valid_and_has_no_outputs():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code, "the notebook must contain code cells"
    for cell in code:
        assert cell["outputs"] == [] and cell["execution_count"] is None
    source = "".join("".join(c["source"]) for c in nb["cells"])
    assert "transformers==" in source and "peft==" in source, "versions must be pinned"
    assert "make_dataset" in source
    assert "API_KEY=" not in source, "no key in the notebook"
    assert not SECRET.search(source)
