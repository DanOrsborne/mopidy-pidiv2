from unittest import mock

import pkg_resources

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


def test_get_display_types_supports_legacy_entry_point_group():
    ext = Extension()
    distribution = pkg_resources.Distribution(__file__)
    endpoint = pkg_resources.EntryPoint.parse(
        "dummy = mopidy_pidiv2.plugin:DisplayDummy", dist=distribution
    )

    def iter_entry_points(group):
        if group == "pidi.plugin.display":
            return [endpoint]
        return []

    with mock.patch("pkg_resources.iter_entry_points", side_effect=iter_entry_points):
        display_types = ext.get_display_types()

    assert "dummy" in display_types
