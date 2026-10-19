import base64
import os
import threading
from io import BytesIO

from openrouter import OpenRouter
from PIL import Image

from transimage.request_limits import REQUEST_TIMEOUT_MS

DEFAULT_MODEL = "meta/muse-image"
_MAX_UPLOAD_SIDE = 2048

_EDIT_PROMPT = (
    "Edit the attached image to satisfy the user's request. "
    "Return the edited image."
)


def get_modify_model() -> str:
    return os.environ.get("MODEL_MODIFY_IMAGE") or DEFAULT_MODEL


def _encode_upload(image: Image.Image) -> str:
    width, height = image.size
    long_side = max(width, height)
    if long_side > _MAX_UPLOAD_SIDE:
        scale = _MAX_UPLOAD_SIDE / long_side
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        prepared = image.resize(size, Image.Resampling.LANCZOS)
    else:
        prepared = image.copy()
    buf = BytesIO()
    prepared.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def _decode_b64_json(value: str) -> bytes:
    stripped = value.strip()
    if stripped.startswith("data:"):
        _header, sep, payload = stripped.partition(",")
        if not sep or "base64" not in _header:
            raise ValueError("The model returned a non-base64 data URL.")
        stripped = payload
    return base64.b64decode(stripped)


def modify_image(
    image: Image.Image,
    api_key: str,
    request: str,
    description: str = "",
    model: str | None = None,
) -> Image.Image:
    data_url = _encode_upload(image)

    text = _EDIT_PROMPT
    if description:
        text += (
            f' Context: the cached description of the image is "{description}". '
            "It may be stale if the image was edited earlier."
        )
    text += f'\n\nModification request: "{request}"'

    resolved_model = model or get_modify_model()
    client = OpenRouter(api_key=api_key)
    response = client.images.generate(
        model=resolved_model,
        prompt=text,
        input_references=[
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
        timeout_ms=REQUEST_TIMEOUT_MS,
        retries=None,
    )
    if not response.data:
        raise ValueError("The model returned no image.")
    try:
        payload = _decode_b64_json(response.data[0].b64_json)
        with Image.open(BytesIO(payload)) as opened:
            opened.load()
            return opened.copy()
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not read the returned image: {exc}") from exc


def modify_image_async(
    root,
    image: Image.Image,
    api_key: str,
    request: str,
    description: str,
    on_done,
    on_error,
) -> None:
    def _run():
        try:
            result = modify_image(image, api_key, request, description)
            root.after(0, lambda: on_done(result))
        except Exception as exc:
            message = str(exc)
            root.after(0, lambda: on_error(message))

    threading.Thread(target=_run, daemon=True).start()