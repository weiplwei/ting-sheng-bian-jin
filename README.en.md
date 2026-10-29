# Ting Sheng Bian Jin (Sound-Based Valuable Item Identifier)

A Windows sound recognition helper for the merchant mode in *Arena Breakout: Infinite*. It listens to audio playing on your PC, matches sounds against the bundled local library, and displays a small overlay so you can decide whether an item is worth buying.

This project only provides sound alerts. It does not purchase items or control the game. It captures Windows audio loopback and does not read game memory, inject into the game, connect to game servers, or simulate keyboard or mouse input. This is an independent community project and is not affiliated with the game publisher.

## Quick start (Windows)

1. Download and extract the repository ZIP.
2. Install [Python 3.12](https://www.python.org/downloads/windows/) (recommended) or Python 3.13 and enable the Python Launcher.
3. Run `setup.bat` and wait for dependencies to install.
4. Run `start_live.bat` to use the included default sound library. Set the game to borderless windowed mode for the overlay.
5. Press `Ctrl+C` in the console to stop.

The repository currently provides batch launchers, not a packaged `.exe`.

## English interface

Chinese is the default display language. Add `--lang en` to supported commands to display English item names and overlay labels. Item names follow the English names used in *Arena Breakout: Infinite* where verified.

```powershell
.venv\Scripts\python.exe main.py items --lang en
.venv\Scripts\python.exe main.py live --overlay --lang en
.venv\Scripts\python.exe main.py match --wav "C:\path\to\sample.wav" --lang en
```

## Manual setup and commands

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py items
.venv\Scripts\python.exe main.py live --overlay
.venv\Scripts\python.exe main.py live --seconds 30
```

To replace the library, drop a compatible SoundRadar `.srz` file onto `import_library.bat`. Importing replaces the library index; back up `data/library/` first. You can also replace WAV samples under `data/library/_raw/items/<item-id>/samples/` while keeping the paths in `items.json` unchanged. Group candidate names and inventory sizes are maintained in `data/catalog_hints.json`; English labels are in `data/catalog_hints.en.json`.

If you only have Python 3.13 installed, use `py -3.13 -m venv .venv` for the first command in the manual setup block.

## Notes

- Loopback captures all audio played through the selected output device, including voice chat, which can affect recognition.
- Accuracy depends on the library, volume, and in-game conditions. Treat results as hints, not a guarantee.
- Exclusive fullscreen may cover the overlay; use borderless windowed mode.
- Only share sound and image assets you have permission to redistribute.

## License

The source code and bundled default library are distributed under the MIT License. See [LICENSE](LICENSE).
