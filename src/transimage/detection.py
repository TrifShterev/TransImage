import base64
import math
import os
import threading
from io import BytesIO

from openrouter import OpenRouter
from PIL import Image

from transimage.request_limits import REQUEST_TIMEOUT_MS

DETECTION_MODEL = "typesafe/jev-1.14"
PRESENCE_THRESHOLD = 0.5
_MIN_SIDE = 256
_MAX_SIDE = 1568
_MIN_PIXELS = 78_400


def get_detection_model() -> str:
    return os.environ.get("MODEL_DETECT_OBJECTS") or DETECTION_MODEL


def prepare_detection_image(image: Image.Image) -> Image.Image:
    width, height = image.size
    new_wide = width
    new_high = height
    if width < _MIN_SIDE or height < _MIN_SIDE or width * height < _MIN_PIXELS:
        scale = max(
            _MIN_SIDE / min(width, height),
            math.sqrt(_MIN_PIXELS / (width * height)),
        )
        new_wide = math.ceil(width * scale)
        new_high = math.ceil(height * scale)
    if new_wide > _MAX_SIDE or new_high > _MAX_SIDE:
        scale = min(_MAX_SIDE / new_wide, _MAX_SIDE / new_high)
        new_wide = math.floor(new_wide * scale)
        new_high = math.floor(new_high * scale)
    if (new_wide, new_high) == (width, height):
        return image.copy()
    return image.resize((new_wide, new_high), Image.Resampling.LANCZOS)


def parse_detections(
    answers, label: str = "object", presence_threshold: float = PRESENCE_THRESHOLD
) -> list[dict]:
    found = answers.get("found")
    if found is not None and getattr(found, "noul", 1.0) < presence_threshold:
        return []
    box_answer = answers.get("box")
    box = getattr(box_answer, "box", None) if box_answer is not None else None
    if box is None:
        return []
    left = float(getattr(box, "left", 0.0))
    top = float(getattr(box, "top", 0.0))
    right = float(getattr(box, "right", 1.0))
    bottom = float(getattr(box, "bottom", 1.0))
    bbox = [
        left,
        top,
        max(0.0, right - left),
        max(0.0, bottom - top),
    ]
    return [{"label": label, "bbox": bbox}]


def detect_objects(
    image: Image.Image,
    api_key: str,
    description: str,
    question: str,
    model: str | None = None,
) -> list[dict]:
    buf = BytesIO()
    prepared = prepare_detection_image(image)
    prepared.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_url = f"data:image/png;base64,{b64}"

    state = []
    if description:
        state.append(f"Image description: {description}")
    state.append({"type": "image_url", "image_url": {"url": data_url}})

    resolved_model = model or get_detection_model()
    client = OpenRouter(api_key=api_key)
    response = client.alpha.decisions.create(
        model=resolved_model,
        state=state,
        questions={
            "found": {
                "type": "noul",
                "instructions": (
                    'Is a visible instance of what the user asked for present '
                    f'in the picture? User question: "{question}"'
                ),
                "criteria": {
                    "true": (
                        "a visible instance of the object the user asked "
                        "about appears in the picture"
                    ),
                    "false": (
                        "nothing in the picture matches the object the user "
                        "asked about"
                    ),
                },
            },
            "box": {
                "type": "box",
                "instructions": (
                    f'the object in the picture the user asked about: "{question}"'
                ),
            },
        },
        timeout_ms=REQUEST_TIMEOUT_MS,
        retries=None,
    )
    return parse_detections(response.answers, label=question)


def detect_objects_async(
    root,
    image: Image.Image,
    api_key: str,
    description: str,
    question: str,
    on_done,
    on_error,
) -> None:
    def _run():
        try:
            result = detect_objects(image, api_key, description, question)
            root.after(0, lambda: on_done(result))
        except Exception as exc:
            message = str(exc)
            root.after(0, lambda: on_error(message))

    threading.Thread(target=_run, daemon=True).start()