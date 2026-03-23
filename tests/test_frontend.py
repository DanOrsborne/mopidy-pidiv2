import pkg_resources
import pykka
from mopidy import core
from unittest import mock

import pytest
from mopidy_pidiv2 import frontend as frontend_lib

from . import dummy_audio, dummy_backend, dummy_mixer


def stop_mopidy_core():
    pykka.ActorRegistry.stop_all()


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    request.addfinalizer(stop_mopidy_core)


@pytest.fixture
def frontend():
    mixer = dummy_mixer.create_proxy()
    audio = dummy_audio.create_proxy()
    backend = dummy_backend.create_proxy(audio=audio)
    dummy_core = core.Core.start(audio=audio, mixer=mixer, backends=[backend]).proxy()

    distribution = pkg_resources.Distribution(__file__)
    endpoint = pkg_resources.EntryPoint.parse(
        "dummy = mopidy_pidiv2.plugin:DisplayDummy", dist=distribution
    )
    distribution._ep_map = {"pidiv2.plugin.display": {"dummy": endpoint}}
    pkg_resources.working_set.add(distribution, "dummy")

    config = {"pidiv2": {"display": "dummy"}, "core": {"data_dir": "/tmp"}}

    return frontend_lib.PiDiV2Frontend(config, dummy_core)


def test_on_start(frontend):
    frontend.on_start()
    frontend.on_stop()


def test_options_changed(frontend):
    frontend.on_start()
    frontend.options_changed()
    frontend.on_stop()


def test_build_rfid_track_uri(monkeypatch):
    frontend = frontend_lib.PiDiV2Frontend(
        {
            "pidiv2": {"display": "dummy", "rfid_enabled": True},
            "local": {"media_dir": "/music"},
        },
        mock.Mock(),
    )

    monkeypatch.setattr(frontend_lib.os.path, "isfile", lambda path: path == "/music/ABCD1234.mp3")

    assert frontend._build_rfid_track_uri("ABCD1234") == "local:track:ABCD1234.mp3"


def test_play_rfid_uid(monkeypatch):
    core_proxy = mock.Mock()
    tl_track = mock.Mock()
    core_proxy.tracklist.add.return_value.get.return_value = [tl_track]

    frontend = frontend_lib.PiDiV2Frontend(
        {
            "pidiv2": {"display": "dummy", "rfid_enabled": True},
            "local": {"media_dir": "/music"},
        },
        core_proxy,
    )

    monkeypatch.setattr(
        frontend,
        "_build_rfid_track_uri",
        lambda uid_str: "local:track:ABCD1234.mp3",
    )

    frontend._play_rfid_uid("ABCD1234")

    core_proxy.playback.stop.assert_called_once_with()
    core_proxy.tracklist.clear.assert_called_once_with()
    core_proxy.tracklist.add.assert_called_once_with(uris=["local:track:ABCD1234.mp3"])
    core_proxy.playback.play.assert_called_once_with(tl_track=tl_track)
