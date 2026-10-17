import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageOps, ImageTk

from transimage.fit import fit_image
from transimage.platform_ui import accelerator_label, choose_font_family

_HEADER_BG = "#2b2b2b"
_VIEWPORT_BG = "#111111"
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

        file_button = tk.Menubutton(
            header,
            text="File",
            bg=_HEADER_BG,
            fg="#ffffff",
            activebackground="#3c3c3c",
            activeforeground="#ffffff",
            font=self.menu_font,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=12,
            pady=4,
        )
        file_button.place(relx=1.0, x=-8, rely=0.5, anchor=tk.E)
        self.file_menu = tk.Menu(
            file_button,
            tearoff=0,
            bg=_HEADER_BG,
            fg="#ffffff",
            activebackground="#3c3c3c",
            activeforeground="#ffffff",
            font=self.menu_font,
        )
        self.file_menu.add_command(
            label="Open Image...",
            accelerator=accelerator_label(),
            command=self.open_image,
        )
        self.file_menu.add_command(label="Exit", command=self.root.destroy)
        file_button.configure(menu=self.file_menu)

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
        if self._mapped:
            self._paint()

    def _on_open_shortcut(self, _event: tk.Event) -> str:
        self.open_image()
        return "break"

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


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
