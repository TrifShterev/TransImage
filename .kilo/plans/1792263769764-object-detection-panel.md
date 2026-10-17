# Object Detection Panel

## Goal

Add an object-detection feature that reuses the generated image description, the image itself, and a user question. Detection is offloaded to `typesafe/jev-1.14` on OpenRouter.

---

## Decisions (from user Q&A)

- **Model:** `typesafe/jev-1.14` on OpenRouter; outputs bounding-box coordinates.
- **Button enable:** enabled only when **both** an image is loaded AND a description has been generated and cached.
- **Detection result display:** bounding-box rectangles + labels drawn on the image canvas.
- **Description caching:** stored on the `App` instance (`self.last_description`) so the panel can access it independently of the messagebox.

---

## Files changed

| File | Action |
|------|--------|
| `src/transimage/detection.py` | **NEW** — OpenRouter call, async wrapper, result parsing |
| `src/transimage/app.py` | **MODIFY** — cache description, detect button, panel, canvas overlays |
| `.env.example` | **MODIFY** — add `PROMPT_DETECT_OBJECTS` |
| `.env` | **MODIFY** — add `PROMPT_DETECT_OBJECTS` |

(No changes to `description.py` — caching happens in `app.py`'s `on_done` callback.)

---

## 1. New module — `src/transimage/detection.py`

### `detect_objects(image, api_key, description, prompt) -> list[dict]`

- Encodes `image` as base64 PNG data URL (same pattern as `description.py`).
- Calls `OpenRouter(api_key).chat.send(model="typesafe/jev-1.14", …)` with a message that includes:
  - The image
  - The existing description
  - The prompt (constructed from env `PROMPT_DETECT_OBJECTS` + the user question)
- Returns the parsed list of `{"label": str, "bbox": [x, y, w, h]}` dicts.
- Raises `ValueError` on malformed output.

### `detect_objects_async(root, image, api_key, description, prompt, on_done, on_error)`

- Threaded wrapper (same pattern as `describe_image_async` in `description.py`).
- On success: `root.after(0, lambda: on_done(result))`.
- On error: `root.after(0, lambda: on_error(str(exc)))`.

### Detection prompt design

The user-facing question is combined with a system prompt that asks the model to output bounding boxes as a JSON array:

```
You are an object-detection system.
Given an image and its description, answer the user's question.

Image description: {cached_description}
User question: {user_question}

Return ONLY a JSON array of detected objects, each with:
- "label": string (the object class name)
- "bbox": [x, y, w, h] where values are 0-1 normalized to image dimensions
  (x, y = top-left corner, w = width, h = height)

If nothing matches, return an empty array [].
```

This prompt is stored in env var `PROMPT_DETECT_OBJECTS` with a placeholder `{description}` and `{question}` that are substituted at runtime. The default fallback (if env var is missing) is the hardcoded prompt above.

---

## 2. Modify `src/transimage/app.py`

### 2a. New state on `App`

```python
self.last_description: str | None = None
self._detection_boxes: list[tuple[int, int, int, int, str]] | None = None
# Each tuple: (canvas_x, canvas_y, canvas_w, canvas_h, label)
```

### 2b. Cache description in existing handler

In `_on_generate_description`, the `on_done` callback currently calls `messagebox.showinfo("Description", result)` and re-enables the button. Change it to:

1. Store `self.last_description = result`.
2. Call `messagebox.showinfo("Description", result)` (keep the popup — UX doesn't change).
3. Call `self._update_detect_btn_state()`.

### 2c. New `_update_detect_btn_state()` helper

```python
def _update_detect_btn_state(self) -> None:
    has_image = self.source_path is not None
    has_desc = self.last_description is not None
    self.detect_btn.configure(state=tk.NORMAL if (has_image and has_desc) else tk.DISABLED)
```

Called from:
- `open_path()` (after setting source_path, clears description → DISABLED)
- `on_done` callback of description generation (NORMAL if both satisfied)

### 2d. New detect button in header

Placed after `self.generate_btn.place(...)`:

```python
self.detect_btn = tk.Button(
    header,
    text="Object Detection",
    bg=_HEADER_BG, fg="#ffffff",
    activebackground="#3c3c3c", activeforeground="#ffffff",
    font=self.menu_font,
    relief=tk.FLAT, borderwidth=0,
    padx=12, pady=4,
    state=tk.DISABLED,
    command=self._on_object_detection,
)
self.detect_btn.place(x=300, rely=0.5, anchor=tk.W)  # right of generate_btn at x=140
```

### 2e. Detection panel — `_on_object_detection()`

Opens a `tk.Toplevel`:

```
+----------------------------------------------------+
| Object Detection                          [X] Close |
+----------------------------------------------------+
| Description (read-only):                            |
| [ScrolledText widget — 50% of panel height]         |
|                                                     |
| --------------------------------------------------- |
|                                                     |
| Your question:                                      |
| [Text entry (2-3 lines)]                            |
|                                                     |
| [Detect]                                             |
+----------------------------------------------------+
```

Details:

- **Title**: "Object Detection"
- **Size**: 640×480, centered on parent.
- **Top half (50%)**: `tk.scrolledtext.ScrolledText` with `state=tk.DISABLED`, populated from `self.last_description`.
- **Bottom half**: A `tk.Label("Your question:")`, a `tk.Text` widget (3 lines high) for the user's question, and a `tk.Button("Detect")`.
- **Detect button handler**:
  1. Disables the Detect button (text: "Detecting…").
  2. Reads user question from the Text widget.
  3. Builds prompt by substituting `{description}` and `{question}` into `PROMPT_DETECT_OBJECTS`.
  4. Calls `detect_objects_async(...)` with `self.display_master`.
  5. `on_done`: parses result into `self._detection_boxes`, re-enables Detect button, calls `_paint()` to redraw image with overlays.
  6. `on_error`: `messagebox.showerror`, re-enables Detect button.
- **Panel is non-modal** (no `grab_set`) so the user can see the canvas update behind it.
- Closing the panel does not cancel an in-flight request (it completes silently).

### 2f. Draw detection boxes on canvas

Modify `_draw_image` so that after drawing the image, if `self._detection_boxes` is non‑None, it draws:

```python
for x, y, w, h, label in self._detection_boxes:
    self.viewport.create_rectangle(x, y, x + w, y + h,
                                    outline="#00ff00", width=2, tags="detection")
    self.viewport.create_text(x, y - 4, text=label,
                               fill="#00ff00", anchor=tk.SW,
                               font=(family, 10), tags="detection")
```

The bounding-box coordinates stored in `_detection_boxes` are already in canvas‑space (computed from the normalized model output, see coordinate mapping below).

### 2g. Coordinate mapping

The model receives `display_master` (max 4096px) and outputs normalized coords `[n_x, n_y, n_w, n_h]` (0–1). In `on_done`:

```python
master_w, master_h = self.display_master.size
# Get the viewport display size (computed by fit_image)
width, height = self.viewport.winfo_width(), self.viewport.winfo_height()
display_w, display_h, offset_x, offset_y = fit_image(
    master_w, master_h, width, height
)

detection_boxes = []
for item in detection_list:
    n_x, n_y, n_w, n_h = item["bbox"]
    # Map normalized → canvas coordinates
    canvas_x = offset_x + n_x * display_w
    canvas_y = offset_y + n_y * display_h
    canvas_w = n_w * display_w
    canvas_h = n_h * display_h
    detection_boxes.append((canvas_x, canvas_y, canvas_w, canvas_h, item["label"]))
self._detection_boxes = detection_boxes
```

Note: `fit_image` is already imported in `app.py`. The `on_done` callback runs on the main thread via `root.after(0, …)`, so viewport dimensions are safe to read.

### 2h. Clear detection state on new image

In `open_path()`, after existing lines, add:

```python
self.last_description = None
self._detection_boxes = None
self._update_detect_btn_state()
```

### 2i. Clear detection boxes on new description

When a new description is generated, previous detection results are stale. Add to the `on_done` callback:

```python
self._detection_boxes = None
```

### 2j. Refresh overlays on viewport resize

Since bounding boxes are stored in canvas coordinates and the canvas is being redrawn on resize, the existing `_schedule_paint` → `_paint` → `_draw_image` flow already handles redrawing. `_draw_image` will draw the current `self._detection_boxes` after the image.

---

## 3. Prompt env vars

**`.env`** and **`.env.example`** — add:

```
PROMPT_DETECT_OBJECTS=You are an object-detection system.\nGiven an image and its description, answer the user\'s question.\n\nImage description: {description}\nUser question: {question}\n\nReturn ONLY a JSON array of detected objects, each with:\n- \"label\": string (the object class name)\n- \"bbox\": [x, y, w, h] where values are 0-1 normalized to image dimensions\n  (x, y = top-left corner, w = width, h = height)\n\nIf nothing matches, return an empty array [].
```

(All one line with `\n` escapes.)

---

## Edge cases

| Case | Behaviour |
|------|-----------|
| No image loaded | Detect button disabled |
| Description not yet generated | Detect button disabled |
| Image loaded but description cleared (new image) | Detect button disabled, old boxes removed |
| Model returns malformed JSON | `on_error` shows `messagebox.showerror` with parse error |
| Model returns empty array `[]` | `_detection_boxes` set to empty list → no boxes drawn (image shown normally) |
| User closes panel during detection | Thread runs to completion, `root.after(0, …)` fires (panel gone), no error |
| Viewport resized after detection | Existing `_schedule_paint` → `_draw_image` redraws image + boxes at new positions? |

**Resize handling caveat**: Currently boxes are stored in canvas-pixel coordinates computed from the *old* viewport size. On resize, the fit dimensions change, so the old coordinates are wrong.

**Solution**: Store the **normalized** coordinates from the model instead of canvas-pixel coordinates, and compute canvas coordinates on every paint call. This way, `_draw_image` always draws boxes that match the current viewport.

Change `_detection_boxes` to store normalized data:

```python
self._detection_normalized: list[tuple[float, float, float, float, str]] | None = None
# (n_x, n_y, n_w, n_h, label)  — all 0-1 relative to display_master
```

In `_draw_image`, after computing `display_w, display_h, offset_x, offset_y`, if `self._detection_normalized` is set:

```python
for n_x, n_y, n_w, n_h, label in self._detection_normalized:
    canvas_x = offset_x + n_x * display_w
    canvas_y = offset_y + n_y * display_h
    canvas_w = n_w * display_w
    canvas_h = n_h * display_h
    self.viewport.create_rectangle(...)
    self.viewport.create_text(...)
```

---

## Validation

1. `uv run pytest` — all existing tests pass.
2. Manual: open image → generate description → "Object Detection" button appears enabled.
3. Manual: click "Object Detection" → panel opens with cached description in top half.
4. Manual: type a question → click "Detect" → wait for result → boxes appear on the image.
5. Manual: open a new image → description cleared → detect button disabled.
6. Manual: resize window after detection → boxes reposition correctly.
7. Manual: close panel in middle of detection → no crash, no leftover state.
8. Manual: model returns empty array → image shown cleanly, no boxes.
9. Manual: model returns malformed output → error dialog shown.

## Implementation order

1. Create `src/transimage/detection.py` with `detect_objects` and `detect_objects_async`.
2. Modify `src/transimage/app.py`:
   a. Add `last_description`, `_detection_normalized` state.
   b. Add `_update_detect_btn_state()`.
   c. Add `detect_btn` widget and `_on_object_detection` panel.
   d. Modify `open_path()` to clear description + boxes.
   e. Modify `_on_generate_description` to cache description.
   f. Modify `_draw_image` to draw detection boxes from normalized coords.
3. Add `PROMPT_DETECT_OBJECTS` to `.env` and `.env.example`.
4. Run `uv run pytest`, then manual smoke test.