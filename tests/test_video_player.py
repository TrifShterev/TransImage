import threading
from fractions import Fraction
from pathlib import Path

import av
import pytest
from PIL import Image

from transimage.video_player import iter_video_frames

_FRAMES = 8


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    path = tmp_path / "clip.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=Fraction(10))
        stream.width, stream.height = 64, 48
        stream.pix_fmt = "yuv420p"
        for index in range(_FRAMES):
            image = Image.new("RGB", (64, 48), (index * 30, 40, 80))
            frame = av.VideoFrame.from_image(image)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def test_yields_every_frame_with_non_decreasing_times(clip: Path) -> None:
    frames = list(iter_video_frames(clip))
    assert len(frames) == _FRAMES
    times = [seconds for seconds, _image in frames]
    assert times == sorted(times)
    assert times[0] == 0
    assert all(image.size == (64, 48) for _s, image in frames)


def test_max_size_downsizes_keeping_aspect(clip: Path) -> None:
    frames = list(iter_video_frames(clip, max_size=(32, 32)))
    assert {image.size for _s, image in frames} == {(32, 24)}


def test_max_size_never_upscales(clip: Path) -> None:
    frames = list(iter_video_frames(clip, max_size=(640, 480)))
    assert {image.size for _s, image in frames} == {(64, 48)}


def test_max_size_may_be_a_callable(clip: Path) -> None:
    frames = list(iter_video_frames(clip, max_size=lambda: (16, 16)))
    assert {image.size for _s, image in frames} == {(16, 12)}


def test_stop_event_halts_early(clip: Path) -> None:
    stop = threading.Event()
    seen = 0
    for _seconds, _image in iter_video_frames(clip, stop_event=stop):
        seen += 1
        if seen == 3:
            stop.set()
    assert seen == 3


def test_file_handle_released_after_early_close(clip: Path) -> None:
    source = iter_video_frames(clip)
    next(source)
    source.close()
    clip.unlink()
    assert not clip.exists()
