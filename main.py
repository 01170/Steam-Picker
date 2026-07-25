"""

Steam Picker

a tiny slot machine that picks out what to play from your installed steam games.

you can't lose at these slots.

"""

import os
import random
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from PIL import Image, ImageOps, ImageTk

from game_filter import add_to_excluded, filter_games
from steam_scanner import scan_installed_games


BASE_DIR = Path(__file__).resolve().parent
ART_PATH = BASE_DIR / "art" / "cabinet.png"
SKINS_DIR = BASE_DIR / "SKINS"

TRANSPARENT_KEY = "#102346"

# button adjustments

LOGO_CENTER = (106, 58)
LOGO_HIT_RADIUS = 24
CABINET_SIZE = (240, 320)
SCREEN_RECT = (38, 105, 134, 146)
NAME_BAR_RECT = (9, 281, 193, 20)
BALL_CENTER = (220, 100)
BALL_HIT_RADIUS = 15

ICON_SIZE = 108
NAME_COLOR = "#dbe4f0"

SPIN_FRAME_DELAYS = [
    40, 40, 45, 50, 55, 65, 75, 90, 105, 125, 150, 180, 220, 270
]

WINNER_BOUNCE_STEPS = (-3, -3, 2, 2, 1, 1)
WINNER_BOUNCE_DELAY = 45
INPUT_COOLDOWN_MS = 250


def discover_skins() -> dict[str, Path]:
    skins = {"Default": ART_PATH}
    if not SKINS_DIR.is_dir():
        return skins

    for folder in sorted(SKINS_DIR.iterdir(), key=lambda path: path.name.casefold()):
        if not folder.is_dir():
            continue
        try:
            cabinet = next(
                (
                    path
                    for path in folder.iterdir()
                    if path.is_file() and path.name.casefold() == "cabinet.png"
                ),
                None,
            )
        except OSError:
            cabinet = None
        if cabinet:
            skins[folder.name] = cabinet
    return skins


def load_icon(path: str, size: int = ICON_SIZE) -> Image.Image:
    if path:
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
            resample = (
                Image.Resampling.NEAREST
                if image.width < size or image.height < size
                else Image.Resampling.LANCZOS
            )
            image = ImageOps.fit(image, (size, size), resample)
            backing = Image.new("RGBA", (size, size), "#0d0d0c")
            return Image.alpha_composite(backing, image)
        except (OSError, ValueError):
            pass
    return Image.new("RGBA", (size, size), "#3f3f3d")


