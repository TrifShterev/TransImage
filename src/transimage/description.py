import base64
import os
import threading
from io import BytesIO
from tkinter import messagebox

from openrouter import OpenRouter
from PIL.Image import Image

from transimage.request_limits import REQUEST_TIMEOUT_MS

DEFAULT_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"

# code -> (English name used in the prompt, native name shown in the menu)
LANGUAGES = {
    "EN": ("English", "English"),
    "FI": ("Finnish", "Suomi"),
    "BG": ("Bulgarian", "Български"),
}
DEFAULT_LANGUAGE = "EN"


def build_description_prompt(base_prompt: str, language: str) -> str:
    name = LANGUAGES.get(language, LANGUAGES[DEFAULT_LANGUAGE])[0]
    return (
        f"{base_prompt}\n\n"
        f"Write the entire response in {name}, regardless of the language "
        "used in the instructions above."
    )


def get_description_model() -> str:
    return os.environ.get("MODEL_DESCRIBE_IMAGE") or DEFAULT_MODEL


def describe_image(
    image: Image, api_key: str, prompt: str, model: str | None = None
) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_url = f"data:image/png;base64,{b64}"

    resolved_model = model or get_description_model()
    client = OpenRouter(api_key=api_key)
    response = client.chat.send(
        model=resolved_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        max_tokens=2048,
        timeout_ms=REQUEST_TIMEOUT_MS,
        retries=None,
    )
    return response.choices[0].message.content


def describe_image_async(
    root,
    image: Image,
    api_key: str,
    prompt: str,
    on_done,
    on_error,
) -> None:
    def _run():
        try:
            result = describe_image(image, api_key, prompt)
            root.after(0, lambda: on_done(result))
        except Exception as exc:
            message = str(exc)
            root.after(0, lambda: on_error(message))

    threading.Thread(target=_run, daemon=True).start()


def generate_and_show_description(
    root,
    btn,
    image: Image,
    api_key: str | None,
    after_success=None,
    language: str = DEFAULT_LANGUAGE,
) -> None:
    if not api_key:
        messagebox.showerror(
            "TransImage",
            "No API key configured.\n"
            "Set OPENROUTER_API_KEY in .env",
            parent=root,
        )
        return

    if image is None:
        return

    prompt = (os.environ.get("PROMPT_DESCRIBE_IMAGE") or "").strip()
    if not prompt:
        messagebox.showerror(
            "TransImage",
            "No description prompt configured.\n"
            "Set PROMPT_DESCRIBE_IMAGE in .env",
            parent=root,
        )
        return
    prompt = build_description_prompt(prompt, language)

    btn.configure(text="Generating...", state="disabled")

    def on_done(result: str) -> None:
        btn.configure(text="Generate Description", state="normal")
        messagebox.showinfo(f"Description ({language})", result, parent=root)
        if after_success is not None:
            after_success(result)

    def on_error(error_msg: str) -> None:
        btn.configure(text="Generate Description", state="normal")
        messagebox.showerror("Error", error_msg, parent=root)

    describe_image_async(root, image, api_key, prompt, on_done, on_error)