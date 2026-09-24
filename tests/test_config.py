import os
import yaml
from tempfile import NamedTemporaryFile
from tests.conftest import TEST_CONFIG_PATH
from bbot_server.config import BBOT_SERVER_CONFIG as bbcfg
from bbot_server.config import BBOTServerSettings


def test_name_setting_is_persisted(monkeypatch, tmp_path):
    import bbot_server.config as config_module

    config_file = tmp_path / "config.yml"
    config_file.write_text("name: BBOT Server\n")
    monkeypatch.setattr(config_module, "BBOT_SERVER_CONFIG_PATH", config_file)
    settings = BBOTServerSettings(config_path=config_file)

    settings.set_name("Acme Security")

    assert settings.name == "Acme Security"
    assert yaml.safe_load(config_file.read_text())["name"] == "Acme Security"


def test_config():
    os.environ["BBOT_SERVER_URL"] = "http://asdf:8000"
    bbcfg.refresh()
    assert bbcfg.url == "http://asdf:8000"
    assert bbcfg.event_store.uri == "mongodb://localhost:27017/test_bbot"

    os.environ["BBOT_SERVER_URL"] = "http://fdsa:8000"
    bbcfg.refresh()
    assert bbcfg.url == "http://fdsa:8000"
    assert bbcfg.event_store.uri == "mongodb://localhost:27017/test_bbot"

    tmp_config_file = NamedTemporaryFile(suffix=".yml")
    with open(tmp_config_file.name, "w") as f:
        f.write("""
url: http://qwer:8000
asset_store:
  uri: mongodb://localhost:27017/asdf
""")
    bbcfg.refresh(config_path=tmp_config_file.name)

    # should still be fdsa because of the env var, which takes precedence
    assert bbcfg.url == "http://fdsa:8000"
    # asset store uri should be overridden
    assert bbcfg.asset_store.uri == "mongodb://localhost:27017/asdf"
    # others should be untouched
    assert bbcfg.event_store.uri == "mongodb://localhost:27017/bbot"

    # everything should be the same after a refresh
    bbcfg.refresh()
    assert bbcfg.url == "http://fdsa:8000"
    assert bbcfg.asset_store.uri == "mongodb://localhost:27017/asdf"
    assert bbcfg.event_store.uri == "mongodb://localhost:27017/bbot"

    # reset back to testing defaults
    os.environ.pop("BBOT_SERVER_URL", None)
    bbcfg.refresh(config_path=TEST_CONFIG_PATH)
    assert bbcfg.url == "http://localhost:8807/v1/"
    assert bbcfg.event_store.uri == "mongodb://localhost:27017/test_bbot"
