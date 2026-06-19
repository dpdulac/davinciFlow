# BookStack Tutorial Generation Plan

*This document outlines the planned structure for the DaVinci Flow BookStack tutorial. Once the media assets are captured and placed in a `docs/media` folder, an AI can use this plan to generate the final, beautifully formatted Markdown/HTML code for BookStack.*

## Proposed Page Structure

1. **Overview & Purpose:** A quick TL;DR for artists explaining what DaVinci Flow is and how it saves them time.
2. **Prerequisites & Setup:** Simple steps for artists to ensure they have the right files in the right folders on their specific OS (Windows/Mac/Linux).
3. **The User Preferences App (Step-by-Step):** A dedicated section walking artists through how to use the `userpref_manager.py` tool to build their own department presets safely.
4. **Using the DaVinci Script (Step-by-Step):** A breakdown of the three UI sections (Flow, Tasks, Timeline), explaining what each dropdown and checkbox actually does.
5. **FAQ / Troubleshooting:** Common things artists might run into (e.g., "Why is there a red NO CLIP image?", "Why aren't my audio files syncing?").

---

## Required Media Assets (The "Shot List")

Please capture the following media and save them to the repository (e.g. `docs/media/`). The tutorial will embed these to provide visual context for artists.

### 📸 Images (Screenshots)
1. **`menu_launch.png`**: A simple screenshot showing the DaVinci Resolve top menu (`Workspace > Scripts > davinciFlow`). This helps artists find it on their first try.
2. **`main_ui.png`**: A clean, static screenshot of the newly redesigned `davinciFlow.py` window, showing the 3 headers (FLOW, TASKS, TIMELINE).
3. **`userpref_app.png`**: A static screenshot of the `userpref_manager.py` companion app with a few tasks already populated in the list and the table visible at the bottom.
4. **`no_clip_placeholder.png`**: A quick screenshot of DaVinci's viewer showing the red "NO CLIP" placeholder, so artists know exactly what to look for when a ShotGrid proxy is missing.

### 🎥 Small Movies / GIFs
1. **`dynamic_ui_toggle.gif` (5-7 seconds):** A short clip of someone checking and unchecking the `Use Task Presets` box in the main UI, showing the "Highest/Lowest" drop-downs greying out and the "Task Preset" drop-down lighting up.
2. **`build_sequence.gif` (10-15 seconds):** The "money shot." A short clip of a user hitting the "Build Sequence" button, and the DaVinci timeline instantly populating with the stacked takes and synced audio.
