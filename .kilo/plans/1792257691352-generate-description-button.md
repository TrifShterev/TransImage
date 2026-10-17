# Plan: "Generate Description" Button

## Files changed
- `.env` — add `PROMPT_DESCRIBE_IMAGE`
- `.env.example` — add `PROMPT_DESCRIBE_IMAGE`
- `src/transimage/description.py` — **new file**
- `src/transimage/app.py` — add button + handler

---

### 1. Add prompt env var

**`.env`** and **`.env.example`** — add:

```
PROMPT_DESCRIBE_IMAGE=Describe this image in detail, including the main subject, composition, colors, lighting, and any visible text or notable elements. Be concise but thorough.
```

---

### 2. New module: `src/transimage/description.py`

Two public functions:

**`describe_image(image, api_key, prompt) -> str`**
- Encode image to base64 data URL (`data:image/png;base64,...`)
- Call `OpenRouter(api_key=api_key).chat.send(model="qwen/qwen3-vl-235b-a22b-instruct", messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}]}], max_tokens=2048)`
- Return `response.choices[0].message.content`

**`describe_image_async(root, image, api_key, prompt, on_done, on_error)`**
- Wraps `describe_image` in a `threading.Thread`
- On success: `root.after(0, lambda: on_done(result))`
- On error: `root.after(0, lambda: on_error(str(exc)))`

The `openrouter` SDK uses `httpx` (threadsafe). No extra locking needed.

---

### 3. Add button to header in `app.py`

In `App._build()`, after the wordmark `place()` (line ~84), add:

```python
self.generate_btn = tk.Button(
    header,
    text="Generate Description",
    bg=_HEADER_BG, fg="#ffffff",
    activebackground="#3c3c3c", activeforeground="#ffffff",
    font=self.menu_font,
    relief=tk.FLAT, borderwidth=0,
    padx=12, pady=4,
    state=tk.DISABLED,
    command=self._on_generate_description,
)
self.generate_btn.place(x=140, rely=0.5, anchor=tk.W)
```

Also add `import os` and `import threading` to the existing imports at the top.

---

### 4. Handler in `App`

**`_on_generate_description`**:
1. Check `OPENROUTER_API_KEY` env var — if empty/missing, show `messagebox.showerror("No API key configured")` and return
2. Read prompt from `PROMPT_DESCRIBE_IMAGE` env var (fallback to a hardcoded default)
3. Disable button, change text to `"Generating..."`
4. Call `describe_image_async` with `self.display_master` (not source — keeps payload small)
5. On success (`on_done`): re-enable button, restore text, show result via `messagebox.showinfo("Description", result)`
6. On error (`on_error`): re-enable button, restore text, show error via `messagebox.showerror("Error", error_msg)`

---

### 5. Button state wiring

- Initially `state=tk.DISABLED`
- Enable in `open_path()` after `self.source_image` is set and `self.display_master` is set
- Disabled if no image is loaded (no current way to clear — out of scope)

---

### 6. Edge cases

| Case | Behaviour |
|------|-----------|
| No image loaded | Button disabled — can't click |
| API key missing | Early return with `messagebox.showerror` |
| Network error | `on_error` fires, shows error in `messagebox.showerror` |
| Rate limited / 429 | `openrouter` raises typed exception, caught by `on_error` |
| Very large image | Use `display_master` (max 4096px) to keep base64 payload reasonable |
| Button double-click | Button disabled during generation, re-enabled on completion/error |

---

## Validation

1. `uv run pytest` — all existing tests still pass
2. Manual: launch app, open image, click button, verify description appears in popup
3. Manual: click with no API key set — verify error popup appears
4. Manual: button is disabled before an image is loaded