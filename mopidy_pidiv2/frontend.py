import base64
import hashlib
import logging
import os
import threading
import time
from urllib.parse import unquote, urlparse

import pykka
from mopidy import core
from mutagen.id3 import ID3
from mutagen.id3._util import ID3NoHeaderError

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
        self.blur_album_art = False


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
        art = self._extract_embedded_apic_data_uri("file:///home/pi/Music/startup.mp3")
        self.display.update_album_art(art=art)
               

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
        # Intentionally ignore stream title updates so no title is shown on display.
        self.display.update(title="")

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

        # Keep title blank to prevent showing track title on screen.
        title = ""

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

        # APIC-only mode: always extract embedded album art directly from track file metadata.
        logger.warning("mopidy-pidiv2: extracting embedded album art for current track" f" (URI: {track.uri})")
        art = self._extract_embedded_apic_data_uri(track.uri)

        self.display.update_album_art(art=art)

    def _extract_embedded_apic_data_uri(self, track_uri):
        file_path = self._resolve_track_file_path(track_uri)
        if file_path is None:
            logger.warning(
                f"mopidy-pidiv2: cannot resolve playable file path from URI: {track_uri}"
            )
            return None

        if not os.path.isfile(file_path):
            logger.error(
                f"mopidy-pidiv2: cannot read local track file for APIC extraction: {file_path}"
            )
            return None

        try:
            tags = ID3(file_path)
            apic_frames = tags.getall("APIC")
            if not apic_frames:
                logger.warning(
                    f"mopidy-pidiv2: no APIC frames in MP3 metadata for {file_path}"
                )
                return None

            apic = apic_frames[0]
            mime = apic.mime or "image/jpeg"
            encoded = base64.b64encode(apic.data).decode("ascii")
            logger.warning(
                f"mopidy-pidiv2: extracted APIC embedded art via mutagen from {file_path}"
            )
            return f"data:{mime};base64,{encoded}"
        except ID3NoHeaderError:
            logger.warning(
                f"mopidy-pidiv2: no ID3 header available for APIC extraction in {file_path}"
            )
            return None
        except Exception as e:
            logger.error(
                f"mopidy-pidiv2: mutagen APIC extraction failed for {file_path}: {e}"
            )
            return None

    def _resolve_track_file_path(self, track_uri):
        parsed = urlparse(track_uri)

        if parsed.scheme == "file":
            return unquote(parsed.path)

        if track_uri.startswith("local:track:"):
            relative_path = unquote(track_uri[len("local:track:") :])
            media_dir = self.config.get("local", {}).get("media_dir")
            if media_dir:
                return os.path.join(media_dir, relative_path)
            logger.error(
                "mopidy-pidiv2: local:track URI received but local.media_dir is not configured"
            )
            return None

        return None

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
        if not art:
            logger.warning("mopidy-pidiv2: no artwork URI supplied for this track")
            return

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
            else:
                logger.error("mopidy-pidiv2: non-embedded artwork blocked (only data: URIs are allowed)")

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