# Steam Picker v1.0.0

![Steam Picker release banner](https://github.com/01170/Steam-Picker/blob/main/steam-picker-release-banner.png)

Your Steam backlog, now with gambling mechanics.

Steam Picker is a tiny always-on-top Windows slot machine that scans your
installed Steam libraries and chooses what you should play next.

![Steam Picker demo](https://github.com/01170/Steam-Picker/blob/main/steam-picker-demo.gif)

## Highlights

- Automatically discovers games across every installed Steam library
- Uses real square game icons from Steam's local artwork cache
- Filters out tools, DLC, soundtracks, and other non-game entries
- Animated slot-machine selection with an ease-out finish
- Cute winner bounce when the final game lands
- Prevents immediate repeats and rapid click-spamming
- Click the Steam logo to launch the selected game
- Right-click menu for Play, Reroll, Exclude, Change Skin, and Exit
- Draggable, transparent, always-on-top desktop widget
- Remembers excluded games locally

## Included Skins

- Black
- Green
- Pink
- Purple
- Red
- Valve

Additional skins can be added under `SKINS/<skin name>/cabinet.png`.

## Controls

| Action | Control |
| --- | --- |
| Pick another game | Click the cabinet handle |
| Launch the selected game | Click the Steam logo |
| Open actions and skins | Right-click the cabinet |
| Move the widget | Click and drag |
| Close Steam Picker | Press `Esc` |

## Download

Download **Steam Picker.exe** from the assets attached to this release and
double-click it to start.

Python is not required when using the executable.

> [!NOTE]
> Windows may show a SmartScreen warning because the executable is not
> digitally signed. If you downloaded it from this repository, select
> **More info → Run anyway**.

## Requirements

- Windows 10 or newer
- Steam installed
- At least one installed Steam game

Steam does not need to be running when Steam Picker starts. It will open
automatically when you launch the selected game.

## Local Data

Steam Picker stores its classification cache and exclusions in:

```text
%LOCALAPPDATA%\GamePicker
```

Delete `excluded.json` from that folder to restore all excluded games.

## Known Limitations

- Windows only
- Game artwork must already exist in Steam's local cache
- The first source-code run may take longer while app classifications are
  downloaded and cached

Built as a fun solution for friends who could not decide what to play.
