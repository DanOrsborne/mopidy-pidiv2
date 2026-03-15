import base64
import hashlib
import logging
import os
import threading
import time
from urllib.parse import unquote

import pykka
import requests
from mopidy import core

import netifaces

from . import Extension
from .brainz import Brainz

logger = logging.getLogger(__name__)


class PiDiV2Config:
    def __init__(self, config=None):
        self.rotation = config.get("rotation", 90)
        self.spi_port = 0
        self.spi_chip_select_pin = 1
        self.spi_data_command_pin = 9
        self.spi_speed_mhz = 80
        self.backlight_pin = 13
        self.size = 240
        self.blur_album_art = True


class PiDiV2Frontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config, core):
        super().__init__()
        self.core = core
        self.config = config
        self.current_track = None

    def on_start(self):

        
        self.display = PiDiV2(self.config)
        self.display.start()
        self.display.update(volume=self.core.mixer.get_volume().get())
        self.display.update_album_art(art="")
        
                    

    def on_stop(self):
        self.display.stop()
        self.display = None

    def get_ifaddress(self, iface, family):
        try:
            return netifaces.ifaddresses(iface)[family][0]["addr"]
        except (IndexError, KeyError):
            return None

    def mute_changed(self, mute):
        pass

    def options_changed(self):
        self.display.update(
            shuffle=self.core.tracklist.get_random(),
            repeat=self.core.tracklist.get_repeat(),
        )

    def playlist_changed(self, playlist):
        pass

    def playlist_deleted(self, playlist):
        pass

    def playlists_loaded(self):
        pass

    def seeked(self, time_position):
        self.update_elapsed(time_position)

    def stream_title_changed(self, title):
        self.display.update(title=title)

    def track_playback_ended(self, tl_track, time_position):
        self.update_elapsed(time_position)
        self.display.update(state="pause")

    def track_playback_paused(self, tl_track, time_position):
        self.update_elapsed(time_position)
        self.display.update(state="pause")

    def track_playback_resumed(self, tl_track, time_position):
        self.update_elapsed(time_position)
        self.display.update(state="play")

    def track_playback_started(self, tl_track):
        self.update_track(tl_track.track, 0)
        self.display.update(state="play")

    def update_elapsed(self, time_position):
        self.display.update(elapsed=float(time_position))

    def update_track(self, track, time_position=None):
        if track is None:
            track = self.core.playback.get_current_track().get()

        title = ""
        album = ""
        artist = ""

        if track.name is not None:
            title = track.name

        if track.album is not None and track.album.name is not None:
            album = track.album.name

        if track.artists is not None:
            artist = ", ".join([artist.name for artist in track.artists])

        self.display.update(title=title, album=album, artist=artist)

        if time_position is not None:
            length = track.length
            # Default to 60s long and loop the transport bar
            if length is None:
                length = 60
                time_position %= length

            self.display.update(elapsed=float(time_position), length=float(length))

        art = None
        track_images = self.core.library.get_images([track.uri]).get()
        logger.warning(f"mopidy-pidiv2: got {len(track_images)} image entries for {track.uri}")
        if track.uri in track_images:
            images = track_images[track.uri]
            logger.warning(f"mopidy-pidiv2: {len(images)} image(s) available for track")
            # Prefer embedded art (data: URIs from MP3/FLAC tags) — no dimensions available
            for image in images:
                if image.uri.startswith("data:"):
                    art = image.uri
                    logger.warning("mopidy-pidiv2: using embedded data: URI cover art")
                    break
            if art is None:
                # Fall back to a remote image that meets the minimum display size
                for image in images:
                    if image.width is not None and image.height is not None:
                        if image.height >= 240 and image.width >= 240:
                            art = image.uri
                            logger.warning(f"mopidy-pidiv2: using sized remote image {image.width}x{image.height}: {art}")
                            break
            if art is None and images:
                # Last resort: use whatever is available
                art = images[0].uri
                logger.warning(f"mopidy-pidiv2: using first available image as fallback: {art[:80]}")
        else:
            logger.warning(f"mopidy-pidiv2: no images returned for {track.uri}, falling back to MusicBrainz")

        self.display.update_album_art(art=art)

    def tracklist_changed(self):
        pass

    def volume_changed(self, volume):
        if volume is None:
            return

        self.display.update(volume=volume)


