"""
main.py

The slot machine window - real cabinet artwork as the background, with
the live icon/name rendered through the screen cutout and the spin
triggered by clicking the handle ball.
"""

import os
import random
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk, ImageOps

from steam_scanner import scan_installed_games
from game_filter import filter_games, add_to_excluded

ART_PATH = os.path.join(os.path.dirname(__file__), "art", "cabinet.png")

# The color tkinter treats as transparent on Windows - must never appear
# anywhere else in the UI, or that spot goes see-through too.
TRANSPARENT_KEY = "#ff00ff"

# Measured directly from cabinet.png (240x320 canvas) - see conversation
# for how these were derived. If the art changes, re-measure and update
# these rather than guessing.
CABINET_SIZE = (240, 320)
SCREEN_RECT = (38, 105, 134, 146)   # x, y, w, h - the white cutout
NAME_BAR_RECT = (9, 284, 193, 20)   # x, y, w, h - bottom blue bar
BALL_CENTER = (220, 100)
BALL_HIT_RADIUS = 15                # a little larger than the drawn ball for easier clicking

ICON_SIZE = 108  # fits inside SCREEN_RECT with breathing room
NAME_COLOR = "#dbe4f0"

# Milliseconds between each spin frame - short gaps at first (fast blur of
# icons), lengthening toward the end for an ease-out "clunk to a stop"
# feel. The final landed icon is shown after the last delay in this list.
SPIN_FRAME_DELAYS = [40, 40, 45, 50, 55, 65, 75, 90, 105, 125, 150, 180, 220, 270]


def load_icon(path: str, size: int = ICON_SIZE) -> Image.Image:
    """Load and crop an icon to a square thumbnail, composited onto a
    dark backing so transparent .ico files don't show black smudges."""
    if path:
        try:
            img = Image.open(path).convert("RGBA")
            img = ImageOps.fit(img, (size, size), Image.LANCZOS)
            backing = Image.new("RGBA", (size, size), "#0d0d0c")
            return Image.alpha_composite(backing, img)
        except Exception:
            pass
    return Image.new("RGBA", (size, size), "#3f3f3d")


class SlotMachineApp:
    def __init__(self, games):
        self.games = games
        self.current_pick = random.choice(games)
        self.spinning = False
        # Keep references so PhotoImage objects don't get garbage collected
        self.cabinet_photo = None
        self.icon_photo = None

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT_KEY)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.attributes("-topmost", True)

        self._build_canvas()
        self._render_pick()

        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def _build_canvas(self):
        w, h = CABINET_SIZE
        self.canvas = tk.Canvas(self.root, width=w, height=h,
                                 bg=TRANSPARENT_KEY, highlightthickness=0)
        self.canvas.pack()

        cabinet_img = Image.open(ART_PATH).convert("RGBA")
        self.cabinet_photo = ImageTk.PhotoImage(cabinet_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.cabinet_photo)

        sx, sy, sw, sh = SCREEN_RECT
        self.icon_item = self.canvas.create_image(
            sx + sw // 2, sy + sh // 2, anchor="center"
        )

        nx, ny, nw, nh = NAME_BAR_RECT
        self.name_font = tkfont.Font(family="Consolas", size=8, weight="bold")
        self.name_max_width = nw - 10
        self.name_item = self.canvas.create_text(
            nx + nw // 2, ny + nh // 2, text="", fill=NAME_COLOR,
            font=self.name_font, anchor="center"
        )

        # Dragging: bound to the whole canvas, but the ball's own binding
        # (below) returns "break" so a click on the ball spins instead of
        # starting a drag.
        self.canvas.bind("<Button-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._do_drag)

        # Invisible hit zone over the handle ball
        bx, by = BALL_CENTER
        r = BALL_HIT_RADIUS
        self.ball_hit = self.canvas.create_oval(
            bx - r, by - r, bx + r, by + r, fill="", outline=""
        )
        self.canvas.tag_bind(self.ball_hit, "<Button-1>", self._on_ball_click)

        # Right-click anywhere on the screen area excludes the current pick
        self.canvas.tag_bind(self.icon_item, "<Button-3>",
                              lambda e: self.exclude_current())

    def _on_ball_click(self, event):
        if not self.spinning:
            self.start_spin()
        return "break"  # stop this click from also starting a drag

    def _fit_name(self, name: str) -> str:
        """Truncate to the bar's actual pixel width (not a guessed char
        count), so long titles always end in a clean ellipsis instead of
        wrapping or overflowing the bar."""
        if self.name_font.measure(name) <= self.name_max_width:
            return name
        ellipsis = "…"
        low, high = 0, len(name)
        while low < high:
            mid = (low + high + 1) // 2
            candidate = name[:mid] + ellipsis
            if self.name_font.measure(candidate) <= self.name_max_width:
                low = mid
            else:
                high = mid - 1
        return name[:low] + ellipsis

    def _render_game(self, game):
        icon_img = load_icon(game.icon_path)
        self.icon_photo = ImageTk.PhotoImage(icon_img)
        self.canvas.itemconfigure(self.icon_item, image=self.icon_photo)
        self.canvas.itemconfigure(self.name_item, text=self._fit_name(game.name))

    def _render_pick(self):
        self._render_game(self.current_pick)

    def start_spin(self):
        if len(self.games) < 2:
            # Nothing to spin through - just land immediately
            self.current_pick = random.choice(self.games)
            self._render_pick()
            return

        self.spinning = True
        final_pick = random.choice(self.games)
        # Random games for every frame but the last, which is the real
        # result - the increasing delays between frames create the
        # ease-out "clunk to a stop" feel.
        sequence = [random.choice(self.games) for _ in SPIN_FRAME_DELAYS] + [final_pick]
        self._play_spin_frame(sequence, 0)

    def _play_spin_frame(self, sequence, index):
        self._render_game(sequence[index])
        if index < len(SPIN_FRAME_DELAYS):
            delay = SPIN_FRAME_DELAYS[index]
            self.root.after(delay, lambda: self._play_spin_frame(sequence, index + 1))
        else:
            self.current_pick = sequence[index]
            self.spinning = False

    def reroll(self):
        self.start_spin()

    def exclude_current(self):
        if self.spinning:
            return
        add_to_excluded(self.current_pick.appid)
        self.games = [g for g in self.games if g.appid != self.current_pick.appid]
        self.reroll()

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
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
        app = SlotMachineApp(eligible_games)
        app.run()
