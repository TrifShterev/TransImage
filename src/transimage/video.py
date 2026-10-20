import math
import os
import tempfile
import threading
import time
from pathlib import Path

from openrouter import OpenRouter
from PIL import Image

from transimage.modify import _encode_upload
from transimage.request_limits import REQUEST_TIMEOUT_MS

DEFAULT_MODEL = "heygen/heygen-video-1"
DEFAULT_RESOLUTION = "768p"
MIN_DURATION = 5
MAX_DURATION = 15
DEFAULT_DURATION = 5
ASPECT_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
POLL_INTERVAL_S = 5
JOB_TIMEOUT_S = 900
MAX_POLL_FAILURES = 3

_FAILED_STATUSES = ("failed", "cancelled", "expired")

_VIDEO_PROMPT = (
    "Animate the attached image, which is the first frame of the video, "
    "according to the user's request."
)


def get_video_model() -> str:
    return os.environ.get("MODEL_GENERATE_VIDEO") or DEFAULT_MODEL


def get_video_resolution() -> str:
    return os.environ.get("VIDEO_RESOLUTION") or DEFAULT_RESOLUTION


def clamp_duration(value) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_DURATION
    return max(MIN_DURATION, min(MAX_DURATION, number))


def nearest_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "16:9"
    target = math.log(width / height)

    def distance(ratio: str) -> float:
        ratio_w, ratio_h = (int(part) for part in ratio.split(":"))
        return abs(target - math.log(ratio_w / ratio_h))

    return min(ASPECT_RATIOS, key=distance)


def build_video_prompt(request: str, description: str = "") -> str:
    text = _VIDEO_PROMPT
    if description:
        text += (
            f' Context: the cached description of the image is "{description}". '
            "It may be stale if the image was edited earlier."
        )
    text += f'\n\nVideo request: "{request}"'
    return text


def _download(client, job_id: str, on_status) -> Path:
    on_status("downloading", 0)
    response = client.video_generation.get_video_content(
        job_id=job_id,
        index=0,
        timeout_ms=REQUEST_TIMEOUT_MS,
        retries=None,
    )
    fd, name = tempfile.mkstemp(prefix="transimage_", suffix=".mp4")
    path = Path(name)
    try:
        written = 0
        try:
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    written += len(chunk)
        finally:
            response.close()
        if written == 0:
            raise ValueError("The model returned an empty video.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def generate_video(
    image: Image.Image,
    api_key: str,
    request: str,
    duration: int,
    description: str = "",
    model: str | None = None,
    on_status=None,
    sleep=time.sleep,
    clock=time.monotonic,
) -> Path:
    def report(status: str, elapsed: float) -> None:
        if on_status is not None:
            on_status(status, elapsed)

    data_url = _encode_upload(image)
    client = OpenRouter(api_key=api_key)
    started = clock()
    job = client.video_generation.generate(
        model=model or get_video_model(),
        prompt=build_video_prompt(request, description),
        frame_images=[
            {
                "type": "image_url",
                "image_url": {"url": data_url},
                "frame_type": "first_frame",
            }
        ],
        duration=clamp_duration(duration),
        aspect_ratio=nearest_aspect_ratio(*image.size),
        resolution=get_video_resolution(),
        timeout_ms=REQUEST_TIMEOUT_MS,
        retries=None,
    )
    job_id = job.id
    report(job.status, clock() - started)

    failures = 0
    status = job.status
    while status != "completed":
        if status in _FAILED_STATUSES:
            detail = getattr(job, "error", None) or status
            raise ValueError(f"Video generation {status}: {detail}")
        if clock() - started > JOB_TIMEOUT_S:
            raise ValueError(
                f"Video generation timed out after {JOB_TIMEOUT_S // 60} minutes "
                f"(job {job_id})."
            )
        sleep(POLL_INTERVAL_S)
        try:
            job = client.video_generation.get_generation(
                job_id=job_id,
                timeout_ms=REQUEST_TIMEOUT_MS,
                retries=None,
            )
        except Exception as exc:
            failures += 1
            if failures >= MAX_POLL_FAILURES:
                raise ValueError(
                    f"Lost contact with video job {job_id}: {exc}"
                ) from exc
            continue
        failures = 0
        status = job.status
        report(status, clock() - started)

    return _download(client, job_id, lambda s, _e: report(s, clock() - started))


def generate_video_async(
    root,
    image: Image.Image,
    api_key: str,
    request: str,
    duration: int,
    description: str,
    on_status,
    on_done,
    on_error,
) -> None:
    def _status(status: str, elapsed: float) -> None:
        root.after(0, lambda: on_status(status, elapsed))

    def _run():
        try:
            result = generate_video(
                image,
                api_key,
                request,
                duration,
                description,
                on_status=_status,
            )
            root.after(0, lambda: on_done(result))
        except Exception as exc:
            message = str(exc)
            root.after(0, lambda: on_error(message))

    threading.Thread(target=_run, daemon=True).start()
