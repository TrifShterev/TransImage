import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable, Iterator
from pathlib import Path

import av
from PIL import Image, ImageTk

from transimage.fit import fit_image

_QUEUE_SIZE = 12
_JOIN_TIMEOUT_S = 2.0
_EOF = object()


def iter_video_frames(
    path: Path,
    stop_event: threading.Event | None = None,
    max_size: tuple[int, int] | Callable[[], tuple[int, int]] | None = None,
) -> Iterator[tuple[float, Image.Image]]:
    container = av.open(str(path))
    try:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        rate = stream.average_rate
        for index, frame in enumerate(container.decode(stream)):
            if stop_event is not None and stop_event.is_set():
                return
            if frame.time is not None:
                seconds = float(frame.time)
            elif rate:
                seconds = index / float(rate)
            else:
                seconds = 0.0
            image = frame.to_image()
            box = max_size() if callable(max_size) else max_size
            if box is not None:
                width, height = image.size
                fit_w, fit_h, _x, _y = fit_image(width, height, *box)
                if 0 < fit_w < width or 0 < fit_h < height:
                    image = image.resize((fit_w, fit_h), Image.Resampling.BILINEAR)
            yield seconds, image
    finally:
        container.close()


class VideoPlayback:
    def __init__(
        self,
        widget: tk.Misc,
        canvas: tk.Canvas,
        path: Path,
        on_state: Callable[[str], None],
    ) -> None:
        self._widget = widget
        self._canvas = canvas
        self._path = path
        self._on_state = on_state
        self._state = "paused"
        self._closed = False
        self._after_id: str | None = None
        self._origin: float | None = None
        self._position = 0.0
        self._held: tuple[float, Image.Image] | None = None
        self._eof = False
        self._last_frame: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=_QUEUE_SIZE)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._box_size = (1, 1)
        self._canvas.bind("<Configure>", self._on_configure, add="+")
        self._start_worker()
        self._set_state("playing")
        self._schedule(0)

    @property
    def state(self) -> str:
        return self._state

    def toggle(self) -> None:
        if self._closed:
            return
        if self._state == "playing":
            self._cancel_tick()
            self._set_state("paused")
        elif self._state == "paused":
            self._origin = time.monotonic() - self._position
            self._set_state("playing")
            self._schedule(0)
        else:
            self.restart()

    def restart(self) -> None:
        if self._closed:
            return
        self._cancel_tick()
        self._stop_worker()
        self._origin = None
        self._position = 0.0
        self._held = None
        self._eof = False
        self._start_worker()
        self._set_state("playing")
        self._schedule(0)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_tick()
        self._stop_worker()
        self._last_frame = None
        self._photo = None

    def _set_state(self, state: str) -> None:
        self._state = state
        self._on_state(state)

    def _refresh_box(self) -> tuple[int, int]:
        self._box_size = (
            max(1, self._canvas.winfo_width()),
            max(1, self._canvas.winfo_height()),
        )
        return self._box_size

    def _start_worker(self) -> None:
        self._stop = threading.Event()
        frames: queue.Queue = queue.Queue(maxsize=_QUEUE_SIZE)
        self._queue = frames
        stop = self._stop
        path = self._path
        self._refresh_box()

        def box() -> tuple[int, int]:
            return self._box_size

        def put(item) -> bool:
            while not stop.is_set():
                try:
                    frames.put(item, timeout=0.1)
                    return True
                except queue.Full:
                    continue
            return False

        def run() -> None:
            source = iter_video_frames(path, stop, box)
            try:
                for item in source:
                    if not put(item):
                        return
                put(_EOF)
            except Exception:
                put(_EOF)
            finally:
                source.close()

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def _stop_worker(self) -> None:
        self._stop.set()
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.join(timeout=_JOIN_TIMEOUT_S)

    def _schedule(self, delay_ms: int) -> None:
        self._cancel_tick()
        if self._closed:
            return
        try:
            self._after_id = self._widget.after(delay_ms, self._tick)
        except tk.TclError:
            self._after_id = None

    def _cancel_tick(self) -> None:
        if self._after_id is None:
            return
        try:
            self._widget.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _tick(self) -> None:
        self._after_id = None
        if self._closed or self._state != "playing":
            return
        drawn: Image.Image | None = None
        elapsed = 0.0
        if self._origin is not None:
            elapsed = time.monotonic() - self._origin
        while True:
            if self._held is None:
                if self._eof:
                    break
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is _EOF:
                    self._eof = True
                    break
                self._held = item
                if self._origin is None:
                    self._origin = time.monotonic() - item[0]
                    elapsed = item[0]
            seconds, image = self._held
            if seconds > elapsed:
                break
            drawn = image
            self._position = seconds
            self._held = None
        if drawn is not None:
            self._draw(drawn)
        if self._eof and self._held is None:
            self._set_state("ended")
            return
        if self._held is not None:
            wait_ms = int((self._held[0] - elapsed) * 1000)
            self._schedule(max(1, min(wait_ms, 30)))
        else:
            self._schedule(8)

    def _draw(self, frame: Image.Image) -> None:
        self._last_frame = frame
        width, height = self._refresh_box()
        fit_w, fit_h, offset_x, offset_y = fit_image(*frame.size, width, height)
        if fit_w <= 0 or fit_h <= 0:
            return
        shown = frame
        if (fit_w, fit_h) != frame.size:
            shown = frame.resize((fit_w, fit_h), Image.Resampling.BILINEAR)
        self._photo = ImageTk.PhotoImage(shown)
        self._canvas.delete("all")
        self._canvas.create_image(
            offset_x, offset_y, image=self._photo, anchor=tk.NW
        )

    def _on_configure(self, _event: tk.Event) -> None:
        if self._closed:
            return
        self._refresh_box()
        if self._last_frame is None:
            return
        if self._state != "playing":
            self._draw(self._last_frame)
