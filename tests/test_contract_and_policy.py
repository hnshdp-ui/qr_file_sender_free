import json
from pathlib import Path

import pytest

from sender.config import BLOCK_SIZE, LARGE_ZIP_SIZE, MAX_ZIP_SIZE, classify_zip_size


def test_size_policy_boundaries():
    assert classify_zip_size(0).tier == "NORMAL"
    assert classify_zip_size(LARGE_ZIP_SIZE).tier == "NORMAL"
    assert classify_zip_size(LARGE_ZIP_SIZE + 1).tier == "LARGE TRANSFER"
    assert classify_zip_size(MAX_ZIP_SIZE).tier == "LARGE TRANSFER"
    with pytest.raises(ValueError, match="not supported"):
        classify_zip_size(MAX_ZIP_SIZE + 1)


def test_machine_readable_contract_matches_python_defaults():
    contract = json.loads((Path(__file__).parents[1] / "protocol" / "contract.json").read_text())
    assert contract["magic"] == "QFS1"
    assert contract["protocol_version"] == 1
    assert contract["block_size"] == BLOCK_SIZE
    assert contract["qr"]["symbol_size"] == 1200
    assert contract["size_policy"]["max_zip_bytes"] == MAX_ZIP_SIZE
