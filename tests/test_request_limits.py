from types import SimpleNamespace

from PIL import Image

from transimage.description import describe_image
from transimage.detection import detect_objects
from transimage.request_limits import REQUEST_TIMEOUT_MS


class _Recorder:
    def __init__(self, response):
        self.kwargs = {}
        self._response = response

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self._response


def _assert_bounded(kwargs) -> None:
    assert kwargs["timeout_ms"] == REQUEST_TIMEOUT_MS
    assert kwargs["retries"] is None


def test_request_timeout_is_long_enough_for_image_models() -> None:
    assert REQUEST_TIMEOUT_MS >= 60_000


def test_describe_image_bounds_request(monkeypatch) -> None:
    message = SimpleNamespace(content="a cat")
    send = _Recorder(SimpleNamespace(choices=[SimpleNamespace(message=message)]))
    client = SimpleNamespace(chat=SimpleNamespace(send=send))
    monkeypatch.setattr("transimage.description.OpenRouter", lambda **_: client)

    assert describe_image(Image.new("RGB", (8, 8)), "key", "describe") == "a cat"
    _assert_bounded(send.kwargs)


def test_detect_objects_bounds_request(monkeypatch) -> None:
    create = _Recorder(SimpleNamespace(answers={}))
    client = SimpleNamespace(
        alpha=SimpleNamespace(decisions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr("transimage.detection.OpenRouter", lambda **_: client)

    assert detect_objects(Image.new("RGB", (8, 8)), "key", "", "cat") == []
    _assert_bounded(create.kwargs)
