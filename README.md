# DaVinci Flow Pipeline Script

A powerful python bridge between ShotGrid (Flow) and DaVinci Resolve.

## Features
- **Sequence Assembly:** Live fetches latest media from Flow based on `Sequence` and `Tasks` filters.
- **Playlist Assembly:** Direct integration with ShotGrid Playlists, dynamically bypassing the Task hierarchy to load explicitly approved versions.
- **Dynamic B&W / Review Shots:** Define specific shots as "Review Shots". The script applies your studio LUT to Hero shots, and mathematically generated B&W LUTs to Non-Hero shots.
- **Automated Timelines:** Creates timelines dynamically. In Sequence mode, it uses `{Seq}_YYYY_MM_DD`. In Playlist mode, it generates mathematical `{Playlist}_vXXX` sequences.
- **Historical Takes:** Stacks previous version iterations into DaVinci "Takes" under the primary clips.
- **Proxy Management:** Auto-downloads missing web proxies from Shotgrid using parallel threading.
- **Preset Management:** A standalone Desktop App (`userpref_manager.py`) allows artists to create custom task hierarchy presets.

## Usage
1. Drag and drop `davinciFlow.py` into your DaVinci Resolve `Utility` script folder.
2. Launch via `Workspace > Scripts > Utility > davinciFlow`.
3. Toggle between **Sequence Mode** (for task-based discovery) and **Playlist Mode** (for exact version loading).
4. Use the "Show Shots" menus to explicitly target or exclude shots from the timeline.

## Configuration
Requires `davinciFlow_config.json` at root:
```json
{
    "flow_url": "https://mikrosanim.priv.shotgunstudio.com/",
    "script_name": "resolveTest",
    "script_key": "your_key",
    "proxy_download_path": "T:/flowDavinci",
    "projects": ["Tmnt2"],
    "tasks": ["delivery", "compo_comp", "light_precomp"],
    "verbose_level": 3,
    "exr_lut": "Mikros/TMNT2_acescg_to_vd16.cube"
}
```

## Setup & Dependencies
- Python 3.6+
- `shotgun_api3`
- `PyOpenColorIO`
- `PySide6` (For Preset Manager)
