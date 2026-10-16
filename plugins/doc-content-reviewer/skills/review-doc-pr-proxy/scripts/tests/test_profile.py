import pytest
from scripts import profile


def test_shipped_profile_loads():
    assert profile.load("proxy")["engine"] == "mkdocs"


def test_missing_required_key_fails(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"name": "x"}')
    with pytest.raises(ValueError):
        profile.load(str(bad))
