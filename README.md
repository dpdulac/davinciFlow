# DaVinci Flow Pipeline

A Python 3 integration script bridging **ShotGrid (Flow)** and **DaVinci Resolve**.

This utility allows artists to instantly query ShotGrid for a specific sequence, fetch the latest media (or historical versions) across multiple pipeline tasks, and automatically assemble them into a perfectly synced DaVinci Resolve timeline.

![UI Screenshot Placeholder](https://dummyimage.com/600x300/1a1a1a/ffffff.png&text=DaVinci+Flow+UI)

## ✨ Key Features

* **Intelligent Version Grouping:** Automatically groups duplicate versions (e.g., `dnxhd` vs `mjpeg` for the same version number) and prioritizes high-quality formats.
* **Historical Takes:** Don't just load the newest clip. The script can load the Last 3, Last 5, or *All* historical versions of a shot, layering the newest on top and tucking older versions cleanly underneath as selectable DaVinci Takes.
* **User Presets:** Fully customizable task filters. Create presets in `userpref.json` to tailor the sequence build for specific departments (e.g., "Compositor Review" vs "Animator Review").
* **Smart Pathing:** Automatically resolves path differences between local workstations (e.g., swapping `W:\` and `V:\` drive letters on the fly).
* **Auto-Proxies & Parallel Acceleration:** If a file exists on ShotGrid but isn't available locally, the script utilizes a `ThreadPoolExecutor` to download web proxies simultaneously in parallel for massive speed boosts. If no proxy exists, it generates a red "NO CLIP" placeholder.
* **Audio Sync:** Optionally fetches published audio tracks from Flow and syncs them perfectly to the timeline start.
* **Scalable Verbose Logging:** A fully configurable 0 to 5 logging level system allowing for silent operations (0) or deep technical tracing (5).

## 📦 Dependencies

This script requires external Python libraries to communicate with ShotGrid, process timelines, and launch the companion UI apps. Ensure they are installed in the Python environment that DaVinci Resolve uses:

```bash
# Core Requirements
* ShotGrid API (`pip install shotgun_api3`)
* PyOpenColorIO (`pip install opencolorio`) - For OCIO color management and pipeline LUT processing.
* PySide6 (`pip install PySide6`)

# Optional / Future Requirements
pip install opentimelineio
```

## 🚀 Installation

Copy all files (`davinciFlow.py`, `userpref_manager.py`, `davinciFlow_config.json`, `userpref.json`) into your DaVinci Resolve utility scripts folder based on your operating system:

* **Windows:**
  `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow\`
* **Mac OS:**
  `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/davinciFlow/`
* **Linux:**
  `/opt/resolve/Fusion/Scripts/Utility/davinciFlow/`  
  *(Note: Depending on your Linux installation, it may also be located at `~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/`)*

Once copied:
1. Launch DaVinci Resolve Studio.
2. Open the top menu: **Workspace > Scripts > davinciFlow > davinciFlow**.

## ⚙️ Configuration

### 1. `davinciFlow_config.json`
Define your global pipeline rules here.
```json
{
  "flow_url": "https://your-studio.shotgunstudio.com/",
  "script_name": "resolve_api_script",
  "script_key": "YOUR_API_KEY",
  "proxy_download_path": "T:\\flowDavinci",
  "projects": ["ProjectA", "ProjectB"],
  "tasks": ["delivery", "compo_comp", "anim_main", "layout_base", "editing_edt"],
  "verbose_level": 3,
  "userpref_dir": "/homes/shared_prefs",
  "exr_lut": "Mikros/TMNT2_acescg_to_vd16.cube"
}
```

### 2. `userpref.json`
Define custom Task Presets for the dropdown UI.
```json
{
  "presets": {
    "Compositor Default": ["compo_comp", "light_precomp", "anim_main", "editing_edt"],
    "Animator Default": ["anim_main", "layout_base", "previz_base", "editing_edt"]
  }
}
```

## 🛠️ Usage

### 1. DaVinci Script
1. Open the script in DaVinci.
2. Under **FLOW**, select your Project and Sequence. Check `Use Flow Audio` if you want synced sound.
3. Under **TASKS**, either specify a High/Low range of tasks to search through, OR check `Use Task Presets` to select a predefined array from your config.
4. Under **TIMELINE**, choose how many historical Takes you'd like to load.
5. Hit **Build Sequence**!

### 2. User Preferences Manager
Instead of manually editing the `userpref.json` file, you can use the included companion desktop app.
1. Run `userpref_manager.py` using Python (or double-click the included `Launch_UserPref_Manager.bat` example file on Windows).
2. Enter a preset name and sequentially add tasks from the master configuration drop-down.
3. Save the preset to automatically update `userpref.json`.
4. Click "View / Refresh Prefs" to review all stored sequences in a table format.

---
*For AI Developers: See `davinciFlow_documentation.txt` for a strict architectural prompt on how to recreate this script's logic.*
