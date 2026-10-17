import base64
import os
import threading
from io import BytesIO
from tkinter import messagebox

from openrouter import OpenRouter
from PIL.Image import Image

DEFAULT_PROMPT = (
    "Опишете това изображение подробно на български език, включително "
    "основния обект, композицията, цветовете, осветлението и всички "
    "видими текстови или забележителни елементи. Бъдете кратки, но задълбочени."
)


def describe_image(image: Image, api_key: str, prompt: str) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    data_url = f"data:image/png;base64,{b64}"

    client = OpenRouter(api_key=api_key)
    response = client.chat.send(
        model="qwen/qwen3-vl-235b-a22b-instruct",
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
            root.after(0, lambda: on_error(str(exc)))

    threading.Thread(target=_run, daemon=True).start()


def generate_and_show_description(root, btn, image: Image, api_key: str | None) -> None:
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

    prompt = os.environ.get("PROMPT_DESCRIBE_IMAGE", DEFAULT_PROMPT)
    btn.configure(text="Generating...", state="disabled")

    def on_done(result: str) -> None:
        btn.configure(text="Generate Description", state="normal")
        messagebox.showinfo("Description", result, parent=root)

    def on_error(error_msg: str) -> None:
        btn.configure(text="Generate Description", state="normal")
        messagebox.showerror("Error", error_msg, parent=root)

    describe_image_async(root, image, api_key, prompt, on_done, on_error)