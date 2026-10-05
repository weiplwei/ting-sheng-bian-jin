# Default sound library

This directory contains the default item metadata, WAV samples, and icons shipped
with the project. You can use it as-is, replace individual WAV files under
`_raw/items/<item-id>/samples/`, or import another compatible library.

Shared candidate names, gold/non-gold classifications, and grid sizes live in
`data/catalog_hints.json`; these lightweight hints can be distributed with the
application and are merged into the local item metadata when loaded.

To import a compatible SoundRadar `.srz` library, run from the project directory:

```powershell
python import_library.py --src "C:\path\to\library.srz"
```

The importer replaces `items.json` and extracts audio and icons into `_raw/`.
Back up this directory first if you want to keep the bundled defaults.
