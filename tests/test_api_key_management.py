"""Regression coverage for local key rotation."""

import pytest
import yaml

from bbot_server.errors import BBOTServerValueError


def test_revoke_primary_key_persists_and_preserves_last_key(tmp_path, monkeypatch):
    import bbot_server.config as config_module

    primary = "11111111-1111-1111-1111-111111111111"
    additional = "22222222-2222-2222-2222-222222222222"
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.safe_dump({"api_key": primary, "api_keys": [additional]}))
    monkeypatch.setattr(config_module, "BBOT_SERVER_CONFIG_PATH", config_file)
    config = config_module.BBOTServerSettings()
    config.refresh_api_keys()
    added = config.add_api_key()
    config.refresh()
    assert added in config.get_api_keys()
    config.revoke_api_key(str(added))
    config.revoke_api_key(primary)
    assert config.api_key is None
    assert yaml.safe_load(config_file.read_text()) == {"api_keys": [additional]}
    with pytest.raises(BBOTServerValueError, match="last API key"):
        config.revoke_api_key(additional)
    assert yaml.safe_load(config_file.read_text()) == {"api_keys": [additional]}
