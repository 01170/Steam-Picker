# Steam Picker

A tiny Windows desktop widget that randomly selects a game from your installed Steam library.

Because everything needs gambling mechanics.

## Requirements

- Windows
- Python 3.10 or newer
- Steam
- [Pillow](https://pypi.org/project/pillow/)

## Installation

Download or clone this repository, then install the required package:

```bash
pip install -r requirements.txt
```

Start Steam Picker with:

```bash
python main.py
```

Steam must be installed, but it does not need to be running.

## Controls

- Click the handle to spin the slot.
- Right-click the current game to exclude it.
- Drag the cabinet to move it.
- Press `Esc` to close it.

## Project Files

```text
Steam-Picker/
├── main.py
├── steam_scanner.py
├── game_filter.py
├── requirements.txt
├── art/
│   └── cabinet.png
└── SKINS/
    ├── Pink/
    │   └── cabinet.png
    └── Valve/
        └── cabinet.png
```

## Changing Skins

Additional cabinet designs are included under `SKINS/`.

To use one, copy its `cabinet.png` file into the `art/` folder and replace the existing `art/cabinet.png`.

The artwork must remain 240×320 pixels because the icon, title, and handle positions are aligned to that canvas.

## Notes

Steam Picker scans your installed Steam libraries locally. Game icons are loaded from Steam’s local artwork cache whenever possible.
