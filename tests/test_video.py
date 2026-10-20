import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from transimage import video
from transimage.request_limits import REQUEST_TIMEOUT_MS
from transimage.video import (
    DEFAULT_MODEL,
    DEFAULT_RESOLUTION,
    JOB_TIMEOUT_S,
    build_video_prompt,
    clamp_duration,
    generate_video,
    generate_video_async,
    get_video_model,
    get_video_resolution,
    nearest_aspect_ratio,
)


class _FakeStream:
    def __init__(self, chunks, closed):
        self._chunks = chunks
        self._closed = closed

    def iter_bytes(self):
        yield from self._chunks

    def close(self):
        self._closed.append(True)


class _FakeVideoGeneration:
    def __init__(self, statuses, chunks, poll_errors=0, error=None):
        self.statuses = list(statuses)
        self.chunks = chunks
        self.poll_errors = poll_errors
        self.error = error
        self.calls = {}
        self.closed = []
        self.polls = 0

    def generate(self, **kwargs):
        self.calls["generate"] = kwargs
        return SimpleNamespace(id="job-1", status="pending", error=None)

    def get_generation(self, **kwargs):
        self.calls["get_generation"] = kwargs
        self.polls += 1
        if self.poll_errors:
            self.poll_errors -= 1
            raise RuntimeError("network blip")
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return SimpleNamespace(id="job-1", status=status, error=self.error)

    def get_video_content(self, **kwargs):
        self.calls["get_video_content"] = kwargs
        return _FakeStream(self.chunks, self.closed)


def _install(monkeypatch, **kwargs):
    fake = _FakeVideoGeneration(**kwargs)
    monkeypatch.setattr(
        "transimage.video.OpenRouter",
        lambda **_kw: SimpleNamespace(video_generation=fake),
    )
    monkeypatch.delenv("MODEL_GENERATE_VIDEO", raising=False)
    monkeypatch.delenv("VIDEO_RESOLUTION", raising=False)
    return fake


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _run(clock=None, **kwargs):
    clock = clock or _Clock()
    return generate_video(
        Image.new("RGB", (160, 90)),
        "key",
        "make it wave",
        kwargs.pop("duration", 7),
        sleep=clock.sleep,
        clock=clock,
        **kwargs,
    )


