import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageOps, ImageTk

from transimage.detection import detect_objects_async
from transimage.description import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    generate_and_show_description,
)
from transimage.export import (
    DEFAULT_EXPORT_FORMAT,
    build_export_path,
    export_dir,
    resolve_export_target,
    save_image,
)
from transimage.fit import fit_image
from transimage.modify import modify_image_async
from transimage.platform_ui import choose_font_family

_HEADER_BG = "#2b2b2b"
_VIEWPORT_BG = "#111111"
_ACCENT_BG = "#2d7ff9"
_ACCENT_ACTIVE_BG = "#1f6fe0"
_HEADER_HEIGHT = 44
_MASTER_LIMIT = 4096
_FILETYPES = (
    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff"),
    ("PNG", "*.png"),
    ("JPEG", "*.jpg *.jpeg"),
    ("GIF", "*.gif"),
    ("BMP", "*.bmp"),
    ("WEBP", "*.webp"),
    ("TIFF", "*.tif *.tiff"),
    ("All files", "*.*"),
)
_EXPORT_FILETYPES = (
    ("PNG", "*.png"),
    ("JPG", "*.jpg"),
    ("JPEG", "*.jpeg"),
)


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        oriented = ImageOps.exif_transpose(opened) or opened
        try:
            oriented.seek(0)
        except (EOFError, ValueError):
            pass
        frame = oriented.copy()
        frame.load()
    return frame


