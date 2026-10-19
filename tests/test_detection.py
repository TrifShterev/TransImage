from types import SimpleNamespace

import pytest
from PIL import Image

from transimage.description import DEFAULT_MODEL, get_description_model
from transimage.detection import (
    DETECTION_MODEL,
    get_detection_model,
    parse_detections,
    prepare_detection_image,
)


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


def test_description_model_env_override_and_default(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_DESCRIBE_IMAGE", raising=False)
    assert get_description_model() == DEFAULT_MODEL
    assert DEFAULT_MODEL == "qwen/qwen3-vl-235b-a22b-instruct"

    monkeypatch.setenv("MODEL_DESCRIBE_IMAGE", "")
    assert get_description_model() == DEFAULT_MODEL

    monkeypatch.setenv("MODEL_DESCRIBE_IMAGE", "custom/describe-model")
    assert get_description_model() == "custom/describe-model"


def test_detection_model_env_override_and_default(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_DETECT_OBJECTS", raising=False)
    assert get_detection_model() == DETECTION_MODEL
    assert DETECTION_MODEL == "typesafe/jev-1.14"

    monkeypatch.setenv("MODEL_DETECT_OBJECTS", "")
    assert get_detection_model() == DETECTION_MODEL

    monkeypatch.setenv("MODEL_DETECT_OBJECTS", "custom/decision-model")
    assert get_detection_model() == "custom/decision-model"
