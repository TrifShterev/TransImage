import base64
import time
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from transimage.modify import (
    DEFAULT_MODEL,
    _encode_upload,
    get_modify_model,
    modify_image,
    modify_image_async,
)
from transimage.request_limits import REQUEST_TIMEOUT_MS


def _png_b64(size=(64, 48), color="red") -> str:
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _FakeImages:
    def __init__(self, captured):
        self._captured = captured

    def generate(self, **kwargs):
        self._captured["kwargs"] = kwargs
        return self._captured["response"]


class _FakeClient:
    def __init__(self, captured, **kwargs):
        self.images = _FakeImages(captured)


def _install_fake_client(monkeypatch, response):
    captured = {"kwargs": {}, "response": response}

    def factory(**kwargs):
        return _FakeClient(captured, **kwargs)

    monkeypatch.setattr("transimage.modify.OpenRouter", factory)
    return captured


def test_modify_model_env_override_and_default(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_MODIFY_IMAGE", raising=False)
    assert get_modify_model() == DEFAULT_MODEL
    assert DEFAULT_MODEL == "meta/muse-image"

    monkeypatch.setenv("MODEL_MODIFY_IMAGE", "")
    assert get_modify_model() == DEFAULT_MODEL

    monkeypatch.setenv("MODEL_MODIFY_IMAGE", "custom/edit-model")
    assert get_modify_model() == "custom/edit-model"


def test_encode_upload_downscales_long_side() -> None:
    url = _encode_upload(Image.new("RGB", (4000, 1000)))
    payload = base64.b64decode(url.partition(",")[2])
    result = Image.open(BytesIO(payload))
    assert max(result.size) == 2048


def test_encode_upload_keeps_small_image() -> None:
    source = Image.new("RGB", (320, 200))
    url = _encode_upload(source)
    payload = base64.b64decode(url.partition(",")[2])
    result = Image.open(BytesIO(payload))
    assert result.size == (320, 200)


def test_modify_image_parses_b64_json(monkeypatch) -> None:
    captured = _install_fake_client(
        monkeypatch,
        SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64(size=(40, 24)))]),
    )
    result = modify_image(Image.new("RGB", (40, 24)), "key", "add a hat")
    assert isinstance(result, Image.Image)
    assert result.size == (40, 24)


def test_modify_image_parses_data_url_b64_json(monkeypatch) -> None:
    b64 = "data:image/png;base64," + _png_b64(size=(16, 16))
    _install_fake_client(
        monkeypatch,
        SimpleNamespace(data=[SimpleNamespace(b64_json=b64)]),
    )
    result = modify_image(Image.new("RGB", (16, 16)), "key", "make it blue")
    assert result.size == (16, 16)


def test_modify_image_sends_request_contract(monkeypatch) -> None:
    captured = _install_fake_client(
        monkeypatch,
        SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64(size=(8, 8)))]),
    )
    modify_image(
        Image.new("RGB", (8, 8)),
        "key",
        "add a hat",
        description="a red cat",
    )
    kwargs = captured["kwargs"]
    assert kwargs["model"] == DEFAULT_MODEL
    assert "add a hat" in kwargs["prompt"]
    assert "a red cat" in kwargs["prompt"]
    refs = kwargs["input_references"]
    assert refs[0]["type"] == "image_url"
    url = refs[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert kwargs["timeout_ms"] == REQUEST_TIMEOUT_MS
    assert kwargs["retries"] is None


def test_modify_image_respects_model_override(monkeypatch) -> None:
    captured = _install_fake_client(
        monkeypatch,
        SimpleNamespace(data=[SimpleNamespace(b64_json=_png_b64(size=(8, 8)))]),
    )
    modify_image(
        Image.new("RGB", (8, 8)),
        "key",
        "add a hat",
        model="custom/edit-model",
    )
    assert captured["kwargs"]["model"] == "custom/edit-model"


def test_modify_image_raises_when_no_image_data(monkeypatch) -> None:
    _install_fake_client(monkeypatch, SimpleNamespace(data=[]))
    with pytest.raises(ValueError, match="no image"):
        modify_image(Image.new("RGB", (16, 16)), "key", "add a hat")


def test_modify_image_raises_on_unreadable_response(monkeypatch) -> None:
    _install_fake_client(
        monkeypatch,
        SimpleNamespace(data=[SimpleNamespace(b64_json="not-base64!!")]),
    )
    with pytest.raises(ValueError, match="Could not read the returned image"):
        modify_image(Image.new("RGB", (16, 16)), "key", "add a hat")


class _FakeRoot:
    def __init__(self):
        self.callbacks = []

    def after(self, _ms, fn):
        self.callbacks.append(fn)
        return "id"


def _wait_for_callbacks(root: _FakeRoot) -> None:
    deadline = time.time() + 2
    while not root.callbacks and time.time() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)
    for fn in root.callbacks:
        fn()


def test_modify_image_async_reports_error(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("API failure")

    monkeypatch.setattr("transimage.modify.modify_image", boom)
    root = _FakeRoot()
    errors = []
    modify_image_async(
        root,
        Image.new("RGB", (8, 8)),
        "key",
        "fix this",
        "",
        lambda _result: None,
        errors.append,
    )
    _wait_for_callbacks(root)
    assert errors == ["API failure"]


def test_modify_image_async_reports_success(monkeypatch) -> None:
    result_image = Image.new("RGB", (8, 8))

    def fake_modify(*args, **kwargs):
        return result_image

    monkeypatch.setattr("transimage.modify.modify_image", fake_modify)
    root = _FakeRoot()
    results = []
    modify_image_async(
        root,
        Image.new("RGB", (8, 8)),
        "key",
        "fix this",
        "",
        results.append,
        lambda _msg: None,
    )
    _wait_for_callbacks(root)
    assert results == [result_image]