def test_model_and_resolution_env_fallback(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_GENERATE_VIDEO", raising=False)
    monkeypatch.delenv("VIDEO_RESOLUTION", raising=False)
    assert get_video_model() == DEFAULT_MODEL == "heygen/heygen-video-1"
    assert get_video_resolution() == DEFAULT_RESOLUTION == "768p"
    monkeypatch.setenv("MODEL_GENERATE_VIDEO", "")
    monkeypatch.setenv("VIDEO_RESOLUTION", "")
    assert get_video_model() == DEFAULT_MODEL
    assert get_video_resolution() == DEFAULT_RESOLUTION
    monkeypatch.setenv("MODEL_GENERATE_VIDEO", "custom/video")
    monkeypatch.setenv("VIDEO_RESOLUTION", "1080p")
    assert get_video_model() == "custom/video"
    assert get_video_resolution() == "1080p"


@pytest.mark.parametrize(
    "value, expected",
    [(5, 5), (15, 15), ("9", 9), (" 12 ", 12), (1, 5), (99, 15), ("x", 5), (None, 5)],
)
def test_clamp_duration(value, expected) -> None:
    assert clamp_duration(value) == expected


@pytest.mark.parametrize(
    "size, expected",
    [
        ((1920, 1080), "16:9"),
        ((1000, 1000), "1:1"),
        ((1080, 1920), "9:16"),
        ((800, 600), "4:3"),
        ((600, 800), "3:4"),
        ((3000, 1000), "21:9"),
        ((1500, 1000), "4:3"),
        ((0, 10), "16:9"),
    ],
)
def test_nearest_aspect_ratio(size, expected) -> None:
    assert nearest_aspect_ratio(*size) == expected


def test_prompt_without_description() -> None:
    prompt = build_video_prompt("make it wave")
    assert "first frame" in prompt
    assert "description" not in prompt
    assert prompt.endswith('Video request: "make it wave"')


def test_prompt_with_description() -> None:
    prompt = build_video_prompt("make it wave", "a red cat")
    assert '"a red cat"' in prompt
    assert "stale" in prompt
    assert prompt.endswith('Video request: "make it wave"')


def test_generate_video_full_flow(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        statuses=["in_progress", "completed"],
        chunks=[b"abc", b"def"],
    )
    seen = []
    path = _run(description="a red cat", on_status=lambda s, e: seen.append((s, e)))
    try:
        assert path.suffix == ".mp4"
        assert path.read_bytes() == b"abcdef"
        assert [s for s, _ in seen] == [
            "pending",
            "in_progress",
            "completed",
            "downloading",
        ]
        assert fake.closed == [True]
        assert seen[1][1] == 5
    finally:
        path.unlink(missing_ok=True)


def test_generate_video_request_contract(monkeypatch) -> None:
    fake = _install(monkeypatch, statuses=["completed"], chunks=[b"x"])
    path = _run(description="a red cat", duration=99)
    path.unlink(missing_ok=True)
    kwargs = fake.calls["generate"]
    assert kwargs["model"] == DEFAULT_MODEL
    assert "make it wave" in kwargs["prompt"]
    assert "a red cat" in kwargs["prompt"]
    frame = kwargs["frame_images"][0]
    assert frame["frame_type"] == "first_frame"
    assert frame["type"] == "image_url"
    assert frame["image_url"]["url"].startswith("data:image/png;base64,")
    assert kwargs["duration"] == 15
    assert kwargs["aspect_ratio"] == "16:9"
    assert kwargs["resolution"] == "768p"
    assert fake.calls["get_generation"]["job_id"] == "job-1"
    assert fake.calls["get_video_content"]["job_id"] == "job-1"
    assert fake.calls["get_video_content"]["index"] == 0
    for name in ("generate", "get_generation", "get_video_content"):
        assert fake.calls[name]["timeout_ms"] == REQUEST_TIMEOUT_MS
        assert fake.calls[name]["retries"] is None


def test_generate_video_respects_model_override(monkeypatch) -> None:
    fake = _install(monkeypatch, statuses=["completed"], chunks=[b"x"])
    path = _run(model="custom/video")
    path.unlink(missing_ok=True)
    assert fake.calls["generate"]["model"] == "custom/video"


@pytest.mark.parametrize("status", ["failed", "cancelled", "expired"])
def test_terminal_failure_raises_provider_message(monkeypatch, status) -> None:
    _install(monkeypatch, statuses=[status], chunks=[], error="content policy")
    with pytest.raises(ValueError, match=f"{status}: content policy"):
        _run()


def test_terminal_failure_without_message_names_status(monkeypatch) -> None:
    _install(monkeypatch, statuses=["failed"], chunks=[])
    with pytest.raises(ValueError, match="failed: failed"):
        _run()


def test_job_timeout_names_job_id(monkeypatch) -> None:
    fake = _install(monkeypatch, statuses=["in_progress"], chunks=[])
    with pytest.raises(ValueError, match="job-1"):
        _run()
    assert fake.polls >= JOB_TIMEOUT_S // video.POLL_INTERVAL_S - 1


def test_poll_failures_are_tolerated(monkeypatch) -> None:
    fake = _install(
        monkeypatch, statuses=["completed"], chunks=[b"ok"], poll_errors=2
    )
    path = _run()
    path.unlink(missing_ok=True)
    assert fake.polls == 3


def test_too_many_poll_failures_raise(monkeypatch) -> None:
    _install(monkeypatch, statuses=["completed"], chunks=[b"ok"], poll_errors=3)
    with pytest.raises(ValueError, match="job-1"):
        _run()


def test_poll_failure_counter_resets_on_success(monkeypatch) -> None:
    fake = _install(monkeypatch, statuses=["completed"], chunks=[b"ok"])
    outcomes = iter(["err", "err", "in_progress", "err", "err", "completed"])

    def flaky(**kwargs):
        fake.polls += 1
        outcome = next(outcomes)
        if outcome == "err":
            raise RuntimeError("blip")
        return SimpleNamespace(id="job-1", status=outcome, error=None)

    fake.get_generation = flaky
    path = _run()
    path.unlink(missing_ok=True)
    assert fake.polls == 6


def test_empty_download_raises_and_removes_temp_file(monkeypatch) -> None:
    fake = _install(monkeypatch, statuses=["completed"], chunks=[b""])
    created = []
    real_mkstemp = video.tempfile.mkstemp

    def tracking_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        created.append(Path(name))
        return fd, name

    monkeypatch.setattr(video.tempfile, "mkstemp", tracking_mkstemp)
    with pytest.raises(ValueError, match="empty video"):
        _run()
    assert len(created) == 1
    assert not created[0].exists()
    assert fake.closed == [True]


class _FakeRoot:
    def __init__(self):
        self.callbacks = []

    def after(self, _ms, fn):
        self.callbacks.append(fn)
        return "id"


def _drain(root: _FakeRoot) -> None:
    deadline = time.time() + 2
    while not root.callbacks and time.time() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)
    for fn in list(root.callbacks):
        fn()


def test_async_reports_status_and_success(monkeypatch) -> None:
    result_path = Path("video.mp4")

    def fake_generate(image, api_key, request, duration, description, on_status):
        on_status("in_progress", 6)
        return result_path

    monkeypatch.setattr("transimage.video.generate_video", fake_generate)
    root = _FakeRoot()
    statuses, results = [], []
    generate_video_async(
        root,
        Image.new("RGB", (8, 8)),
        "key",
        "wave",
        5,
        "",
        lambda s, e: statuses.append((s, e)),
        results.append,
        lambda _m: None,
    )
    _drain(root)
    assert statuses == [("in_progress", 6)]
    assert results == [result_path]


def test_async_reports_error(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("API failure")

    monkeypatch.setattr("transimage.video.generate_video", boom)
    root = _FakeRoot()
    errors = []
    generate_video_async(
        root,
        Image.new("RGB", (8, 8)),
        "key",
        "wave",
        5,
        "",
        lambda s, e: None,
        lambda _p: None,
        errors.append,
    )
    _drain(root)
    assert errors == ["API failure"]
