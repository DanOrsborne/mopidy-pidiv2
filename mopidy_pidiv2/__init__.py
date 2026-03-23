import logging
import pathlib

import pkg_resources

from mopidy import config, ext

__version__ = pkg_resources.get_distribution("mopidy_pidiv2").version

logger = logging.getLogger(__name__)


class Extension(ext.Extension):

    dist_name = "Mopidy-PiDi"
    ext_name = "pidiv2"
    version = __version__

    @classmethod
    def get_display_types(self):
        display_types = {}
        for entry_point in pkg_resources.iter_entry_points("pidi.plugin.display"):
            try:
                plugin = entry_point.load()
                display_types[plugin.option_name] = plugin
            except (ImportError) as err:
                logger.log(
                    logging.WARN, f"Error loading display plugin {entry_point}: {err}"
                )

        return display_types

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()
        schema["display"] = config.String(choices=self.get_display_types().keys())
        schema["rotation"] = config.Integer(choices=[0, 90, 180, 270])
        schema["idle_timeout"] = config.Integer(minimum=0)
        schema["rfid_enabled"] = config.Boolean()
        schema["rfid_poll_interval"] = config.Float(minimum=0)
        schema["rfid_debounce"] = config.Float(minimum=0)
        schema["button_play_pause_pin"] = config.Integer(minimum=0)
        schema["button_next_pin"] = config.Integer(minimum=0)
        schema["button_volume_down_pin"] = config.Integer(minimum=0)
        schema["button_volume_up_pin"] = config.Integer(minimum=0)
        schema["shutdown_hold_time"] = config.Integer(minimum=1)
        schema["ups_enabled"] = config.Boolean()
        schema["ups_shutdown_threshold"] = config.Integer(minimum=1, maximum=100)
        schema["ups_poll_interval"] = config.Integer(minimum=1)
        return schema

    def setup(self, registry):
        from .frontend import PiDiV2Frontend

        registry.add("frontend", PiDiV2Frontend)