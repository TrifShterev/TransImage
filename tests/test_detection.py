from types import SimpleNamespace

import pytest
from PIL import Image

from transimage.detection import parse_detections, prepare_detection_image


def _box_answer(top: float, bottom: float, left: float, right: float):
    return SimpleNamespace(
        type="box",
        box=SimpleNamespace(top=top, bottom=bottom, left=left, right=right),
        confidence=0.9,
    )


def test_parse_detections_box_found_and_present() -> None:
    answers = {
        "found": SimpleNamespace(type="noul", noul=0.98),
        "box": _box_answer(0.49, 0.89, 0.58, 0.96),
    }
    assert parse_detections(answers, label="face") == [
        {"label": "face", "bbox": [0.58, 0.49, 0.38, 0.4]}
    ]


def test_parse_detections_empty_when_not_present() -> None:
    answers = {
        "found": SimpleNamespace(type="noul", noul=0.03),
        "box": _box_answer(0.1, 0.2, 0.4, 0.5),
    }
    assert parse_detections(answers) == []


def test_parse_detections_draws_box_when_noul_answer_missing() -> None:
    answers = {"box": _box_answer(0.0, 0.5, 0.0, 0.5)}
    assert parse_detections(answers, label="cat") == [
        {"label": "cat", "bbox": [0.0, 0.0, 0.5, 0.5]}
    ]


def test_parse_detections_empty_when_box_missing() -> None:
    answers = {"found": SimpleNamespace(type="noul", noul=0.9)}
    assert parse_detections(answers) == []


def test_parse_detections_zero_sized_box() -> None:
    answers = {"box": _box_answer(0.0, 0.0, 0.0, 0.0)}
    assert parse_detections(answers) == [{"label": "object", "bbox": [0, 0, 0, 0]}]


def test_parse_detections_uses_custom_presence_threshold() -> None:
    answers = {
        "found": SimpleNamespace(type="noul", noul=0.7),
        "box": _box_answer(0.0, 1.0, 0.0, 1.0),
    }
    assert parse_detections(answers, presence_threshold=0.8) == []
    assert parse_detections(answers, presence_threshold=0.6) != []


def test_prepare_detection_image_upscales_small_image() -> None:
    result = prepare_detection_image(Image.new("RGB", (100, 100)))
    width, height = result.size
    assert width >= 256 and height >= 256
    assert width * height >= 78_400


def test_prepare_detection_image_downscales_large_image() -> None:
    result = prepare_detection_image(Image.new("RGB", (4096, 2048)))
    assert max(result.size) <= 1568
    assert min(result.size) >= 256


def test_prepare_detection_image_keeps_valid_image_unchanged() -> None:
    source = Image.new("RGB", (640, 480))
    result = prepare_detection_image(source)
    assert result.size == (640, 480)