class PiDiV2:
    def __init__(self, config):
        self.config = config
        self.cache_dir = Extension.get_data_dir(config)
        self.display_config = PiDiV2Config(config["pidiv2"])
        self.display_class = Extension.get_display_types()[
            self.config["pidiv2"]["display"]
        ]
        self.idle_timeout = config["pidiv2"].get("idle_timeout", 0)

        self._brainz = Brainz(cache_dir=self.cache_dir)
        self._display = self.display_class(self.display_config)
        self._running = threading.Event()
        self._delay = 1.0 / 30
        self._thread = None

        self.shuffle = False
        self.repeat = False
        self.state = "stop"
        self.volume = 100
        self.progress = 0
        self.elapsed = 0
        self.length = 0
        self.title = ""
        self.album = ""
        self.artist = ""
        self._last_progress_update = time.time()
        self._last_progress_value = 0
        self._last_state_change = 0
        self._last_art = ""

    def start(self):
        if self._thread is not None:
            return

        self._running = threading.Event()
        self._running.set()
        self._thread = threading.Thread(target=self._loop)
        self._thread.start()

    def stop(self):
        self._running.clear()
        self._thread.join()
        self._thread = None
        self._display.stop()

    def _handle_album_art(self, art):
        if art != self._last_art:
            self._display.update_album_art(art)
            self._last_art = art

    def update_album_art(self, art=None):
        _album = self.title if self.album is None or self.album == "" else self.album

        if art is not None:
            logger.warning(f"mopidy-pidiv2: update_album_art called with uri scheme '{art.split(':')[0]}:'")
            if art.startswith("data:"):
                # Embedded cover art from MP3/FLAC ID3 tags via mopidy-local.
                # Must be checked before os.path.isfile — the URI is too long for the
                # filesystem and raises OSError on Linux.
                cache_key = hashlib.md5(art.encode("utf-8")).hexdigest()
                file_name = os.path.join(self.cache_dir, f"{cache_key}.jpg")
                if not os.path.isfile(file_name):
                    logger.warning(f"mopidy-pidiv2: decoding embedded cover art to {file_name}")
                    try:
                        _, encoded = art.split(",", 1)
                        self._brainz.save_album_art(base64.b64decode(encoded), file_name)
                    except Exception as e:
                        logger.error(f"mopidy-pidiv2: failed to decode embedded cover art: {e}")
                        return
                else:
                    logger.warning(f"mopidy-pidiv2: embedded cover art cache hit: {file_name}")
                self._handle_album_art(file_name)
                return

            elif art.startswith("file://"):
                # Local file URI from mopidy-local
                file_path = unquote(art[7:])
                if os.path.isfile(file_path):
                    logger.warning(f"mopidy-pidiv2: using local file URI: {file_path}")
                    self._handle_album_art(file_path)
                    return
                else:
                    logger.error(f"mopidy-pidiv2: local file URI not found on disk: {file_path}")

            elif art.startswith("http://") or art.startswith("https://"):
                file_name = self._brainz.get_cache_file_name(art)

                if os.path.isfile(file_name):
                    logger.warning(f"mopidy-pidiv2: remote art cache hit: {file_name}")
                    self._handle_album_art(file_name)
                    return

                else:
                    logger.warning(f"mopidy-pidiv2: downloading remote art: {art}")
                    response = requests.get(art)
                    if response.status_code == 200:
                        self._brainz.save_album_art(response.content, file_name)
                        self._handle_album_art(file_name)
                        return
                    else:
                        logger.error(f"mopidy-pidiv2: remote art download failed with HTTP {response.status_code}: {art}")

            else:
                logger.error(f"mopidy-pidiv2: unrecognised art URI scheme, skipping: {art[:80]}")

        logger.warning(f"mopidy-pidiv2: falling back to MusicBrainz for '{self.artist} - {_album}'")
        art = self._brainz.get_album_art(self.artist, _album, self._handle_album_art)

    def update(self, **kwargs):
        if "state" in kwargs or "volume" in kwargs:
            self._last_state_change = time.time()
            self._display.start()
        self.shuffle = kwargs.get("shuffle", self.shuffle)
        self.repeat = kwargs.get("repeat", self.repeat)
        self.state = kwargs.get("state", self.state)
        self.volume = kwargs.get("volume", self.volume)
        # self.progress = kwargs.get('progress', self.progress)
        self.elapsed = kwargs.get("elapsed", self.elapsed)
        self.length = kwargs.get("length", self.length)
        self.title = kwargs.get("title", self.title)
        self.album = kwargs.get("album", self.album)
        self.artist = kwargs.get("artist", self.artist)

        if "elapsed" in kwargs:
            if "length" in kwargs:
                self.progress = float(self.elapsed) / float(self.length)
            self._last_elapsed_update = time.time()
            self._last_elapsed_value = kwargs["elapsed"]

    def _loop(self):
        while self._running.is_set():
            t_idle_sec = time.time() - self._last_state_change
            if self.idle_timeout > 0 and t_idle_sec >= self.idle_timeout:
                self._display.stop()
            elif self.state == "play":
                t_elapsed_ms = (time.time() - self._last_elapsed_update) * 1000
                self.elapsed = float(self._last_elapsed_value + t_elapsed_ms)
                self.progress = self.elapsed / self.length
            self._display.update_overlay(
                self.shuffle,
                self.repeat,
                self.state,
                self.volume,
                self.progress,
                self.elapsed,
                self.title,
                self.album,
                self.artist,
            )

            self._display.redraw()
            time.sleep(self._delay)