class SlotMachineApp:
    def __init__(self, games):
        self.games = games
        self.current_pick = random.choice(games)
        self.spinning = False
        self.input_locked = False
        self.skins = discover_skins()
        self.current_skin = "Default"

        # Keep references so Tk does not garbage-collect displayed images.
        self.cabinet_photo = None
        self.icon_photo = None

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT_KEY)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.attributes("-topmost", True)

        self._build_canvas()
        self._build_context_menu()
        self._render_pick()

        self.root.bind("<Escape>", lambda event: self.root.destroy())

    def _build_canvas(self):
        width, height = CABINET_SIZE
        self.canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
        )
        self.canvas.pack()

        self.cabinet_item = self.canvas.create_image(0, 0, anchor="nw")
        self._change_skin("Default")

        sx, sy, sw, sh = SCREEN_RECT
        self.icon_item = self.canvas.create_image(
            sx + sw // 2,
            sy + sh // 2,
            anchor="center",
        )

        nx, ny, nw, nh = NAME_BAR_RECT
        self.name_font = tkfont.Font(family="Consolas", size=8, weight="bold")
        self.name_max_width = nw - 10
        self.name_item = self.canvas.create_text(
            nx + nw // 2,
            ny + nh // 2,
            text="",
            fill=NAME_COLOR,
            font=self.name_font,
            anchor="center",
        )

        self.canvas.bind("<Button-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._do_drag)
        self.canvas.bind("<Button-3>", self._show_context_menu)

        bx, by = BALL_CENTER
        radius = BALL_HIT_RADIUS
        self.ball_hit = self.canvas.create_oval(
            bx - radius,
            by - radius,
            bx + radius,
            by + radius,
            fill="",
            outline="",
        )
        self.canvas.tag_bind(self.ball_hit, "<Button-1>", self._on_ball_click)

        lx, ly = LOGO_CENTER
        radius = LOGO_HIT_RADIUS
        self.logo_hit = self.canvas.create_oval(
            lx - radius,
            ly - radius,
            lx + radius,
            ly + radius,
            fill="",
            outline="",
        )
        self.canvas.tag_bind(
            self.logo_hit,
            "<Button-1>",
            self._launch_current_game,
        )
        self.canvas.tag_bind(
            self.logo_hit,
            "<Enter>",
            lambda event: self.canvas.configure(cursor="hand2"),
        )
        self.canvas.tag_bind(
            self.logo_hit,
            "<Leave>",
            lambda event: self.canvas.configure(cursor=""),
        )

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=False)
        self.context_menu.add_command(
            label="Play",
            command=self._launch_current_game,
        )
        self.context_menu.add_command(label="Reroll", command=self.reroll)
        self.context_menu.add_command(
            label="Exclude",
            command=self.exclude_current,
        )
        self.context_menu.add_separator()

        skin_menu = tk.Menu(self.context_menu, tearoff=False)
        for skin_name in self.skins:
            skin_menu.add_command(
                label=skin_name,
                command=lambda name=skin_name: self._change_skin(name),
            )
        self.context_menu.add_cascade(label="Change Skin", menu=skin_menu)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Exit", command=self.root.destroy)

    def _show_context_menu(self, event):
        if self.input_locked:
            return "break"
        self.context_menu.entryconfigure(
            0,
            label=f"Play {self._fit_name(self.current_pick.name)}",
        )
        self.context_menu.entryconfigure(
            2,
            label=f"Exclude {self._fit_name(self.current_pick.name)}",
        )
        self.context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _change_skin(self, skin_name: str):
        if self.input_locked and self.cabinet_photo is not None:
            return

        path = self.skins.get(skin_name)
        if path is None:
            return
        try:
            with Image.open(path) as source:
                cabinet = source.convert("RGBA")
        except OSError as exc:
            print(f"Couldn't load skin {skin_name}: {exc}")
            return

        if cabinet.size != CABINET_SIZE:
            print(
                f"Couldn't load skin {skin_name}: expected {CABINET_SIZE[0]}x"
                f"{CABINET_SIZE[1]}, got {cabinet.width}x{cabinet.height}"
            )
            return

        self.cabinet_photo = ImageTk.PhotoImage(cabinet)
        self.canvas.itemconfigure(self.cabinet_item, image=self.cabinet_photo)
        self.current_skin = skin_name

    def _launch_current_game(self, event=None):
        if self.input_locked or not self.current_pick:
            return "break"
        try:
            os.startfile(f"steam://rungameid/{self.current_pick.appid}")
        except OSError as exc:
            print(f"Couldn't launch {self.current_pick.name}: {exc}")
        return "break"

    def _on_ball_click(self, event):
        self.start_spin()
        return "break"

    def _fit_name(self, name: str) -> str:
        if self.name_font.measure(name) <= self.name_max_width:
            return name
        ellipsis = "…"
        low, high = 0, len(name)
        while low < high:
            midpoint = (low + high + 1) // 2
            candidate = name[:midpoint] + ellipsis
            if self.name_font.measure(candidate) <= self.name_max_width:
                low = midpoint
            else:
                high = midpoint - 1
        return name[:low] + ellipsis

    def _render_game(self, game):
        icon_image = load_icon(game.icon_path)
        self.icon_photo = ImageTk.PhotoImage(icon_image)
        self.canvas.itemconfigure(self.icon_item, image=self.icon_photo)
        self.canvas.itemconfigure(
            self.name_item,
            text=self._fit_name(game.name),
        )

    def _render_pick(self):
        self._render_game(self.current_pick)

    def start_spin(self):
        if self.input_locked or not self.games:
            return

        if len(self.games) < 2:
            self._render_pick()
            return

        self.input_locked = True
        self.spinning = True
        choices = [
            game for game in self.games
            if game.appid != self.current_pick.appid
        ]
        final_pick = random.choice(choices)
        sequence = [
            random.choice(self.games) for _ in SPIN_FRAME_DELAYS
        ] + [final_pick]
        self._play_spin_frame(sequence, 0)

    def _play_spin_frame(self, sequence, index):
        self._render_game(sequence[index])
        if index < len(SPIN_FRAME_DELAYS):
            delay = SPIN_FRAME_DELAYS[index]
            self.root.after(
                delay,
                lambda: self._play_spin_frame(sequence, index + 1),
            )
            return

        self.current_pick = sequence[index]
        self._play_winner_bounce(0)

    def _play_winner_bounce(self, index):
        if index < len(WINNER_BOUNCE_STEPS):
            self.canvas.move(
                self.icon_item,
                0,
                WINNER_BOUNCE_STEPS[index],
            )
            self.root.after(
                WINNER_BOUNCE_DELAY,
                lambda: self._play_winner_bounce(index + 1),
            )
            return

        self.spinning = False
        self.root.after(INPUT_COOLDOWN_MS, self._unlock_input)

    def _unlock_input(self):
        self.input_locked = False

    def reroll(self):
        self.start_spin()

    def exclude_current(self):
        if self.input_locked or not self.current_pick:
            return

        add_to_excluded(self.current_pick.appid)
        self.games = [
            game for game in self.games
            if game.appid != self.current_pick.appid
        ]
        if not self.games:
            print("No games remain after exclusions.")
            self.root.destroy()
            return

        self.current_pick = random.choice(self.games)
        self._render_pick()

    def _start_drag(self, event):
        if self.input_locked:
            return
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        if self.input_locked or not hasattr(self, "_drag_x"):
            return
        x = self.root.winfo_pointerx() - self._drag_x
        y = self.root.winfo_pointery() - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    print("Scanning your Steam library...")
    all_games = scan_installed_games()

    print("Filtering out non-games (first run may take a few seconds)...")

    def progress(done, total):
        print(f"  checking... {done}/{total}", end="\r")

    eligible_games = filter_games(all_games, progress_callback=progress)
    print(f"\n{len(eligible_games)} games ready to roll.\n")

    if not eligible_games:
        print("No eligible games found - check your exclude list or filtering.")
    else:
        SlotMachineApp(eligible_games).run()