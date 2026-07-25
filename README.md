# Steam Picker

A tiny Windows desktop widget that randomly selects a game from your installed Steam library.

Because everything needs gambling mechanics.

## Features

- Automatically discovers games across all installed Steam libraries
- Uses Steam’s locally cached game icons
- Animated slot-machine selection with a winner bounce
- Prevents repeat winners and accidental click-spamming
- Click the handle to reroll
- Click the Steam logo to launch the selected game
- Right-click menu for playing, rerolling, excluding, and changing skins
- Includes classic Valve-blue and pink sparkle cabinet skins
- Always-on-top, draggable desktop widget
- No Steam API key required

## Download

Download the latest `Steam Picker.exe` from the repository’s **Releases** page.

No Python installation is required when using the executable.

Windows may display a SmartScreen warning because the application is not digitally signed. Choose **More info → Run anyway** if you downloaded it from this repository.

## Controls

- **Click the handle:** Pick another game
- **Click the Steam logo:** Launch the displayed game
- **Right-click the cabinet:** Open the action and skin menu
- **Click and drag:** Move the cabinet
- **Esc:** Close Steam Picker

## Running from Source

### Requirements

- Windows
- Python 3.10 or newer
- Steam
- Pillow

Install the required package:

```bash
pip install -r requirements.txt
```

Start Steam Picker:

```bash
python main.py
```

Steam must be installed, but it does not need to be running when Steam Picker starts.

## Project Structure

```text
Steam-Picker/
├── main.py
├── steam_scanner.py
├── game_filter.py
├── art/
│   └── cabinet.png
└── SKINS/
    ├── Pink/
    │   └── cabinet.png
    └── Valve/
        └── cabinet.png
```

## Custom Skins

Create a folder inside `SKINS/` and place a file named `cabinet.png` inside it:

```text
SKINS/
└── My Skin/
    └── cabinet.png
```

Steam Picker discovers new skins automatically and adds them to the right-click menu.

Cabinet artwork must:

- Be exactly **240×320 pixels**
- Use a transparent background
- Preserve the screen, logo, name bar, and handle positions

## Excluded Games

Right-click the cabinet and select **Exclude** to remove the displayed game from future rolls.

Exclusions are saved locally in:

```text
%LOCALAPPDATA%\GamePicker\excluded.json
```

Deleting that file restores every excluded game.

## Notes

Steam Picker reads installed-game metadata and artwork from files already maintained by Steam. Store classification results and exclusions are cached locally to make future launches faster.

Originally built over a VC as a quick, slightly ridiculous solution for friends who couldn't decide what to play.