def make_display_master(image: Image.Image) -> Image.Image:
    width, height = image.size
    long_side = max(width, height)
    if long_side <= _MASTER_LIMIT:
        return image.copy()
    scale = _MASTER_LIMIT / long_side
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.source_path: Path | None = None
        self.source_image: Image.Image | None = None
        self.display_master: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._mapped = False
        self._after_id: str | None = None
        self._seen_size: tuple[int, int] | None = None
        self.last_description: str | None = None
        self._detection_normalized: (
            list[tuple[float, float, float, float, str]] | None
        ) = None
        self._build()

    def _build(self) -> None:
        self.root.title("TransImage")
        self.root.minsize(640, 480)
        self.root.geometry("1100x720")
        self.root.configure(bg=_VIEWPORT_BG)

        family = choose_font_family(tkfont.families(self.root))
        if family is None:
            family = tkfont.nametofont("TkDefaultFont").actual("family")
        self.wordmark_font = (family, 16, "bold")
        self.menu_font = (family, 12)

        header = tk.Frame(self.root, height=_HEADER_HEIGHT, bg=_HEADER_BG)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)

        wordmark = tk.Label(
            header,
            text="TransImage",
            bg=_HEADER_BG,
            fg="#ffffff",
            font=self.wordmark_font,
        )
        wordmark.place(x=16, rely=0.5, anchor=tk.W)

        toolbar = tk.Frame(header, bg=_HEADER_BG)
        toolbar.place(x=140, rely=0.5, anchor=tk.W)

        self.generate_btn = tk.Button(
            toolbar,
            text="Generate Description",
            bg=_HEADER_BG, fg="#ffffff",
            activebackground="#3c3c3c", activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT, borderwidth=0,
            padx=12, pady=4,
            state=tk.DISABLED,
            command=self._on_generate_description,
        )
        self.generate_btn.pack(side=tk.LEFT)

        self.language_var = tk.StringVar(value=DEFAULT_LANGUAGE)
        language_btn = tk.Menubutton(
            toolbar,
            textvariable=self.language_var,
            bg="#3c3c3c", fg="#ffffff",
            activebackground="#4a4a4a", activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT, borderwidth=0,
            highlightthickness=0,
            padx=8, pady=4,
            indicatoron=True,
        )
        language_menu = tk.Menu(language_btn, tearoff=False, font=self.menu_font)
        for code, (_english, native) in LANGUAGES.items():
            language_menu.add_radiobutton(
                label=f"{code} — {native}",
                value=code,
                variable=self.language_var,
            )
        language_btn.configure(menu=language_menu)
        language_btn.pack(side=tk.LEFT, padx=(0, 16))

        self.detect_btn = tk.Button(
            toolbar,
            text="Object Detection",
            bg=_HEADER_BG, fg="#ffffff",
            activebackground="#3c3c3c", activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT, borderwidth=0,
            padx=12, pady=4,
            state=tk.DISABLED,
            command=self._on_object_detection,
        )
        self.detect_btn.pack(side=tk.LEFT)

        self.modify_btn = tk.Button(
            toolbar,
            text="Modify image",
            bg=_HEADER_BG, fg="#ffffff",
            activebackground="#3c3c3c", activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT, borderwidth=0,
            padx=12, pady=4,
            state=tk.DISABLED,
            command=self._on_modify_image,
        )
        self.modify_btn.pack(side=tk.LEFT)

        self.export_btn = tk.Button(
            toolbar,
            text="Export image",
            bg=_HEADER_BG, fg="#ffffff",
            activebackground="#3c3c3c", activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT, borderwidth=0,
            padx=12, pady=4,
            state=tk.DISABLED,
            command=self._on_export_image,
        )
        self.export_btn.pack(side=tk.LEFT)
        self.export_type_var = tk.StringVar(value=DEFAULT_EXPORT_FORMAT)

        open_button = tk.Button(
            header,
            text="Open Image...",
            bg=_HEADER_BG, fg="#ffffff",
            activebackground="#3c3c3c", activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT, borderwidth=0,
            padx=12, pady=4,
            command=self.open_image,
        )
        open_button.place(relx=1.0, x=-8, rely=0.5, anchor=tk.E)

        self.viewport = tk.Canvas(
            self.root,
            bg=_VIEWPORT_BG,
            highlightthickness=0,
            bd=0,
        )
        self.viewport.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.viewport.bind("<Configure>", self._on_configure)
        self.viewport.bind("<Map>", self._on_map)
        self.root.bind("<Control-o>", self._on_open_shortcut)
        self.root.bind("<Command-o>", self._on_open_shortcut)
        self.root.bind("<Destroy>", self._on_destroy, add="+")

    def open_image(self) -> None:
        kwargs: dict[str, str] = {}
        if self.source_path is not None:
            kwargs["initialdir"] = str(self.source_path.parent)
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Open Image",
            filetypes=_FILETYPES,
            **kwargs,
        )
        if not selected:
            return
        self.open_path(Path(selected))

    def open_path(self, path: Path) -> None:
        try:
            source = load_image(path)
            master = make_display_master(source)
        except Exception as exc:
            messagebox.showerror(
                "TransImage",
                f"{path.name}\n{exc}",
                parent=self.root,
            )
            return
        self.source_path = path
        self.source_image = source
        self.display_master = master
        self.generate_btn.configure(state=tk.NORMAL)
        self.modify_btn.configure(state=tk.NORMAL)
        self.export_btn.configure(state=tk.NORMAL)
        self.last_description = None
        self._detection_normalized = None
        self._update_detect_btn_state()
        if self._mapped:
            self._paint()

    def _on_open_shortcut(self, _event: tk.Event) -> str:
        self.open_image()
        return "break"

    def _on_generate_description(self) -> None:
        master = self.display_master
        generate_and_show_description(
            self.root,
            self.generate_btn,
            master,
            os.environ.get("OPENROUTER_API_KEY"),
            after_success=lambda result: self._on_description_done(master, result),
            language=self.language_var.get(),
        )

    def _on_description_done(self, master: Image.Image | None, result: str) -> None:
        if self.display_master is not master:
            return
        self.last_description = result
        self._detection_normalized = None
        self._update_detect_btn_state()

    def _update_detect_btn_state(self) -> None:
        has_image = self.source_path is not None
        has_desc = self.last_description is not None
        self.detect_btn.configure(
            state=tk.NORMAL if (has_image and has_desc) else tk.DISABLED
        )

    def _accent_button(self, parent: tk.Misc, text: str) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            bg=_ACCENT_BG, fg="#ffffff",
            activebackground=_ACCENT_ACTIVE_BG, activeforeground="#ffffff",
            disabledforeground="#c7d6f5",
            font=(self.menu_font[0], self.menu_font[1], "bold"),
            relief=tk.FLAT, borderwidth=0,
            highlightthickness=0,
            padx=22, pady=7,
            cursor="hand2",
        )

    def _finalize_dialog(self, panel: tk.Toplevel, width: int, height: int) -> None:
        # Never let the window be smaller than its content (keeps buttons visible).
        panel.update_idletasks()
        min_w, min_h = panel.winfo_reqwidth(), panel.winfo_reqheight()
        panel.minsize(min_w, min_h)
        new_w, new_h = max(width, min_w), max(height, min_h)
        if (new_w, new_h) != (width, height):
            panel.geometry(f"{new_w}x{new_h}")

    def _on_object_detection(self) -> None:
        if self.display_master is None:
            return
        description = self.last_description or ""

        panel = tk.Toplevel(self.root)
        panel.title("Object Detection")
        panel.configure(bg=_HEADER_BG)
        panel.transient(self.root)

        width, height = 640, 480
        parent_x = self.root.winfo_rootx() + max(
            0, (self.root.winfo_width() - width) // 2
        )
        parent_y = self.root.winfo_rooty() + max(
            0, (self.root.winfo_height() - height) // 2
        )
        panel.geometry(f"{width}x{height}+{parent_x}+{parent_y}")

        area = tk.Frame(panel, bg=_HEADER_BG)
        area.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(1, weight=1)

        tk.Label(
            area,
            text="Description (read-only):",
            bg=_HEADER_BG,
            fg="#ffffff",
            font=self.menu_font,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        desc_view = scrolledtext.ScrolledText(
            area,
            height=6,
            width=40,
            wrap=tk.WORD,
            font=self.menu_font,
            bg="#1e1e1e",
            fg="#ffffff",
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        desc_view.grid(row=1, column=0, sticky="nsew")
        desc_view.configure(state=tk.NORMAL)
        desc_view.insert("1.0", description)
        desc_view.configure(state=tk.DISABLED)

        ttk.Separator(area, orient=tk.HORIZONTAL).grid(
            row=2, column=0, sticky="ew", pady=10
        )

        tk.Label(
            area,
            text="Your question:",
            bg=_HEADER_BG,
            fg="#ffffff",
            font=self.menu_font,
        ).grid(row=3, column=0, sticky="w", pady=(0, 4))

        question_view = tk.Text(
            area,
            height=3,
            width=40,
            wrap=tk.WORD,
            font=self.menu_font,
            bg="#1e1e1e",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
        )
        question_view.grid(row=4, column=0, sticky="ew")

        button_bar = tk.Frame(area, bg=_HEADER_BG)
        button_bar.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        detect_btn = self._accent_button(button_bar, "Find object")
        detect_btn.pack(side=tk.RIGHT)
        self._finalize_dialog(panel, width, height)

        def panel_alive() -> bool:
            try:
                return bool(panel.winfo_exists())
            except tk.TclError:
                return False

        def on_detect_click() -> None:
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                messagebox.showerror(
                    "TransImage",
                    "No API key configured.\n"
                    "Set OPENROUTER_API_KEY in .env",
                    parent=panel,
                )
                return
            question = question_view.get("1.0", "end-1c").strip()
            if not question:
                messagebox.showerror(
                    "Object Detection",
                    "Please enter a question.",
                    parent=panel,
                )
                return
            detect_btn.configure(text="Finding...", state=tk.DISABLED)

            def on_done(result: list[dict]) -> None:
                if not panel_alive():
                    return
                detect_btn.configure(text="Find object", state=tk.NORMAL)
                boxes = []
                for item in result:
                    n_x, n_y, n_w, n_h = item["bbox"]
                    label = str(item["label"])
                    if len(label) > 80:
                        label = label[:77] + "..."
                    boxes.append(
                        (float(n_x), float(n_y), float(n_w), float(n_h), label)
                    )
                self._detection_normalized = boxes
                self._paint()

            def on_error(error_msg: str) -> None:
                if not panel_alive():
                    return
                detect_btn.configure(text="Find object", state=tk.NORMAL)
                messagebox.showerror("Error", error_msg, parent=panel)

            detect_objects_async(
                self.root,
                self.display_master,
                api_key,
                self.last_description or "",
                question,
                on_done,
                on_error,
            )

        detect_btn.configure(command=on_detect_click)

    def _on_modify_image(self) -> None:
        if self.display_master is None:
            return
        description = self.last_description or ""

        panel = tk.Toplevel(self.root)
        panel.title("Modify image")
        panel.configure(bg=_HEADER_BG)
        panel.transient(self.root)

        width, height = 640, 520
        parent_x = self.root.winfo_rootx() + max(
            0, (self.root.winfo_width() - width) // 2
        )
        parent_y = self.root.winfo_rooty() + max(
            0, (self.root.winfo_height() - height) // 2
        )
        panel.geometry(f"{width}x{height}+{parent_x}+{parent_y}")

        area = tk.Frame(panel, bg=_HEADER_BG)
        area.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(1, weight=1)

        tk.Label(
            area,
            text="Description (read-only):",
            bg=_HEADER_BG,
            fg="#ffffff",
            font=self.menu_font,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        desc_view = scrolledtext.ScrolledText(
            area,
            height=6,
            width=40,
            wrap=tk.WORD,
            font=self.menu_font,
            bg="#1e1e1e",
            fg="#ffffff",
            relief=tk.FLAT,
            state=tk.DISABLED,
        )
        desc_view.grid(row=1, column=0, sticky="nsew")
        desc_view.configure(state=tk.NORMAL)
        desc_view.insert("1.0", description or "No description generated.")
        desc_view.configure(state=tk.DISABLED)

        ttk.Separator(area, orient=tk.HORIZONTAL).grid(
            row=2, column=0, sticky="ew", pady=10
        )

        tk.Label(
            area,
            text="Modification request:",
            bg=_HEADER_BG,
            fg="#ffffff",
            font=self.menu_font,
        ).grid(row=3, column=0, sticky="w", pady=(0, 4))

        request_view = tk.Text(
            area,
            height=3,
            width=40,
            wrap=tk.WORD,
            font=self.menu_font,
            bg="#1e1e1e",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
        )
        request_view.grid(row=4, column=0, sticky="ew")

        button_bar = tk.Frame(area, bg=_HEADER_BG)
        button_bar.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        apply_btn = self._accent_button(button_bar, "Apply")
        apply_btn.pack(side=tk.RIGHT)
        self._finalize_dialog(panel, width, height)

        in_flight = [False]

        def panel_alive() -> bool:
            try:
                return bool(panel.winfo_exists())
            except tk.TclError:
                return False

        def on_apply_click() -> None:
            if in_flight[0]:
                return
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                messagebox.showerror(
                    "TransImage",
                    "No API key configured.\n"
                    "Set OPENROUTER_API_KEY in .env",
                    parent=panel,
                )
                return
            request = request_view.get("1.0", "end-1c").strip()
            if not request:
                messagebox.showerror(
                    "Modify Image",
                    "Please enter a modification request.",
                    parent=panel,
                )
                return
            image = self.display_master
            snapshot_desc = self.last_description or ""
            in_flight[0] = True
            apply_btn.configure(text="Modifying...", state=tk.DISABLED)

            def on_done(result) -> None:
                in_flight[0] = False
                if self.display_master is image:
                    self.source_image = result
                    self.display_master = make_display_master(result)
                    self._detection_normalized = None
                    self._paint()
                    request_view.delete("1.0", "end")
                if panel_alive():
                    apply_btn.configure(text="Apply", state=tk.NORMAL)

            def on_error(error_msg: str) -> None:
                in_flight[0] = False
                if panel_alive():
                    apply_btn.configure(text="Apply", state=tk.NORMAL)
                    messagebox.showerror("Error", error_msg, parent=panel)

            modify_image_async(
                self.root,
                image,
                api_key,
                request,
                snapshot_desc,
                on_done,
                on_error,
            )

        apply_btn.configure(command=on_apply_click)

    def _on_export_image(self) -> None:
        image = self.source_image
        if image is None:
            return
        stem = self.source_path.stem if self.source_path is not None else "image"
        folder = export_dir()
        kwargs: dict[str, str] = {}
        try:
            folder.mkdir(parents=True, exist_ok=True)
            kwargs["initialdir"] = str(folder)
        except OSError:
            pass
        fmt = self.export_type_var.get()
        suggested = build_export_path(folder, stem, fmt, datetime.now())
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export image",
            filetypes=_EXPORT_FILETYPES,
            defaultextension=f".{fmt.lower()}",
            initialfile=suggested.name,
            typevariable=self.export_type_var,
            **kwargs,
        )
        if not selected:
            return
        saved, fmt = resolve_export_target(selected, self.export_type_var.get())
        if str(saved) != str(Path(selected)) and saved.exists():
            if not messagebox.askyesno(
                "Export image",
                f"{saved.name} already exists.\nDo you want to replace it?",
                parent=self.root,
            ):
                return
        try:
            save_image(image, saved, fmt)
        except Exception as exc:
            messagebox.showerror(
                "Export image",
                f"Could not export the image.\n{exc}",
                parent=self.root,
            )
            return
        messagebox.showinfo(
            "Export image",
            f"Saved to:\n{saved}",
            parent=self.root,
        )

    def _on_map(self, _event: tk.Event) -> None:
        self._mapped = True
        self._schedule_paint()

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is not self.viewport or not self._mapped:
            return
        size = (int(event.width), int(event.height))
        if size == self._seen_size:
            return
        self._seen_size = size
        self._schedule_paint()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self.root or self._after_id is None:
            return
        try:
            self.root.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _schedule_paint(self) -> None:
        if not self._mapped:
            return
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        self._after_id = self.root.after(80, self._paint)

    def _paint(self) -> None:
        self._after_id = None
        if not self._mapped:
            return
        width = self.viewport.winfo_width()
        height = self.viewport.winfo_height()
        if width <= 1 or height <= 1:
            return
        if self.display_master is None:
            self._draw_hint(width, height)
            return
        self._draw_image(width, height)

    def _draw_hint(self, width: int, height: int) -> None:
        self.viewport.delete("all")
        self._photo = None
        self.viewport.create_text(
            width / 2,
            height / 2,
            text="Open an image",
            fill="#a3a3a3",
            font=self.wordmark_font,
            anchor=tk.CENTER,
        )

    def _draw_image(self, width: int, height: int) -> None:
        master = self.display_master
        if master is None:
            return
        image_w, image_h = master.size
        display_w, display_h, offset_x, offset_y = fit_image(
            image_w, image_h, width, height
        )
        if display_w <= 0 or display_h <= 0:
            return
        if (display_w, display_h) == master.size:
            resized = master
        else:
            resized = master.resize(
                (display_w, display_h), Image.Resampling.LANCZOS
            )
        photo = ImageTk.PhotoImage(resized.convert("RGBA"))
        self._photo = photo
        self.viewport.delete("all")
        self.viewport.create_image(
            offset_x,
            offset_y,
            image=self._photo,
            anchor=tk.NW,
            tags="image",
        )
        if self._detection_normalized is not None:
            label_family = self.wordmark_font[0]
            for n_x, n_y, n_w, n_h, label in self._detection_normalized:
                box_x = offset_x + n_x * display_w
                box_y = offset_y + n_y * display_h
                box_w = n_w * display_w
                box_h = n_h * display_h
                self.viewport.create_rectangle(
                    box_x,
                    box_y,
                    box_x + box_w,
                    box_y + box_h,
                    outline="#00ff00",
                    width=2,
                    tags="detection",
                )
                self.viewport.create_text(
                    box_x,
                    box_y - 4,
                    text=label,
                    fill="#00ff00",
                    anchor=tk.SW,
                    font=(label_family, 10),
                    tags="detection",
                )


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
