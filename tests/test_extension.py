from unittest import mock

from mopidy_pidiv2 import Extension
from mopidy_pidiv2 import frontend as frontend_lib


def test_get_default_config():
    ext = Extension()

    config = ext.get_default_config()

    assert "[pidiv2]" in config
    assert "enabled = true" in config


def test_get_config_schema():
    ext = Extension()

    schema = ext.get_config_schema()

    assert "display" in schema


def test_setup():
    ext = Extension()
    registry = mock.Mock()

    ext.setup(registry)

    registry.add.assert_called_once_with("frontend", frontend_lib.PiDiV2Frontend)
