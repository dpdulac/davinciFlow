import os
import sys
import json
import datetime
import urllib.request
import wave
import logging
import time
import concurrent.futures

# Setup Logging
try:
    _dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    if sys.platform == "win32":
        if os.path.exists(r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"):
            _dir = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"
        else:
            _dir = r"W:\jmji\_sandbox\dulacd\Script\Blender"
    else:
        linux_path = os.path.expanduser("~/.local/share/DaVinciResolve/Fusion/Scripts/Utility/davinciFlow")
        custom_linux_path = "/datas/dulacd/DaVinciResolve/Fusion/Scripts/Utility/davinciFlow"
        if os.path.exists(linux_path):
            _dir = linux_path
        elif os.path.exists(custom_linux_path):
            _dir = custom_linux_path
        elif os.path.exists("/opt/resolve/Fusion/Scripts/Utility/davinciFlow"):
            _dir = "/opt/resolve/Fusion/Scripts/Utility/davinciFlow"
        else:
            _dir = "/datas/dulacd"
LOG_PATH = os.path.join(_dir, "davinciFlow.log")



# ==========================================
# FLOW AUTHENTICATION & CONFIG
# ==========================================
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # DaVinci Resolve's embedded interpreter doesn't set __file__
    SCRIPT_DIR = _dir

CONFIG_PATH = os.path.join(SCRIPT_DIR, "davinciFlow_config.json")

# Default fallback values if config fails
FLOW_URL = "https://mikrosanim.priv.shotgunstudio.com/"
SCRIPT_NAME = "resolveTest"
SCRIPT_KEY = "vblervsd(ubdZzxsxtvo5jimv"
PROXY_DOWNLOAD_PATH = r"T:\flowDavinci" if sys.platform == "win32" else "/datas/dulacd/tmp/flowDavinci"
PROJECTS = ["Tmnt2", "Bsl"]
MASTER_TASKS = [
    "delivery", "confo_render", "compo_comp", "compo_precomp",
    "light_precomp", "anim_main", "layout_base", "previz_base", "editing_edt"
]

# Load from JSON
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
            FLOW_URL = config.get('flow_url', FLOW_URL)
            SCRIPT_NAME = config.get('script_name', SCRIPT_NAME)
            SCRIPT_KEY = config.get('script_key', SCRIPT_KEY)
            PROXY_DOWNLOAD_PATH = config.get('proxy_download_path', PROXY_DOWNLOAD_PATH)
            if sys.platform != "win32" and PROXY_DOWNLOAD_PATH.startswith("T:\\"):
                PROXY_DOWNLOAD_PATH = "/datas/dulacd/tmp/flowDavinci"
            PROJECTS = config.get('projects', PROJECTS)
            MASTER_TASKS = config.get('tasks', MASTER_TASKS)
            EXR_LUT = config.get('exr_lut', '')
    except Exception as e:
        print(f"Failed to load json config: {e}")

# Dynamically load show configurations
SHOW_CONFIGS = {}
CONFIGS_DIR = os.path.join(SCRIPT_DIR, "configs")
if os.path.exists(CONFIGS_DIR):
    for f_name in os.listdir(CONFIGS_DIR):
        if f_name.endswith(".json"):
            try:
                with open(os.path.join(CONFIGS_DIR, f_name), 'r') as cf:
                    cfg = json.load(cf)
                    display_name = cfg.get("display_name")
                    base_key = os.path.splitext(f_name)[0].lower()
                    SHOW_CONFIGS[base_key] = cfg
                    if display_name:
                        SHOW_CONFIGS[display_name.lower()] = cfg
                        if not cfg.get("is_pipeline_preset", False) and display_name not in PROJECTS and display_name.lower() != "default":
                            PROJECTS.append(display_name)
            except Exception as e:
                print(f"Failed to load show config {f_name}: {e}")

VERBOSE_LEVEL = config.get('verbose_level', 3) if 'config' in locals() else 3
level_map = {0: logging.CRITICAL, 1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG, 5: logging.DEBUG}
logging.basicConfig(filename=LOG_PATH, level=level_map.get(VERBOSE_LEVEL, logging.INFO), 
                    format='%(asctime)s - %(levelname)s - %(message)s')

def log(msg, level=3):
    if VERBOSE_LEVEL >= level:
        print(msg)
    if level == 0: logging.critical(msg)
    elif level == 1: logging.error(msg)
    elif level == 2: logging.warning(msg)
    elif level == 3: logging.info(msg)
    elif level >= 4: logging.debug(msg)

USERPREF_DIR = config.get('userpref_dir') if 'config' in locals() and config.get('userpref_dir') else os.path.join(os.path.expanduser("~"), ".flowDavinciData")
USERPREF_PATH = os.path.join(USERPREF_DIR, "userpref.json")
user_presets = {}
if os.path.exists(USERPREF_PATH):
    try:
        with open(USERPREF_PATH, 'r') as f:
            upref = json.load(f)
            user_presets = upref.get('presets', {})
    except Exception as e:
        print(f"Failed to load userpref.json: {e}")

# ==========================================
# MODULE IMPORTS
# ==========================================
try:
    import shotgun_api3
except ImportError:
    if sys.platform != "win32":
        sys.path.append("/s/apps/packages/mikros/shotgunPythonApi/3.3.1")
        try:
            import shotgun_api3
        except ImportError:
            print("Error: The 'shotgun_api3' module is not installed (Linux fallback failed).")
            sys.exit(1)
    else:
        print("Error: The 'shotgun_api3' module is not installed.")
        sys.exit(1)

try:
    resolve = bmd.scriptapp('Resolve')
except NameError:
    import DaVinciResolveScript as dvr_script
    resolve = dvr_script.scriptapp('Resolve')

if not resolve:
    print("No DaVinci Resolve instance found.")
    sys.exit(1)

fusion = resolve.Fusion()
project_manager = resolve.GetProjectManager()
dvr_project = project_manager.GetCurrentProject()
media_pool = dvr_project.GetMediaPool()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def retry_sg(func, retries=3, delay=2):
    """Wrapper to automatically retry ShotGrid API calls on connection timeouts."""
    for i in range(retries):
        try:
            return func()
        except Exception as e:
            if i == retries - 1:
                log(f"API Error after {retries} retries: {e}", level=1)
                raise e
            log(f"API Timeout, retrying in {delay} seconds...", level=2)
            time.sleep(delay)

def get_sequences(project_name):
    log(f"Fetching sequences for project '{project_name}'...", level=2)
    try:
        sg = shotgun_api3.Shotgun(FLOW_URL, script_name=SCRIPT_NAME, api_key=SCRIPT_KEY)
        proj = retry_sg(lambda: sg.find_one("Project", [["name", "is", project_name]], ["id"]))
        if not proj: return []
        filters = [
            ['project', 'is', proj],
            ['code', 'is_not', 'omit'],
            ['sg_status_list', 'is_not', 'omt'],
        ]
        # Performance: Use summarize instead of fetching all shots
        seqs = retry_sg(lambda: sg.summarize("Shot", filters, summary_fields=[{'field': 'id', 'type': 'count'}], grouping=[{'field': 'sg_sequence', 'type': 'exact', 'direction': 'asc'}]))
        seq_codes = []
        for group in seqs.get('groups', []):
            name = group.get('group_value', {}).get('name')
            if name: seq_codes.append(name)
        seq_codes.sort()
        return seq_codes
    except Exception as e:
        log(f"Failed to fetch sequences: {e}", level=1)
        return []

def get_missing_media_path():
    if not os.path.exists(PROXY_DOWNLOAD_PATH):
        os.makedirs(PROXY_DOWNLOAD_PATH, exist_ok=True)
        
    path = os.path.join(PROXY_DOWNLOAD_PATH, "no_clip.jpg")
    if not os.path.exists(path):
        print("Downloading placeholder 'NO CLIP' image...")
        url = "https://dummyimage.com/1920x1080/ff0000/ffffff.jpg?text=NO+CLIP"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with open(path, 'wb') as f:
                f.write(urllib.request.urlopen(req).read())
        except Exception as e:
            print("Could not download placeholder image:", e)
    return path

def get_or_create_sub_bin(parent_bin, folder_name):
    media_pool.SetCurrentFolder(parent_bin)
    subfolders = parent_bin.GetSubFolderList()
    for folder in subfolders:
        if folder.GetName() == folder_name:
            return folder
    return media_pool.AddSubFolder(parent_bin, folder_name)

def get_or_create_bin(folder_name):
    root = media_pool.GetRootFolder()
    return get_or_create_sub_bin(root, folder_name)

def find_clip_in_folder(folder, file_path):
    clips = folder.GetClipList()
    norm_path = file_path.replace("/", "\\").lower()
    for clip in clips:
        clip_path = clip.GetClipProperty("File Path").replace("/", "\\").lower()
        if clip_path == norm_path:
            return clip
        if os.path.isdir(norm_path) and clip_path.startswith(norm_path):
            return clip
    return None

TASK_COLOR_MAP = {
    "compo": "Blue",
    "comp": "Blue",
    "composite": "Blue",
    "lighting": "Yellow",
    "lgt": "Yellow",
    "light": "Yellow",
    "animation": "Green",
    "anim": "Green",
    "fx": "Purple",
    "effects": "Purple",
    "layout": "Orange",
    "layout_anim": "Orange",
    "rotoscoping": "Pink",
    "roto": "Pink",
    "matte_paint": "Teal",
    "mp": "Teal",
    "model": "Tan",
    "modeling": "Tan",
    "rig": "Beige",
    "rigging": "Beige"
}

def get_task_color(task_name):
    """Maps a studio pipeline task name to a standard DaVinci Resolve clip color."""
    if not task_name or task_name == "NONE" or task_name == "playlist":
        return "Teal"
    clean_task = str(task_name).strip().lower()
    for key, color in TASK_COLOR_MAP.items():
        if key in clean_task:
            return color
    return "Teal"


def unlock_still_image_duration(item):
    """Enables custom duration trimming for still image placeholders in MediaPool."""
    if item:
        try:
            item.SetMarkInOut(0, 86400)
        except Exception:
            pass

def get_media_item_duration(item, default=48):
    """Retrieves exact frame duration of a MediaPool item if editorial cuts are not in Flow."""
    if not item:
        return default
    try:
        frames = item.GetClipProperty("Frames")
        if frames and str(frames).isdigit() and int(frames) > 0:
            return int(frames)
    except Exception:
        pass
    try:
        start = item.GetClipProperty("Start")
        end = item.GetClipProperty("End")
        if start and end and str(start).isdigit() and str(end).isdigit():
            dur = int(end) - int(start)
            if dur > 0:
                return dur
    except Exception:
        pass
    return default

def ensure_luts_installed():
    import shutil
    if sys.platform == "win32":
        davinci_lut_dir = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\davinciFlow"
        repo_lut_dir = r"T:\davinciFlow_repo\luts"
    else:
        davinci_lut_dir = os.path.expanduser("~/.local/share/DaVinciResolve/LUT/davinciFlow")
        if not os.path.exists(os.path.expanduser("~/.local/share/DaVinciResolve/LUT")):
            davinci_lut_dir = "/datas/dulacd/DaVinciResolve/LUT/davinciFlow"
        repo_lut_dir = "/datas/dulacd/gitHub/davinciFlow/luts"
    if not os.path.exists(repo_lut_dir): return
    os.makedirs(davinci_lut_dir, exist_ok=True)
    for f in os.listdir(repo_lut_dir):
        if f.endswith(".cube"):
            src = os.path.join(repo_lut_dir, f)
            dst = os.path.join(davinci_lut_dir, f)
            try: shutil.copy2(src, dst)
            except: pass

def _path_exists_smart(p):
    if "%" in p or "#" in p:
        return os.path.exists(os.path.dirname(p))
    return os.path.exists(p)

def resolve_path(raw_path):
    if not raw_path: return None
    
    if sys.platform != "win32":
        clean_path = raw_path.replace("\\", "/")
        if clean_path.upper().startswith("V:/") or clean_path.upper().startswith("W:/"):
            tail = clean_path[3:]
            return f"/s/prodanim/{tail}"
        return clean_path

    clean_path = raw_path.replace("/", "\\")
    
    # Handle Linux paths
    if clean_path.startswith("\\s\\prodanim\\"):
        tail = clean_path.replace("\\s\\prodanim\\", "")
        if _path_exists_smart(f"W:\\{tail}"): return f"W:\\{tail}"
        if _path_exists_smart(f"V:\\{tail}"): return f"V:\\{tail}"
        return f"W:\\{tail}" # default fallback
        
    # Handle Windows paths
    if len(clean_path) > 2 and clean_path[1:3] == ":\\":
        if _path_exists_smart(clean_path): return clean_path
        
        # Try swapping V and W if not found
        drive = clean_path[0].upper()
        tail = clean_path[3:]
        if drive == 'V':
            if _path_exists_smart(f"W:\\{tail}"): return f"W:\\{tail}"
        elif drive == 'W':
            if _path_exists_smart(f"V:\\{tail}"): return f"V:\\{tail}"
            
    return clean_path

# ==========================================
# UI BUILDER
# ==========================================
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

# Pre-fetch sequences for the first project
initial_sequences = get_sequences(PROJECTS[0]) if PROJECTS else ["0575"]
if not initial_sequences: initial_sequences = ["0575"]

layout = ui.VGroup([
    # FLOW
    ui.Button({"ID": "FlowHeaderBtn", "Text": "▼ FLOW", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "FlowGrp", "Weight": 0}, [
        ui.HGroup([
            ui.Label({"Text": "Mode:", "ToolTip": "Switch between Sequence Mode and Playlist Mode"}),
            ui.ComboBox({"ID": "ModeCombo", "Weight": 2})
        ]),
        ui.HGroup([
            ui.Label({"Text": "Project:", "ToolTip": "Select the Flow project to load"}),
            ui.ComboBox({"ID": "ProjectCombo", "Weight": 2, "ToolTip": "Select the Flow project to load"})
        ]),
        ui.HGroup({"ID": "SeqGrp"}, [
            ui.Label({"Text": "Sequence:", "Weight": 0}),
            ui.ComboBox({"ID": "SeqCombo", "Weight": 2, "ToolTip": "Select the sequence to build"})
        ]),
        ui.HGroup([
            ui.Label({"Text": "Use Cut Order:", "ToolTip": "Sort clips by Flow cut order instead of alphabetical", "Weight": 0}),
            ui.CheckBox({"ID": "CutOrderCheck", "Checked": True, "ToolTip": "Sort clips by Flow cut order instead of alphabetical", "Weight": 0}),
            ui.Label({"Weight": 1})
        ]),
        ui.HGroup([
            ui.Label({"Text": "Add Task Metadata:", "ToolTip": "Attach interactive colored task flags and metadata tooltips directly onto timeline clips", "Weight": 0}),
            ui.CheckBox({'ID': 'AddTaskMarkersCheck', 'Checked': False, "ToolTip": "Attach interactive colored task flags and metadata tooltips directly onto timeline clips", "Weight": 0}),
            ui.Label({"Weight": 1})
        ]),
        ui.HGroup({"ID": "PlaylistGrp"}, [
            ui.Label({"Text": "Playlist:", "Weight": 0}),
            ui.LineEdit({"ID": "PlaylistSearchLine", "PlaceholderText": "e.g. MAY24", "Weight": 1}),
            ui.Button({"ID": "FindPlaylistBtn", "Text": "Find", "Weight": 0}),
            ui.ComboBox({"ID": "PlaylistCombo", "Weight": 2})
        ])
    ]),
    
    # A/B WIPE
    ui.Button({"ID": "AbWipeHeaderBtn", "Text": "▼ A/B WIPE", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "AbWipeGrp", "Weight": 0}, [
        ui.HGroup([
            ui.CheckBox({'ID': 'AbWipeCheck', 'Text': 'Version Wipe (Same Task):', 'Checked': False, "ToolTip": "Stack previous version on Track 1 and current version on Track 2 for A/B wiping", "Weight": 0}),
            ui.HGap(5),
            ui.ComboBox({'ID': 'AbStatusCombo', 'Enabled': False, 'Weight': 1, "ToolTip": "Select required status of previous version to compare to (default: rtk)"})
        ]),
        ui.HGroup([
            ui.CheckBox({'ID': 'TaskWipeCheck', 'Text': 'Task Wipe (Cross-Task):', 'Checked': False, "ToolTip": "Compare latest version of two distinct tasks across Track 1 and Track 2", "Weight": 0}),
            ui.HGap(5),
            ui.Label({'Text': 'Top (V2):', "ToolTip": "Top candidate layer task", "Weight": 0}),
            ui.ComboBox({'ID': 'TaskWipeV2Combo', 'Enabled': False, 'Weight': 1, "ToolTip": "Top candidate layer task"}),
            ui.Label({'Text': 'Bottom (V1):', "ToolTip": "Bottom reference layer task", "Weight": 0}),
            ui.ComboBox({'ID': 'TaskWipeV1Combo', 'Enabled': False, 'Weight': 1, "ToolTip": "Bottom reference layer task"})
        ])
    ]),

    # SHOT
    ui.Button({"ID": "ShotHeaderBtn", "Text": "▼ SHOT", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "ShotGrp", "Weight": 0}, [
        ui.HGroup([
            ui.CheckBox({"ID": "AllShotsCheck", "Text": "All Shots", "Checked": True, "Weight": 0, "ToolTip": "Uncheck to build only specific shots"}),
            ui.LineEdit({"ID": "ShotFilterLine", "Text": "", "Enabled": False, "PlaceholderText": "e.g. 10, 30, 60-120", "Weight": 2, "ToolTip": "Comma-separated list of shots or ranges"}),
            ui.CheckBox({"ID": "ExcludeCheck", "Text": "Exclude", "Checked": False, "Enabled": False, "Weight": 0, "ToolTip": "If checked, the listed shots will be REMOVED from the timeline"}),
            ui.Button({"ID": "ShowShotsBtn", "Text": "Show Shots", "Enabled": False, "Weight": 0, "ToolTip": "Display all available shots in this sequence"})
        ]),
        ui.HGroup([
            ui.CheckBox({"ID": "UseHeroCheck", "Text": "Review Shots", "Checked": False, "Weight": 0, "ToolTip": "Turn non-review shots black and white"}),
            ui.LineEdit({"ID": "HeroFilterLine", "Text": "", "Enabled": False, "PlaceholderText": "e.g. 10, 20pip", "Weight": 2, "ToolTip": "Shots listed here will remain in color. All others will be black and white."}),
            ui.CheckBox({"ID": "ReverseHeroCheck", "Text": "Reverse", "Checked": False, "Enabled": False, "Weight": 0, "ToolTip": "If checked, listed shots become B&W and others stay colored"}),
            ui.Button({"ID": "ShowReviewShotsBtn", "Text": "Show Shots", "Enabled": False, "Weight": 0, "ToolTip": "Display all available shots to add to Review"})
        ]),
    ]),
    
    # FILE
    ui.Button({"ID": "FileHeaderBtn", "Text": "▼ FILE", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "FileGrp", "Weight": 0}, [
        ui.HGroup([
            ui.Label({"Text": "Image Sequences:", "ToolTip": "Download and load heavy image sequences instead of proxy movies", "Weight": 0}),
            ui.CheckBox({"ID": "ImageSeqCheck", "Checked": False, "ToolTip": "Download and load heavy image sequences instead of proxy movies", "Weight": 0}),
            ui.VGap(2),
            ui.CheckBox({"ID": "ApplyLutCheck", "Text": "Apply LUT", "Checked": True, "Enabled": False, "ToolTip": "Apply the color management LUT defined in the config to the EXR sequences", "Weight": 0}),
            ui.Label({"Weight": 1})
        ]),
        ui.HGroup([
            ui.Label({'Text': 'Audio File:', "ToolTip": "Fetch and sync published audio (.wav) from Flow to the timeline", "Weight": 0}),
            ui.CheckBox({'ID': 'UseAudio', 'Checked': False, "ToolTip": "Fetch and sync published audio (.wav) from Flow to the timeline", "Weight": 0}),
            ui.VGap(2),
            ui.Label({'Text': 'Missing Shots:', "ToolTip": "If checked, creates a red placeholder clip. If unchecked, skips missing shots completely.", "Weight": 0}),
            ui.CheckBox({'ID': 'MissingShotCheck', 'Checked': True, "ToolTip": "If checked, creates a red placeholder clip. If unchecked, skips missing shots completely.", "Weight": 0}),
            ui.Label({"Weight": 1})
        ]),
    ]),
    
    # TASKS
    ui.Button({"ID": "TaskHeaderBtn", "Text": "▼ TASKS", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "TaskGrp", "Weight": 0}, [
        ui.HGroup([
            ui.Label({"Text": "Use Task Presets:", "ToolTip": "Use custom task groups instead of a High/Low range", "Weight": 0}),
            ui.CheckBox({"ID": "UsePresetCheck", "Checked": False, "ToolTip": "Use custom task groups instead of a High/Low range", "Weight": 0}),
            ui.Label({"Weight": 1})
        ]),
        ui.HGroup([
            ui.Label({"Text": "Highest:", "ToolTip": "Top priority pipeline task"}),
            ui.ComboBox({"ID": "HighestTaskCombo", "Weight": 1, "ToolTip": "Top priority pipeline task"}),
            ui.Label({"Text": "Lowest:", "ToolTip": "Fallback pipeline task if higher tasks are missing media"}),
            ui.ComboBox({"ID": "LowestTaskCombo", "Weight": 1, "ToolTip": "Fallback pipeline task if higher tasks are missing media"})
        ]),
        ui.HGroup([
            ui.Label({"Text": "Task Preset:", "ToolTip": "Select a custom preset built in the UserPref Manager"}),
            ui.ComboBox({"ID": "TaskPresetCombo", "Weight": 2, "ToolTip": "Select a custom preset built in the UserPref Manager"})
        ]),
    ]),
    
    # TIMELINE
    ui.Button({"ID": "TimelineHeaderBtn", "Text": "▼ TIMELINE", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "TimelineGrp", "Weight": 0}, [
        ui.HGroup({"ID": "TakeGrp", "Weight": 0}, [
            ui.Label({'Text': 'Load Takes:', "ToolTip": "Choose how many historical versions of a shot to stack into a DaVinci Take", "Weight": 0}),
            ui.ComboBox({'ID': 'TakeCountCombo', 'Weight': 2, "ToolTip": "Choose how many historical versions of a shot to stack into a DaVinci Take"})
        ]),
        ui.HGroup({"Weight": 0}, [
            ui.Label({'Text': 'Timeline Options:', "ToolTip": "Manage timeline creation", "Weight": 0}),
            ui.CheckBox({'ID': 'UseLatestTimeline', 'Text': 'Update latest timeline (clears existing clips)', 'Checked': True, "ToolTip": "Overwrite the latest matching timeline instead of cluttering your bins with new timelines", "Weight": 0}),
            ui.Label({"Weight": 1})
        ]),
    ]),
    
    # ADVANCED
    ui.Button({"ID": "AdvancedHeaderBtn", "Text": "▼ ADVANCED", "Alignment": {"AlignLeft": True}, "Weight": 0}),
    ui.VGroup({"ID": "AdvancedGrp", "Weight": 0}, [
        ui.HGroup({"Weight": 0}, [
            ui.CheckBox({"ID": "AgxCheck", "Text": "AgX Pipeline", "Checked": False, "ToolTip": "Apply AgX DRX color grades instead of standard LUTs", "Weight": 0}),
            ui.HGap(5),
            ui.Button({'ID': 'CleanCacheBtn', 'Text': 'Clean Cache', 'ToolTip': 'Delete all downloaded MP4 proxies in the cache directory', 'Weight': 0}),
            ui.Label({"Weight": 1})
        ])
    ]),
    
    ui.VGap(5),
    ui.Label({"Weight": 1, "Text": ""}), # Flex spacer to keep footer buttons locked safely at the bottom
    ui.HGroup({'Weight': 0, 'Spacing': 10}, [
        ui.Button({'ID': 'CancelBtn', 'Text': 'Cancel', 'ToolTip': 'Close the tool'}),
        ui.Button({'ID': 'ToggleMarkersBtn', 'Text': 'Toggle Markers', 'ToolTip': 'Instantly clear or re-apply full-duration departmental markers on the active timeline'}),
        ui.Button({'ID': 'BuildBtn', 'Text': 'Build Sequence', 'ToolTip': 'Fetch media from Flow and construct the timeline'})
    ])
]),

win = dispatcher.AddWindow({
    "ID": "FlowDialog",
    "Geometry": [400, 200, 560, 720],
    "WindowTitle": "Flow to DaVinci Pipeline"
}, layout)

items = win.GetItems()

# Populate Comboboxes
for p in PROJECTS:
    items["ProjectCombo"].AddItem(p)

for s in initial_sequences:
    items["SeqCombo"].AddItem(s)

for t in MASTER_TASKS:
    items["HighestTaskCombo"].AddItem(t)
    items["LowestTaskCombo"].AddItem(t)
    items["TaskWipeV2Combo"].AddItem(t)
    items["TaskWipeV1Combo"].AddItem(t)

if user_presets:
    for preset_name in user_presets.keys():
        items["TaskPresetCombo"].AddItem(preset_name)

items["TakeCountCombo"].AddItem("None (Latest Only)")
items["TakeCountCombo"].AddItem("Last 2 Versions")
items["TakeCountCombo"].AddItem("Last 3 Versions")
items["TakeCountCombo"].AddItem("Last 4 Versions")
items["TakeCountCombo"].AddItem("Last 5 Versions")
items["TakeCountCombo"].AddItem("All Versions")
items["ModeCombo"].AddItem("Sequence Mode")
items["ModeCombo"].AddItem("Playlist Mode")
items["PlaylistGrp"].Hide()

# Populate A/B Wipe Status ComboBox (defaulting to 'rtk')
ab_status_list = [
    "rtk (Retake)",
    "rev (Pending Review)",
    "rtkd (Retake Done)",
    "chk (To Check)",
    "cmpt (Complete)",
    "dirrev (Pending Director)",
    "artrev (Pending Art Director)",
    "hocvfx (Pending HOCA/VFX)",
    "ip (In Progress)",
    "todo (Todo)",
    "rdy (Ready to Start)",
    "wtg (Waiting to Start)",
    "cbb (CBB)",
    "atfn (Autofinal)",
    "dlypnd (Delivery Pending)",
    "dlycpt (Delivery_complete)",
    "frm (On Farm)",
    "hld (On Hold)",
    "na (N/A)",
    "omt (Omit)",
    "clrtk (Client Retake)",
    "intrtk (Internal Retake)"
]
for st in ab_status_list:
    items["AbStatusCombo"].AddItem(st)
items["AbStatusCombo"].CurrentIndex = 0

# Set defaults for task ranges
if MASTER_TASKS:
    items["HighestTaskCombo"].CurrentIndex = 0
    items["LowestTaskCombo"].CurrentIndex = len(MASTER_TASKS) - 1
    items["TaskWipeV2Combo"].CurrentIndex = 0
    items["TaskWipeV1Combo"].CurrentIndex = 1 if len(MASTER_TASKS) > 1 else 0

# ==========================================
# FETCH DATA
# ==========================================
PROJECT_CACHE = {}

def fetch_flow_data(project_name, sequence_name, valid_tasks, use_image_seq, use_audio, max_versions, target_shots=None, exclude_mode=False, is_playlist_mode=False, playlist_name=None, ab_wipe_enabled=False, ab_status="rtk", ver_wipe_enabled=False, task_wipe_enabled=False, task_wipe_v2=None, task_wipe_v1=None):
    log(f"Connecting to Flow as '{SCRIPT_NAME}'...")
    try:
        sg = shotgun_api3.Shotgun(FLOW_URL, script_name=SCRIPT_NAME, api_key=SCRIPT_KEY)
    except Exception as e:
        log(f"Connection Failed: {e}")
        return None

    project = PROJECT_CACHE.get(project_name)
    if not project:
        project = retry_sg(lambda: sg.find_one("Project", [["name", "is", project_name]], ["id", "name"]))
        if project:
            PROJECT_CACHE[project_name] = project
            
    if not project:
        log(f"Project '{project_name}' not found.")
        return None

    if is_playlist_mode:
        log(f"\nQuerying Playlist {playlist_name}...")
        pl = retry_sg(lambda: sg.find_one("Playlist", [["project", "is", project], ["code", "is", playlist_name]], ["versions"]))
        if not pl or not pl.get("versions"):
            log(f"Playlist {playlist_name} not found or has no versions.")
            return None
            
        v_ids = [v["id"] for v in pl["versions"]]
        versions = retry_sg(lambda: sg.find("Version", [["id", "in", v_ids]], ["code", "sg_path_to_movie", "sg_path_to_frames", "sg_uploaded_movie_mp4", "created_at", "entity", "sg_task", "sg_status_list"]))
        
        # We need shot info (cut in/out) for these versions
        shot_ids = list(set([v["entity"]["id"] for v in versions if v.get("entity") and v["entity"]["type"] == "Shot"]))
        if not shot_ids:
            log("No shots linked to the versions in this playlist.")
            return None
            
        shots = retry_sg(lambda: sg.find("Shot", [["id", "in", shot_ids], ["sg_status_list", "is_not", "omt"]], ["id", "code", "sg_cut_in", "sg_cut_out", "sg_head_in", "sg_cut_order"]))
        
        # Apply target_shots filter
        if target_shots:
            filtered_shots = []
            for s in shots:
                match = any(ts in s["code"] for ts in target_shots)
                if (match and not exclude_mode) or (not match and exclude_mode):
                    filtered_shots.append(s)
            shots = filtered_shots
            if not shots:
                log("No shots matched the filter criteria.")
                return None
                
        shot_dict = {s["id"]: s for s in shots}
        
        prev_versions_by_shot = {}
        if ab_wipe_enabled and shots:
            log("Querying previous published versions for Playlist A/B wiping...")
            all_shot_versions = retry_sg(lambda: sg.find(
                "Version",
                [["project", "is", project], ["entity", "in", shots]],
                ["id", "code", "sg_path_to_movie", "sg_path_to_frames", "sg_uploaded_movie_mp4", "created_at", "entity", "sg_task", "sg_status_list"]
            ))
            by_shot = {}
            for sv in all_shot_versions:
                s_id = sv.get("entity", {}).get("id")
                if s_id:
                    by_shot.setdefault(s_id, []).append(sv)
            for s_id, vlist in by_shot.items():
                vlist.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
                prev_versions_by_shot[s_id] = vlist

        final_data = {}
        
        for v in versions:
            ent = v.get("entity")
            if not ent or ent["id"] not in shot_dict: continue
            
            shot_data = shot_dict[ent["id"]]
            shot_code = shot_data["code"]
            
            p_movie = resolve_path(v.get('sg_path_to_movie'))
            p_frames = resolve_path(v.get('sg_path_to_frames'))
            mp4_url = v.get('sg_uploaded_movie_mp4')
            
            target_path = p_frames if (use_image_seq and p_frames) else p_movie
            if not target_path and mp4_url:
                target_path = mp4_url
                is_web_proxy = True
            elif not target_path:
                target_path = get_missing_media_path()
                is_web_proxy = False
            else:
                is_web_proxy = False
                
            previous_version = None
            if ab_wipe_enabled:
                vlist = prev_versions_by_shot.get(shot_data["id"], [])
                chosen_prev = None
                if task_wipe_enabled and task_wipe_v1:
                    task_b_cands = [sv for sv in vlist if (sv.get("sg_task") and sv.get("sg_task", {}).get("name") == task_wipe_v1)]
                    if task_b_cands:
                        chosen_prev = task_b_cands[0]
                        log(f"  [{shot_code}] V1 Task Wipe: Found latest '{task_wipe_v1}' version '{chosen_prev.get('code')}'")
                    else:
                        log(f"  [{shot_code}] V1 Task Wipe: No media found for reference task '{task_wipe_v1}'")
                        previous_version = {'path': 'MISSING', 'is_web_proxy': False, 'code': '', 'task': task_wipe_v1, 'placeholder_text': f"NO REF TASK [{task_wipe_v1.upper()}]\n{shot_code}"}
                else:
                    v_created = str(v.get("created_at") or "")
                    v_task = v.get("sg_task", {}).get("name") if v.get("sg_task") else None
                    prev_candidates = [sv for sv in vlist if str(sv.get("created_at") or "") < v_created and sv["id"] != v["id"]]
                    same_task_candidates = [sv for sv in prev_candidates if (sv.get("sg_task") and sv.get("sg_task", {}).get("name") == v_task)]
                    candidates_pool = same_task_candidates if same_task_candidates else prev_candidates
                    if candidates_pool:
                        target_status = str(ab_status or "rtk").lower()
                        retake_cands = [sv for sv in candidates_pool if str(sv.get("sg_status_list") or "").lower() == target_status]
                        if retake_cands:
                            chosen_prev = retake_cands[0]
                            log(f"  [{shot_code}] V1 A/B Wipe: Prioritized targeted version '{chosen_prev.get('code')}' (status: {chosen_prev.get('sg_status_list')})")
                        else:
                            chosen_prev = candidates_pool[0]
                            log(f"  [{shot_code}] V1 A/B Wipe: No status '{target_status}' found. Fallback to immediate predecessor '{chosen_prev.get('code')}'")
                if chosen_prev:
                    p_mov_prev = resolve_path(chosen_prev.get('sg_path_to_movie'))
                    p_frm_prev = resolve_path(chosen_prev.get('sg_path_to_frames'))
                    p_mp4_prev = chosen_prev.get('sg_uploaded_movie_mp4')
                    p_target_prev = p_frm_prev if (use_image_seq and p_frm_prev) else p_mov_prev
                    prev_is_web = False
                    if not p_target_prev and p_mp4_prev:
                        p_url = p_mp4_prev.get('url') if isinstance(p_mp4_prev, dict) else p_mp4_prev
                        if p_url:
                            p_target_prev = p_url
                            prev_is_web = True
                    if p_target_prev:
                        prev_task_name = chosen_prev.get("sg_task", {}).get("name") if chosen_prev.get("sg_task") else (v.get("sg_task", {}).get("name") if v.get("sg_task") else "NONE")
                        previous_version = {'path': p_target_prev, 'is_web_proxy': prev_is_web, 'code': chosen_prev.get('code', ''), 'task': prev_task_name}

            v_task_val = v.get("sg_task", {}).get("name") if v.get("sg_task") else "playlist"
            final_data[shot_code] = {
                'shot_id': shot_data['id'],
                'shot_code': shot_code,
                'task': v_task_val,
                'version_code': v.get('code', ''),
                'path': target_path,
                'cut_in': shot_data.get('sg_cut_in'),
                'cut_out': shot_data.get('sg_cut_out'),
                'head_in': shot_data.get('sg_head_in'),
                'is_web_proxy': is_web_proxy,
                'takes': [],  # No historical takes in playlist mode
                'cut_order': shot_data.get('sg_cut_order'),
                'previous_version': previous_version
            }
            
        return final_data

    # Fetch all shots in sequence to get timing and ID
    log(f"\nQuerying Shots for Sequence {sequence_name}...")
    shot_filters = [
        ['project', 'is', project],
        ['sg_sequence', 'name_is', sequence_name],
        ['sg_status_list', 'is_not', 'omt']
    ]
    shot_fields = ['id', 'code', 'sg_cut_in', 'sg_cut_out', 'sg_head_in', 'sg_cut_order']
    shots = retry_sg(lambda: sg.find("Shot", shot_filters, shot_fields))
    
    if not shots:
        log(f"No shots found for sequence {sequence_name}.")
        return None
        
    if target_shots:
        filtered_shots = []
        for s in shots:
            match = any(ts in s["code"] for ts in target_shots)
            if (match and not exclude_mode) or (not match and exclude_mode):
                filtered_shots.append(s)
        shots = filtered_shots
        if not shots:
            log("No shots matched the shot filter criteria.")
            return None
            
    log(f"Found {len(shots)} shots. Resolving latest published files...")
    shot_dict = {s['id']: s for s in shots}
    
    # Query Audio files dynamically only if requested
    audio_dict = {}
    if use_audio:
        log("Querying Sequence Audio...")
        audio_filters = [
            ['project', 'is', project],
            ['published_file_type.PublishedFileType.code', 'in', ['EditingSound', 'Sound']]
        ]
        audio_pubs = retry_sg(lambda: sg.find('PublishedFile', audio_filters, ['code', 'entity', 'path']))
        for p in audio_pubs:
            ent = p.get('entity')
            ent_name = ent.get('name') if ent else ''
            path = p.get('path', {}).get('local_path_windows')
            
            if path and sequence_name in ent_name: 
                # Fix Path mapping for the local machine (Paris W: / Montreal V:)
                audio_dict[ent_name] = resolve_path(path)
    
    # valid_tasks is already passed as argument
    
    # Query all versions for these shots in the valid tasks (including Task Wipe targets if active)
    query_tasks = list(set((valid_tasks or []) + ([task_wipe_v2, task_wipe_v1] if task_wipe_enabled else [])))
    v_filters = [
        ['project', 'is', project],
        ['entity', 'in', shots],
        ['sg_task.Task.content', 'in', query_tasks]
    ]
    v_fields = ['entity', 'code', 'sg_path_to_movie', 'sg_path_to_frames', 'created_at', 'sg_uploaded_movie_mp4', 'sg_task', 'sg_status_list']
    versions = retry_sg(lambda: sg.find('Version', v_filters, v_fields))
    
    # Sort newest first
    versions.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    
    media_dict = {} # Map shot_id -> best version data
    
    for shot_id, shot_data in shot_dict.items():
        found_media = False
        shot_code = shot_data['code']
        
        # Determine Audio Path for this shot
        audio_path = 'MISSING'
        for ent_name, p in audio_dict.items():
            if shot_code in ent_name:
                audio_path = p
                break
        
        def get_shot_task_versions(target_task):
            found_versions_dict = {}
            for v in versions:
                v_shot_id = v.get('entity', {}).get('id')
                v_task_name = v.get('sg_task', {}).get('name')
                if v_shot_id == shot_id and v_task_name == target_task:
                    path_to_use = None
                    is_web_proxy = False
                    if use_image_seq:
                        raw_path = v.get('sg_path_to_frames')
                        if raw_path:
                            win_path = resolve_path(raw_path)
                            if win_path and os.path.exists(os.path.dirname(win_path)):
                                path_to_use = os.path.dirname(win_path)
                    if not path_to_use:
                        raw_path = v.get('sg_path_to_movie')
                        if raw_path:
                            win_path = resolve_path(raw_path)
                            if win_path and os.path.exists(win_path):
                                path_to_use = win_path
                            else:
                                web_url_field = v.get('sg_uploaded_movie_mp4')
                                if web_url_field:
                                    web_url = web_url_field.get('url') if isinstance(web_url_field, dict) else web_url_field
                                    if web_url:
                                        path_to_use = web_url
                                        is_web_proxy = True
                    if path_to_use:
                        v_code = v.get('code', '') or ''
                        base_v_code = v_code.lower().replace('-mjpeg', '').replace('-dnxhd', '').replace('.mov', '')
                        existing = found_versions_dict.get(base_v_code)
                        score = 2 if 'dnxhd' in path_to_use.lower() or 'dnxhd' in v_code.lower() else 1
                        if not existing or score > existing['score']:
                            found_versions_dict[base_v_code] = {
                                'path': path_to_use,
                                'is_web_proxy': is_web_proxy,
                                'score': score,
                                'created_at': v.get('created_at') or '',
                                'status': str(v.get('sg_status_list') or '').lower(),
                                'code': v.get('code', '')
                            }
            if found_versions_dict:
                res = list(found_versions_dict.values())
                res.sort(key=lambda x: str(x['created_at']), reverse=True)
                return res
            return []

        previous_version = None
        if task_wipe_enabled and task_wipe_v2 and task_wipe_v1:
            top_cands = get_shot_task_versions(task_wipe_v2)
            ref_cands = get_shot_task_versions(task_wipe_v1)
            if ref_cands:
                pv = ref_cands[0]
                previous_version = {'path': pv['path'], 'is_web_proxy': pv['is_web_proxy'], 'code': pv.get('code', ''), 'task': task_wipe_v1}
                log(f"  [{shot_code}] V1 Task Wipe: Found reference '{task_wipe_v1}' version '{pv['code']}'")
            else:
                previous_version = {'path': 'MISSING', 'is_web_proxy': False, 'code': '', 'task': task_wipe_v1, 'placeholder_text': f"NO REF TASK [{task_wipe_v1.upper()}]\n{shot_code}"}
                log(f"  [{shot_code}] V1 Task Wipe: No media found for reference task '{task_wipe_v1}'")

            if top_cands:
                base_ver = top_cands[0]
                media_dict[shot_id] = {
                    'shot_code': shot_code,
                    'task': task_wipe_v2,
                    'version_code': base_ver.get('code', ''),
                    'path': base_ver['path'],
                    'audio_path': audio_path,
                    'is_web_proxy': base_ver['is_web_proxy'],
                    'takes': top_cands[1:] if max_versions != 1 else [],
                    'cut_in': shot_data.get('sg_cut_in'),
                    'cut_out': shot_data.get('sg_cut_out'),
                    'head_in': shot_data.get('sg_head_in'),
                    'cut_order': shot_data.get('sg_cut_order'),
                    'previous_version': previous_version
                }
                found_media = True
        else:
            for task in valid_tasks:
                if found_media:
                    break
                found_versions = get_shot_task_versions(task)
                if found_versions:
                    previous_version = None
                    if ab_wipe_enabled and len(found_versions) >= 2:
                        target_status = str(ab_status or "rtk").lower()
                        retake_vers = [pv for pv in found_versions[1:] if pv.get('status') == target_status]
                        if retake_vers:
                            pv = retake_vers[0]
                            log(f"  [{shot_code}] V1 A/B Wipe: Prioritized targeted version '{pv['code']}' (status: {pv['status']})")
                        else:
                            pv = found_versions[1]
                            log(f"  [{shot_code}] V1 A/B Wipe: No status '{target_status}' found. Fallback to immediate predecessor '{pv['code']}'")
                        previous_version = {'path': pv['path'], 'is_web_proxy': pv['is_web_proxy'], 'code': pv.get('code', ''), 'task': task}
                    
                    if max_versions > 0:
                        found_versions = found_versions[:max_versions]
                    base_ver = found_versions[0]
                    media_dict[shot_id] = {
                        'shot_code': shot_code,
                        'task': task,
                        'version_code': base_ver.get('code', ''),
                        'path': base_ver['path'],
                        'audio_path': audio_path,
                        'is_web_proxy': base_ver['is_web_proxy'],
                        'takes': found_versions[1:],
                        'cut_in': shot_data.get('sg_cut_in'),
                        'cut_out': shot_data.get('sg_cut_out'),
                        'head_in': shot_data.get('sg_head_in'),
                        'cut_order': shot_data.get('sg_cut_order'),
                        'previous_version': previous_version
                    }
                    found_media = True
                    break 
                        
        if not found_media:
            media_dict[shot_id] = {
                'shot_code': shot_code,
                'task': task_wipe_v2 if task_wipe_enabled else 'NONE',
                'version_code': '',
                'path': 'MISSING',
                'audio_path': audio_path,
                'is_web_proxy': False,
                'cut_in': shot_data.get('sg_cut_in'),
                'cut_out': shot_data.get('sg_cut_out'),
                'head_in': shot_data.get('sg_head_in'),
                'cut_order': shot_data.get('sg_cut_order'),
                'previous_version': previous_version
            }
                        
    return media_dict

# ==========================================
# EVENT HANDLERS
# ==========================================
# Set initial state
items["TaskPresetCombo"].Enabled = False
items["HighestTaskCombo"].Enabled = True
items["LowestTaskCombo"].Enabled = True

def update_show_shots_btn():
    pass # Replaced by specific handlers

def OnUseHeroCheck(ev):
    checked = items["UseHeroCheck"].Checked
    items["HeroFilterLine"].Enabled = checked
    items["ReverseHeroCheck"].Enabled = checked
    items["ShowReviewShotsBtn"].Enabled = checked

def OnImageSeqCheck(ev):
    checked = items["ImageSeqCheck"].Checked
    items["ApplyLutCheck"].Enabled = checked

def OnAbWipeCheck(ev):
    checked = items["AbWipeCheck"].Checked
    items["AbStatusCombo"].Enabled = checked
    if checked and "TaskWipeCheck" in items:
        items["TaskWipeCheck"].Checked = False
        items["TaskWipeV2Combo"].Enabled = False
        items["TaskWipeV1Combo"].Enabled = False

def OnTaskWipeCheck(ev):
    checked = items["TaskWipeCheck"].Checked
    items["TaskWipeV2Combo"].Enabled = checked
    items["TaskWipeV1Combo"].Enabled = checked
    if checked and "AbWipeCheck" in items:
        items["AbWipeCheck"].Checked = False
        items["AbStatusCombo"].Enabled = False

def OnModeChange(ev):
    mode = items["ModeCombo"].CurrentText
    if mode == "Playlist Mode":
        items["SeqGrp"].Hide()
        items["TaskGrp"].Hide()
        items["TakeGrp"].Hide()
        items["PlaylistGrp"].Show()
    else:
        items["SeqGrp"].Show()
        items["TaskGrp"].Show()
        items["TakeGrp"].Show()
        items["PlaylistGrp"].Hide()

def OnFindPlaylistBtn(ev):
    project_name = items["ProjectCombo"].CurrentText
    search_text = items["PlaylistSearchLine"].Text.strip()
    if not project_name or not search_text: return
    
    items["FindPlaylistBtn"].Text = "Wait..."
    try:
        sg = shotgun_api3.Shotgun(FLOW_URL, script_name=SCRIPT_NAME, api_key=SCRIPT_KEY)
        proj = sg.find_one("Project", [["name", "is", project_name]], ["id"])
        if not proj: raise Exception("Project not found")
        
        # Search playlists containing the text in code
        playlists = sg.find("Playlist", [["project", "is", proj], ["code", "contains", search_text]], ["code"], limit=50)
        
        items["PlaylistCombo"].Clear()
        if playlists:
            for pl in playlists:
                items["PlaylistCombo"].AddItem(pl["code"])
        else:
            items["PlaylistCombo"].AddItem("No match found")
    except Exception as e:
        print(f"Error finding playlists: {e}")
    finally:
        items["FindPlaylistBtn"].Text = "Find"

def OnPresetCheck(ev):
    checked = items["UsePresetCheck"].Checked
    items["TaskPresetCombo"].Enabled = checked
    items["HighestTaskCombo"].Enabled = not checked
    items["LowestTaskCombo"].Enabled = not checked

def OnBuild(ev):
    proj_str = items["ProjectCombo"].CurrentText
    seq_str = items["SeqCombo"].CurrentText.strip()
    seq_padded = seq_str.zfill(4)
    is_playlist_mode = (items["ModeCombo"].CurrentText == "Playlist Mode")
    playlist_name = items["PlaylistCombo"].CurrentText
    highest_idx = int(items["HighestTaskCombo"].CurrentIndex)
    lowest_idx = items["LowestTaskCombo"].CurrentIndex
    use_img = items["ImageSeqCheck"].Checked
    use_lut = items["ApplyLutCheck"].Checked
    use_audio = items["UseAudio"].Checked
    include_missing_shots = items["MissingShotCheck"].Checked
    use_cut_order = items["CutOrderCheck"].Checked
    use_latest_timeline = items["UseLatestTimeline"].Checked
    ver_wipe_enabled = items["AbWipeCheck"].Checked
    task_wipe_enabled = items["TaskWipeCheck"].Checked if "TaskWipeCheck" in items else False
    ab_wipe_enabled = (ver_wipe_enabled or task_wipe_enabled)
    ab_status_raw = items["AbStatusCombo"].CurrentText if ver_wipe_enabled else "rtk"
    ab_status_val = ab_status_raw.split()[0].strip().lower() if ab_status_raw else "rtk"
    task_wipe_v2 = items["TaskWipeV2Combo"].CurrentText if task_wipe_enabled else None
    task_wipe_v1 = items["TaskWipeV1Combo"].CurrentText if task_wipe_enabled else None
    add_task_markers = items["AddTaskMarkersCheck"].Checked
    use_agx = items["AgxCheck"].Checked
    
    take_combo_text = items["TakeCountCombo"].CurrentText
    if take_combo_text == "None (Latest Only)":
        max_versions = 1
    elif take_combo_text == "All Versions":
        max_versions = 0
    else:
        try:
            max_versions = int(take_combo_text.split(" ")[1])
        except:
            max_versions = 0
            
    use_preset = items["UsePresetCheck"].Checked
    if use_preset:
        preset_name = items["TaskPresetCombo"].CurrentText
        valid_tasks = user_presets.get(preset_name, MASTER_TASKS)
    else:
        if highest_idx > lowest_idx:
            print("Error: Highest task must be above Lowest task in the hierarchy.")
            return
        valid_tasks = MASTER_TASKS[highest_idx:lowest_idx+1]
        
    # Parse target shots if not AllShotsCheck
    target_shots = []
    exclude_mode = False
    hero_shots = []
    hero_mode_active = items["UseHeroCheck"].Checked
    reverse_hero = items["ReverseHeroCheck"].Checked
    if hero_mode_active:
        hero_text = items["HeroFilterLine"].Text.strip()
        if hero_text:
            for p in hero_text.split(','):
                p = p.strip()
                if '-' in p:
                    subparts = p.split('-')
                    if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                        for i in range(int(subparts[0]), int(subparts[1]) + 1):
                            hero_shots.append(str(i).zfill(4))
                elif p.isdigit(): hero_shots.append(p.zfill(4))
                elif p:
                    import re
                    m = re.match(r'^(\d+)(.*)$', p)
                    if m: hero_shots.append(m.group(1).zfill(4) + m.group(2))
                    else: hero_shots.append(p)

    if not items["AllShotsCheck"].Checked:
        exclude_mode = items["ExcludeCheck"].Checked
        filter_text = items["ShotFilterLine"].Text.strip()
        if filter_text:
            parts = filter_text.split(',')
            for p in parts:
                p = p.strip()
                if '-' in p:
                    subparts = p.split('-')
                    if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                        start = int(subparts[0])
                        end = int(subparts[1])
                        for i in range(start, end + 1):
                            target_shots.append(str(i).zfill(4))
                elif p.isdigit():
                    target_shots.append(p.zfill(4))
                elif p:
                    import re
                    m = re.match(r'^(\d+)(.*)$', p)
                    if m:
                        target_shots.append(m.group(1).zfill(4) + m.group(2))
                    else:
                        target_shots.append(p)
                    
    print(f"Building Timeline for: Project={proj_str}, Seq={seq_padded}")
    if target_shots:
        print(f"Targeting specific shots: {target_shots}")
        
    log(f"\n--- Starting Build for {proj_str} Sequence {seq_padded} ---", level=2)
    # 1. Fetch
    media_data = fetch_flow_data(
        project_name=proj_str,
        sequence_name=seq_padded,
        valid_tasks=valid_tasks,
        use_image_seq=use_img,
        use_audio=use_audio,
        max_versions=max_versions,
        target_shots=target_shots,
        exclude_mode=exclude_mode,
        is_playlist_mode=is_playlist_mode,
        playlist_name=playlist_name,
        ab_wipe_enabled=ab_wipe_enabled,
        ab_status=ab_status_val,
        ver_wipe_enabled=ver_wipe_enabled,
        task_wipe_enabled=task_wipe_enabled,
        task_wipe_v2=task_wipe_v2,
        task_wipe_v1=task_wipe_v1
    )
    if not media_data:
        log("No media data gathered.", level=2)
        return
        
    base_folder_name = playlist_name if is_playlist_mode else seq_padded
    seq_bin = get_or_create_bin(base_folder_name)
    media_bin = get_or_create_sub_bin(seq_bin, "media")
    movies_bin = get_or_create_sub_bin(media_bin, "movies")
    audio_bin = get_or_create_sub_bin(media_bin, "audio")
    timeline_bin = get_or_create_sub_bin(seq_bin, "timeline")
    
    media_pool.SetCurrentFolder(media_bin)
    
    video_clip_infos = []
    v1_reference_clip_infos = []
    audio_clip_infos = []
    pending_takes_to_attach = []
    
    if use_cut_order:
        sorted_shots = sorted(media_data.values(), key=lambda x: (x.get('cut_order') or 999999, x['shot_code']))
    else:
        sorted_shots = sorted(media_data.values(), key=lambda x: x['shot_code'])
    
    log("\n=== Resolving Media Paths ===", level=4)
    if not os.path.exists(PROXY_DOWNLOAD_PATH):
        os.makedirs(PROXY_DOWNLOAD_PATH, exist_ok=True)
        
    # Phase 1: Collect all web proxy downloads needed
    download_tasks = []
    
    for data in sorted_shots:
        for idx, take_data in enumerate(data.get('takes', [])):
            if take_data['is_web_proxy']:
                safe_name = f"{data['shot_code']}_{data['task']}_v{idx+2}_proxy.mp4"
                local_proxy_path = os.path.join(PROXY_DOWNLOAD_PATH, safe_name)
                if not os.path.exists(local_proxy_path):
                    download_tasks.append((take_data['path'], local_proxy_path, safe_name))
                
        if data.get('is_web_proxy'):
            safe_name = f"{data['shot_code']}_{data['task']}_proxy.mp4"
            local_proxy_path = os.path.join(PROXY_DOWNLOAD_PATH, safe_name)
            if not os.path.exists(local_proxy_path):
                download_tasks.append((data['path'], local_proxy_path, safe_name))
                
        prev_v = data.get('previous_version')
        if prev_v and prev_v.get('is_web_proxy') and prev_v.get('path'):
            safe_prev_name = f"{data['shot_code']}_prev_{prev_v.get('code', 'v1')}_proxy.mp4"
            local_prev_path = os.path.join(PROXY_DOWNLOAD_PATH, safe_prev_name)
            if not os.path.exists(local_prev_path):
                download_tasks.append((prev_v['path'], local_prev_path, safe_prev_name))
                
    # Phase 2: Download them all in parallel!
    if download_tasks:
        log(f"Starting {len(download_tasks)} parallel proxy downloads... Please wait.", level=2)
        def _dl(url, lpath, sname):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with open(lpath, 'wb') as f:
                    f.write(urllib.request.urlopen(req).read())
                return f"Success: {sname}"
            except Exception as e:
                return f"Failed: {sname} ({e})"
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_dl, t[0], t[1], t[2]) for t in download_tasks]
            for f in concurrent.futures.as_completed(futures):
                logging.info(f.result())
        log("All parallel downloads finished!", level=2)
        
    # Phase 3: Resolve paths normally
    for data in sorted_shots:
        path = data['path']
        is_missing = (path == 'MISSING')
        is_web_proxy = data.get('is_web_proxy', False)
        
        takes_data_list = []
        for idx, take_data in enumerate(data.get('takes', [])):
            take_path = take_data['path']
            if take_data['is_web_proxy']:
                safe_name = f"{data['shot_code']}_{data['task']}_v{idx+2}_proxy.mp4"
                take_path = os.path.join(PROXY_DOWNLOAD_PATH, safe_name)
            takes_data_list.append(take_path)
        
        if is_missing:
            if not include_missing_shots:
                log(f"Skipping {data['shot_code']} -> MISSING MEDIA (Missing Shots is unchecked).")
                continue
            path = get_missing_media_path()
            log(f"Processing {data['shot_code']} -> MISSING MEDIA. Using placeholder.")
        elif is_web_proxy:
            safe_name = f"{data['shot_code']}_{data['task']}_proxy.mp4"
            path = os.path.join(PROXY_DOWNLOAD_PATH, safe_name)
            log(f"Processing {data['shot_code']} ({data['task']}) -> Using Local Proxy")
        else:
            log(f"Processing {data['shot_code']} ({data['task']}) -> {path}")
        
        # 1. Handle Video
        existing_clip = find_clip_in_folder(movies_bin, path)
        if not existing_clip:
            print("  -> Importing to Media Pool (movies).")
            media_pool.SetCurrentFolder(movies_bin)
            imported = media_pool.ImportMedia([path])
            if imported:
                existing_clip = imported[0]
                
        if existing_clip:
            is_hero = True
            if hero_mode_active:
                if data['shot_code'] in hero_shots:
                    is_hero = not reverse_hero
                else:
                    is_hero = reverse_hero
                    
            is_clip_exr = False
            orig_name = str(existing_clip.GetName() or "").lower()
            fpath = ""
            ffmt = ""
            try:
                fpath = str(existing_clip.GetClipProperty("File Path") or "").lower()
                ffmt = str(existing_clip.GetClipProperty("Format") or "").lower()
            except Exception:
                pass
            if ".exr" in orig_name or ".exr" in fpath or "exr" in ffmt or (use_img and not is_missing and not is_web_proxy):
                is_clip_exr = True
                    
            task_label = str(data.get('task', 'NONE')).strip()
            ver_label = str(data.get('version_code', '')).strip()
            if existing_clip and not is_missing and task_label not in ['NONE', 'playlist']:
                try:
                    display_name = f"[{task_label.upper()}] {data['shot_code']} {ver_label}".strip()
                    existing_clip.SetClipProperty("Clip Name", display_name)
                except Exception:
                    pass

            clip_info = {
                "mediaPoolItem": existing_clip,
                "is_hero": is_hero,
                "is_missing": is_missing,
                "shot_code": data['shot_code'],
                "cut_order": data.get('sg_cut_order'),
                "task": task_label,
                "version_code": ver_label,
                "is_exr": is_clip_exr,
                "is_web_proxy": is_web_proxy,
                "original_name": orig_name
            }
            if use_audio:
                clip_info["mediaType"] = 1 # Strip the embedded video audio
                
            if is_missing:
                unlock_still_image_duration(existing_clip)
                clip_info["startFrame"] = 0
                if data.get('cut_in') is not None and data.get('cut_out') is not None:
                    duration = int(data['cut_out']) - int(data['cut_in'])
                    clip_info["endFrame"] = max(1, duration)
                    print(f"  -> Applying Placeholder duration from cuts [{duration} frames]")
                else:
                    clip_info["endFrame"] = 48 # 2 seconds at 24fps
                    print(f"  -> No cuts in Flow. Defaulting Placeholder to 2s (48 frames).")
            else:
                if data.get('cut_in') is not None and data.get('cut_out') is not None:
                    duration = int(data['cut_out']) - int(data['cut_in'])
                    if use_img:
                        try:
                            start_f = int(existing_clip.GetClipProperty("Start"))
                        except:
                            start_f = int(data['cut_in'])
                        clip_info["startFrame"] = start_f
                        clip_info["endFrame"] = start_f + duration
                        print(f"  -> Applying Image Seq constraint: {duration} frames ({start_f} to {start_f + duration})")
                    else:
                        clip_info["startFrame"] = 0
                        clip_info["endFrame"] = duration
                        print(f"  -> Applying Video constraint: {duration} frames (0 to {duration})")
                
            video_clip_infos.append(clip_info)
            
            if ab_wipe_enabled:
                prev_info = dict(clip_info)
                prev_v = data.get('previous_version')
                prev_clip = None
                if prev_v and prev_v.get('path') and prev_v.get('path') != 'MISSING':
                    prev_path = prev_v['path']
                    if prev_v.get('is_web_proxy'):
                        safe_prev_name = f"{data['shot_code']}_prev_{prev_v.get('code', 'v1')}_proxy.mp4"
                        prev_path = os.path.join(PROXY_DOWNLOAD_PATH, safe_prev_name)
                    prev_clip = find_clip_in_folder(movies_bin, prev_path)
                    if not prev_clip and os.path.exists(prev_path):
                        media_pool.SetCurrentFolder(movies_bin)
                        imp_p = media_pool.ImportMedia([prev_path])
                        if imp_p: prev_clip = imp_p[0]
                
                if prev_clip:
                    prev_is_exr = False
                    orig_prev_name = str(prev_clip.GetName() or "").lower()
                    prev_fpath = ""
                    prev_ffmt = ""
                    try:
                        prev_fpath = str(prev_clip.GetClipProperty("File Path") or "").lower()
                        prev_ffmt = str(prev_clip.GetClipProperty("Format") or "").lower()
                    except Exception:
                        pass
                    if ".exr" in orig_prev_name or ".exr" in prev_fpath or "exr" in prev_ffmt or (use_img and not (prev_v and prev_v.get('is_web_proxy', False))):
                        prev_is_exr = True

                    prev_info["mediaPoolItem"] = prev_clip
                    prev_info["is_missing"] = False
                    prev_info["is_exr"] = prev_is_exr
                    prev_info["is_web_proxy"] = prev_v.get('is_web_proxy', False) if prev_v else False
                    prev_info["original_name"] = orig_prev_name
                    if "placeholder_text" in prev_info:
                        del prev_info["placeholder_text"]
                    prev_task_label = str(prev_v.get('task') if (prev_v and prev_v.get('task')) else data.get('task', 'NONE')).strip()
                    prev_ver_label = str(prev_v.get('code', '') if prev_v else '').strip()
                    prev_info["task"] = prev_task_label
                    prev_info["version_code"] = prev_ver_label
                    if prev_task_label not in ['NONE', 'playlist']:
                        try:
                            prev_display = f"[{prev_task_label.upper()}] {data['shot_code']} {prev_ver_label}".strip()
                            prev_clip.SetClipProperty("Clip Name", prev_display)
                        except Exception:
                            pass
                else:
                    missing_path = get_missing_media_path()
                    missing_item = find_clip_in_folder(movies_bin, missing_path)
                    if not missing_item and os.path.exists(missing_path):
                        media_pool.SetCurrentFolder(movies_bin)
                        imp_m = media_pool.ImportMedia([missing_path])
                        if imp_m: missing_item = imp_m[0]
                    if missing_item:
                        prev_info["mediaPoolItem"] = missing_item
                        unlock_still_image_duration(missing_item)
                    prev_info["is_missing"] = True
                    prev_info["is_exr"] = False
                    prev_info["placeholder_text"] = (prev_v.get("placeholder_text") if (prev_v and prev_v.get("placeholder_text")) else f"NO PREV VERSION\n{data['shot_code']}")
                    if "endFrame" in clip_info and "startFrame" in clip_info:
                        cand_dur = int(clip_info["endFrame"]) - int(clip_info["startFrame"])
                    else:
                        cand_dur = get_media_item_duration(clip_info.get("mediaPoolItem"), 48)
                    prev_info["startFrame"] = 0
                    prev_info["endFrame"] = max(1, cand_dur)
                    log(f"  -> Synchronized V1 placeholder duration to {cand_dur} frames to match candidate.")
                v1_reference_clip_infos.append(prev_info)
            
            # Now process takes
            if takes_data_list:
                imported_takes = []
                for tp in takes_data_list:
                    ec = find_clip_in_folder(movies_bin, tp)
                    if not ec:
                        media_pool.SetCurrentFolder(movies_bin)
                        imp = media_pool.ImportMedia([tp])
                        if imp: ec = imp[0]
                    if ec: imported_takes.append(ec)
                
                if imported_takes:
                    pending_takes_to_attach.append({
                        "video_index": len(video_clip_infos) - 1,
                        "duration": clip_info.get("endFrame", 48),
                        "media_items": imported_takes
                    })
        else:
            print("  -> ERROR: Failed to import Video.")
            
        # 2. Handle Audio
        if use_audio and not is_missing:
            audio_path = data.get('audio_path', 'MISSING')
            if audio_path == 'MISSING':
                print("  -> Missing audio. Skipping custom audio track for this shot.")
            else:
                print(f"  -> Audio Found: {audio_path}")
                
                existing_audio = find_clip_in_folder(audio_bin, audio_path)
                if not existing_audio:
                    media_pool.SetCurrentFolder(audio_bin)
                    imported_a = media_pool.ImportMedia([audio_path])
                    if imported_a:
                        existing_audio = imported_a[0]
                        
                if existing_audio:
                    a_info = {
                        "mediaPoolItem": existing_audio,
                        "mediaType": 2, # Explicitly Audio
                        "trackIndex": 1 # Place directly on Track 1 since we stripped video audio
                    }
                    if data.get('cut_in') is not None and data.get('cut_out') is not None:
                        duration = int(data['cut_out']) - int(data['cut_in'])
                        a_info["startFrame"] = 0
                        a_info["endFrame"] = duration
                    
                    # Store mapping so we know which video clip this syncs with
                    audio_clip_infos.append({
                        "video_index": len(video_clip_infos) - 1,
                        "info": a_info
                    })
                else:
                    print("  -> ERROR: Failed to import Audio.")

    # 4. Resolve Timeline (Find Latest or Create New)
    media_pool.SetCurrentFolder(timeline_bin)
    
    target_timeline = None
    tl_prefix = f"{playlist_name}_v" if is_playlist_mode else seq_padded
    
    matched_timelines = []
    for i in range(1, dvr_project.GetTimelineCount() + 1):
        tl = dvr_project.GetTimelineByIndex(i)
        if is_playlist_mode:
            if tl.GetName().startswith(tl_prefix):
                matched_timelines.append(tl)
        else:
            if tl.GetName().startswith(seq_padded):
                matched_timelines.append(tl)
                
    if matched_timelines:
        matched_timelines.sort(key=lambda t: t.GetName())
        highest_tl = matched_timelines[-1]
        
        if use_latest_timeline:
            target_timeline = highest_tl
            print(f"Found latest timeline: {target_timeline.GetName()}. Clearing existing clips...")
            dvr_project.SetCurrentTimeline(target_timeline)
            
            all_items = []
            for t_type in ['video', 'audio', 'subtitle']:
                t_count = target_timeline.GetTrackCount(t_type)
                for t_idx in range(1, t_count + 1):
                    t_items = target_timeline.GetItemListInTrack(t_type, t_idx)
                    if t_items:
                        all_items.extend(t_items)
            if all_items:
                target_timeline.DeleteClips(all_items)
        else:
            # Not using latest -> Increment version
            if is_playlist_mode:
                import re
                m = re.search(r'_v(\d{3})$', highest_tl.GetName())
                next_v = int(m.group(1)) + 1 if m else len(matched_timelines) + 1
                tl_name = f"{playlist_name}_v{str(next_v).zfill(3)}"
            else:
                date_str = datetime.datetime.now().strftime("%Y_%m_%d")
                tl_name = f"{seq_padded}_{date_str}_{len(matched_timelines)+1}"
                
    if not target_timeline:
        if not 'tl_name' in locals():
            if is_playlist_mode:
                tl_name = f"{playlist_name}_v001"
            else:
                date_str = datetime.datetime.now().strftime("%Y_%m_%d")
                tl_name = f"{seq_padded}_{date_str}"
        print(f"Creating New Timeline: {tl_name} in 'timeline' bin.")
        target_timeline = media_pool.CreateEmptyTimeline(tl_name)
    
    if target_timeline:
        dvr_project.SetCurrentTimeline(target_timeline)
    
    if ab_wipe_enabled:
        logging.info(f"A/B Wiping Mode: Appending {len(v1_reference_clip_infos)} previous/placeholder clips to Track 1 (V1)...")
        print(f"A/B Wiping Mode: Appending {len(v1_reference_clip_infos)} previous/placeholder clips to Track 1 (V1)...")
        media_pool.AppendToTimeline(v1_reference_clip_infos)
        appended_items = []
        all_grading_items = []
        
        if target_timeline:
            v1_track_items = target_timeline.GetItemListInTrack("video", 1) or []
            
            if target_timeline.GetTrackCount('video') < 2:
                target_timeline.AddTrack("video")
                
            logging.info(f"A/B Wiping Mode: Appending {len(video_clip_infos)} candidate clips to Track 2 (V2)...")
            print(f"A/B Wiping Mode: Appending {len(video_clip_infos)} candidate clips to Track 2 (V2)...")
            v2_submission = []
            for idx, cand_info in enumerate(video_clip_infos):
                c_copy = dict(cand_info)
                if idx < len(v1_track_items):
                    c_copy["recordFrame"] = int(v1_track_items[idx].GetStart())
                c_copy["trackIndex"] = 2
                v2_submission.append(c_copy)
                
            media_pool.AppendToTimeline(v2_submission)
            
            # Reliably pull fresh timeline items directly from Track 1 and Track 2
            v1_track_items = target_timeline.GetItemListInTrack("video", 1) or []
            v2_track_items = target_timeline.GetItemListInTrack("video", 2) or []
            
            appended_items = v2_track_items # Preserve V2 items for optional Takes attachments
            
            for idx, v1_item in enumerate(v1_track_items):
                if idx < len(v1_reference_clip_infos):
                    all_grading_items.append((v1_item, v1_reference_clip_infos[idx], "V1"))
                    
            for idx, v2_item in enumerate(v2_track_items):
                if idx < len(video_clip_infos):
                    all_grading_items.append((v2_item, video_clip_infos[idx], "V2"))
    else:
        logging.info(f"Appending {len(video_clip_infos)} video clips to timeline...")
        print(f"Appending {len(video_clip_infos)} video clips to timeline...")
        media_pool.AppendToTimeline(video_clip_infos)
        appended_items = target_timeline.GetItemListInTrack("video", 1) if target_timeline else []
        if not appended_items: appended_items = []
        all_grading_items = [(item, video_clip_infos[idx], "V1") for idx, item in enumerate(appended_items) if idx < len(video_clip_infos)]
    
    if all_grading_items:
        ensure_luts_installed()
        msg = f"Applying LUTs, DRX Node Grades, and Placeholders to {len(all_grading_items)} timeline clips across all tracks..."
        print(msg)
        logging.info(msg)
        try:
            dvr_project.RefreshLUTList()
            exr_lut_exists = ('EXR_LUT' in globals() and EXR_LUT)
            for item, info, track_name in all_grading_items:
                is_hero = info.get("is_hero", True)
                is_missing = info.get("is_missing", False)
                shot_code = info.get("shot_code", "UNKNOWN")
                
                task_label = info.get("task", "NONE")
                ver_label = info.get("version_code", "")
                clip_color = get_task_color(task_label)

                # Apply timeline clip color
                try:
                    item.SetClipColor(clip_color)
                except Exception:
                    pass

                # Apply clip markers if enabled by UI toggle
                if add_task_markers and not is_missing and task_label not in ['NONE', 'playlist']:
                    try:
                        start_f = 0
                        try:
                            start_f = int(item.GetLeftOffset())
                        except Exception:
                            start_f = int(item.GetStart())
                        marker_dur = 1
                        try:
                            if hasattr(item, "GetDuration"):
                                marker_dur = int(item.GetDuration())
                            else:
                                marker_dur = int(item.GetEnd() - item.GetStart())
                        except Exception:
                            try:
                                marker_dur = int(item.GetEnd() - item.GetStart())
                            except Exception:
                                marker_dur = 48
                        if marker_dur < 1:
                            marker_dur = 1
                        marker_note = f"Shot: {shot_code}\nTask: {task_label}\nVersion: {ver_label}\nLayer: {track_name}"
                        item.AddMarker(start_f, clip_color, f"Task: {task_label.upper()}", marker_note, marker_dur)
                    except Exception as m_err:
                        log(f"  -> Warning: Failed to apply marker on {shot_code}: {m_err}")

                if is_missing:
                    placeholder_str = info.get("placeholder_text", f"NO CLIP\n{shot_code}")
                    p_msg = f"Track {track_name} [{shot_code}]: Applying Fusion Title Placeholder: {placeholder_str.replace(chr(10), ' - ')}"
                    print(p_msg)
                    logging.info(p_msg)
                    fusion_comp = item.AddFusionComp()
                    if fusion_comp:
                        bg_node = fusion_comp.AddTool("Background", True)
                        text_node = fusion_comp.AddTool("TextPlus", True)
                        merge_node = fusion_comp.AddTool("Merge", True)
                        
                        # Set colors (Solid Red)
                        bg_node.SetInput("TopLeftRed", 1.0)
                        bg_node.SetInput("TopLeftGreen", 0.0)
                        bg_node.SetInput("TopLeftBlue", 0.0)
                        bg_node.SetInput("TopRightRed", 1.0)
                        bg_node.SetInput("TopRightGreen", 0.0)
                        bg_node.SetInput("TopRightBlue", 0.0)
                        bg_node.SetInput("BottomLeftRed", 1.0)
                        bg_node.SetInput("BottomLeftGreen", 0.0)
                        bg_node.SetInput("BottomLeftBlue", 0.0)
                        bg_node.SetInput("BottomRightRed", 1.0)
                        bg_node.SetInput("BottomRightGreen", 0.0)
                        bg_node.SetInput("BottomRightBlue", 0.0)
                        
                        # Set text
                        text_node.SetInput("StyledText", placeholder_str)
                        
                        # Connect them
                        merge_node.SetInput("Background", bg_node)
                        merge_node.SetInput("Foreground", text_node)
                        
                        # Connect to MediaOut
                        media_out = fusion_comp.FindTool("MediaOut1")
                        if media_out:
                            media_out.SetInput("Input", merge_node)
                    continue

                item_name_lower = str(item.GetName() or "").lower()
                mp_path = ""
                mp_fmt = ""
                mp_name = ""
                try:
                    mp_item = item.GetMediaPoolItem()
                    if mp_item:
                        mp_path = str(mp_item.GetClipProperty("File Path") or "").lower()
                        mp_fmt = str(mp_item.GetClipProperty("Format") or "").lower()
                        mp_name = str(mp_item.GetName() or "").lower()
                except Exception:
                    pass
                
                is_exr = info.get("is_exr", False) or ".exr" in item_name_lower or ".exr" in mp_path or "exr" in mp_fmt or ".exr" in mp_name or (use_img and not is_missing and not info.get("is_web_proxy", False))
                lut_to_apply = None
                drx_to_apply = None

                proj_key = proj_str.lower()
                active_config = SHOW_CONFIGS.get(proj_key, SHOW_CONFIGS.get("default", {}))
                allow_agx = active_config.get("allow_agx", True)
                apply_agx = use_agx and allow_agx

                if use_agx and not allow_agx:
                    print(f"Notice: AgX Pipeline ignored for clip '{item.GetName()}' because project '{proj_str}' forbids AgX.")

                if apply_agx:
                    # AgX Pipeline Logic (configured dynamically via configs/agx.json):
                    agx_cfg = SHOW_CONFIGS.get("agx", {})
                    
                    if is_exr:
                        # EXRs require a CST node (ACEScg -> ACEScct) prior to agx_acescct_to_rec709.cube
                        cst_drx = agx_cfg.get("exr_drx_grade", "AgX_exr_cst.drx")
                        cst_drx_path = os.path.join(SCRIPT_DIR, "drx", cst_drx)
                        if os.path.exists(cst_drx_path):
                            drx_to_apply = cst_drx_path
                        else:
                            print(f"Warning: AgX EXR CST .drx file not found at {cst_drx_path}")
                    elif any(ext in str(info.get("original_name", "")) or ext in mp_path or ext in mp_name or ext in item_name_lower for ext in [".png", ".jpg", ".jpeg", ".tga", ".tiff", ".tif"]):
                        # Stills use sRGB-to-AgX 65^3 cube directly without external DCTL dependencies
                        lut_to_apply = agx_cfg.get("stills_lut", "davinciFlow/agx_srgb_img.cube")
                    else:
                        # Video proxies (.mov, .mp4, DNxHD) use Rec709-to-AgX 65^3 cube directly
                        lut_to_apply = agx_cfg.get("proxy_lut", "davinciFlow/agx_rec709_proxy.cube")
                elif is_exr and use_lut:
                    # Dynamic Project Node Pipeline (e.g. TMNT2)
                    drx_file = active_config.get("exr_drx_grade", "Acescg.drx")
                    drx_path = os.path.join(SCRIPT_DIR, "drx", drx_file)
                    
                    if os.path.exists(drx_path):
                        drx_to_apply = drx_path
                    else:
                        print(f"Warning: Project DRX file not found at {drx_path}")
                else:
                    # Standard LUT Pipeline Logic
                    if is_exr:
                        if is_hero and use_lut and exr_lut_exists:
                            lut_to_apply = EXR_LUT
                        elif not is_hero:
                            if exr_lut_exists:
                                basename = os.path.basename(EXR_LUT)
                                name, ext = os.path.splitext(basename)
                                lut_to_apply = f"davinciFlow/{name}_bw{ext}"
                            else:
                                lut_to_apply = "davinciFlow/proxy_bw.cube"
                    else:
                        if not is_hero:
                            lut_to_apply = "davinciFlow/proxy_bw.cube"

                if drx_to_apply:
                    try:
                        # 0: "No keyframes", 1: "Source Timecode aligned", 2: "Start Frames aligned"
                        res = item.GetNodeGraph().ApplyGradeFromDRX(drx_to_apply, 0)
                        g_msg = f"Track {track_name} [{shot_code}]: Applied DRX {drx_to_apply} -> {res}"
                        print(g_msg)
                        logging.info(g_msg)
                    except Exception as e:
                        err_msg = f"Warning: Track {track_name} [{shot_code}]: Failed to apply DRX grade: {e}"
                        print(err_msg)
                        logging.warning(err_msg)
                elif lut_to_apply:
                    try:
                        try:
                            item.GetNodeGraph().SetLUT(1, lut_to_apply)
                        except AttributeError:
                            item.SetLUT(1, lut_to_apply)
                        l_msg = f"Track {track_name} [{shot_code}]: Applied LUT {lut_to_apply}"
                        print(l_msg)
                        logging.info(l_msg)
                    except Exception as e:
                        l_err = f"Warning: Track {track_name} [{shot_code}]: Failed to apply LUT: {e}"
                        print(l_err)
                        logging.warning(l_err)
        except Exception as e:
            err = f"Warning: Failed during grading loop: {e}"
            print(err)
            logging.error(err)
            
    if appended_items and pending_takes_to_attach:
        print("Attaching previous versions as Takes...")
        for take_info in pending_takes_to_attach:
            v_idx = take_info["video_index"]
            if v_idx < len(appended_items):
                tl_item = appended_items[v_idx]
                dur = take_info["duration"]
                for take_media in take_info["media_items"]:
                    tl_item.AddTake(take_media, 0, dur)
    
    if use_audio and audio_clip_infos:
        print(f"Appending {len(audio_clip_infos)} audio clips to timeline Track 1...")
        if target_timeline.GetTrackCount('audio') == 0:
            target_timeline.AddTrack("audio")
            
        # Match audio clips explicitly to the starting frames of the video clips
        video_items = target_timeline.GetItemListInTrack('video', 1)
        final_audio_infos = []
        if video_items:
            for item_dict in audio_clip_infos:
                v_idx = item_dict["video_index"]
                if v_idx < len(video_items):
                    a_info = item_dict["info"]
                    a_info["recordFrame"] = int(video_items[v_idx].GetStart())
                    final_audio_infos.append(a_info)
                    
        if final_audio_infos:
            media_pool.AppendToTimeline(final_audio_infos)
    
    print("Build Complete!")
def OnCancel(ev):
    dispatcher.ExitLoop()

def OnAllShotsCheck(ev):
    checked = items["AllShotsCheck"].Checked
    items["ShotFilterLine"].Enabled = not checked
    items["ExcludeCheck"].Enabled = not checked
    items["ShowShotsBtn"].Enabled = not checked

def create_show_shots_handler(target_line_id):
    def handler(ev):
        project_name = items["ProjectCombo"].CurrentText
        is_playlist_mode = (items["ModeCombo"].CurrentText == "Playlist Mode")
        
        if not is_playlist_mode:
            seq_name = items["SeqCombo"].CurrentText
            if not project_name or not seq_name: return
        else:
            playlist_name = items["PlaylistCombo"].CurrentText
            if not project_name or not playlist_name: return
            
        try:
            sg = shotgun_api3.Shotgun(FLOW_URL, script_name=SCRIPT_NAME, api_key=SCRIPT_KEY)
            proj = sg.find_one("Project", [["name", "is", project_name]], ["id"])
            if not proj: raise Exception("Project not found")
            
            if not is_playlist_mode:
                seq = sg.find_one("Sequence", [["code", "is", seq_name], ["project", "is", proj]], ["id"])
                if not seq: raise Exception("Sequence not found")
                shots = sg.find("Shot", [["sg_sequence", "is", seq], ["sg_status_list", "is_not", "omt"]], ["code"])
                codes = sorted([s["code"] for s in shots])
                win_title = f"Available Shots: {seq_name}"
            else:
                pl = sg.find_one("Playlist", [["code", "is", playlist_name], ["project", "is", proj]], ["versions"])
                if not pl or not pl.get("versions"): raise Exception("Playlist not found or empty")
                v_ids = [v["id"] for v in pl["versions"]]
                versions = sg.find("Version", [["id", "in", v_ids]], ["entity"])
                shot_codes = set()
                for v in versions:
                    ent = v.get("entity")
                    if ent and ent["type"] == "Shot":
                        shot_codes.add(ent["name"])
                codes = sorted(list(shot_codes))
                win_title = f"Available Shots: {playlist_name}"
            
            layout_shots = ui.VGroup([
                ui.Tree({"ID": "ShotTree", "Weight": 1}),
                ui.HGroup({"Weight": 0}, [
                    ui.Button({"ID": "AddBtn", "Text": "Add Shots"}),
                    ui.Button({"ID": "ClearBtn", "Text": "Clear"}),
                    ui.Label({"Weight": 1}),
                    ui.Button({"ID": "CloseShotsBtn", "Text": "Close", "Weight": 0})
                ])
            ])
            
            win_shots = dispatcher.AddWindow({
                "ID": "ShotsWin",
                "Geometry": [200, 200, 300, 400],
                "WindowTitle": win_title
            }, layout_shots)
            
            w_items = win_shots.GetItems()
            tree = w_items["ShotTree"]
            tree.SelectionMode = "ExtendedSelection"
            
            hdr = tree.NewItem()
            hdr.Text[0] = "Shot Code"
            tree.SetHeaderItem(hdr)
            tree.ColumnCount = 1
            
            for code in codes:
                it = tree.NewItem()
                it.Text[0] = code
                tree.AddTopLevelItem(it)
                
            def OnShotsClose(ev_close):
                win_shots.Hide()
                
            def OnAdd(ev_add):
                selected = tree.SelectedItems()
                codes_to_add = []
                if selected:
                    items_iter = selected.values() if isinstance(selected, dict) else selected
                    for item in items_iter:
                        codes_to_add.append(item.Text[0])
                
                if codes_to_add:
                    codes_str = ", ".join(codes_to_add)
                    current_text = items[target_line_id].Text.strip()
                    if current_text:
                        if not current_text.endswith(","):
                            current_text += ", "
                        items[target_line_id].Text = current_text + codes_str
                    else:
                        items[target_line_id].Text = codes_str
                        
            def OnClear(ev_clear):
                items[target_line_id].Text = ""
                
            win_shots.On.CloseShotsBtn.Clicked = OnShotsClose
            win_shots.On.ShotsWin.Close = OnShotsClose
            win_shots.On.AddBtn.Clicked = OnAdd
            win_shots.On.ClearBtn.Clicked = OnClear
            
            win_shots.Show()
        except Exception as e:
            print(f"Error fetching shots: {e}")

    return handler


UI_STATE = {
    "FlowGrp": True,
    "AbWipeGrp": True,
    "ShotGrp": True,
    "FileGrp": True,
    "TaskGrp": True,
    "TimelineGrp": True,
    "AdvancedGrp": False
}

def create_toggle_handler(group_id, btn_id, title):
    def handler(ev):
        UI_STATE[group_id] = not UI_STATE[group_id]
        if UI_STATE[group_id]:
            items[group_id].Show()
            items[btn_id].Text = f"▼ {title}"
        else:
            items[group_id].Hide()
            items[btn_id].Text = f"▶ {title}"
    return handler

def OnCleanCache(ev):
    import shutil
    import os
    if os.path.exists(PROXY_DIR):
        try:
            for item in os.listdir(PROXY_DIR):
                item_path = os.path.join(PROXY_DIR, item)
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            print(f"Cache cleaned successfully: {PROXY_DIR}")
        except Exception as e:
            print(f"Failed to clean cache: {e}")
    else:
        print("Cache directory does not exist yet.")

def OnToggleMarkers(ev):
    try:
        if not dvr:
            print("Error: Not inside DaVinci Resolve environment.")
            return
        resolve = dvr.scriptapp("Resolve")
        if not resolve:
            print("Error: Failed to get DaVinci Resolve scriptapp.")
            return
        proj_mgr = resolve.GetProjectManager()
        curr_proj = proj_mgr.GetCurrentProject() if proj_mgr else None
        if not curr_proj:
            print("Error: No active project found.")
            return
        curr_tl = curr_proj.GetCurrentTimeline()
        if not curr_tl:
            print("Error: No active timeline found.")
            return
            
        track_count = curr_tl.GetTrackCount("video")
        if not track_count or track_count < 1:
            print("No video tracks found on active timeline.")
            return

        # Scan timeline to determine if any markers currently exist
        any_markers_found = False
        for t_idx in range(1, track_count + 1):
            items_list = curr_tl.GetItemListInTrack("video", t_idx) or []
            for itm in items_list:
                try:
                    markers = itm.GetMarkers()
                    if markers and len(markers) > 0:
                        any_markers_found = True
                        break
                except Exception:
                    pass
            if any_markers_found:
                break
                
        if any_markers_found:
            print("Toggling Markers: Clearing all markers from active timeline...")
            cleared_count = 0
            for t_idx in range(1, track_count + 1):
                items_list = curr_tl.GetItemListInTrack("video", t_idx) or []
                for itm in items_list:
                    try:
                        markers = itm.GetMarkers() or {}
                        for fid in list(markers.keys()):
                            itm.DeleteMarker(fid)
                            cleared_count += 1
                    except Exception:
                        pass
            print(f"-> Successfully removed {cleared_count} markers.")
        else:
            print("Toggling Markers: Re-applying full-duration departmental markers to timeline clips...")
            added_count = 0
            for t_idx in range(1, track_count + 1):
                items_list = curr_tl.GetItemListInTrack("video", t_idx) or []
                for itm in items_list:
                    try:
                        name_str = str(itm.GetName() or "").strip()
                        if "NO CLIP" in name_str or "NO PREV" in name_str or "NO REF" in name_str:
                            continue
                        task_str = "REVIEW"
                        shot_str = name_str
                        ver_str = ""
                        clip_color = "Teal"
                        
                        if name_str.startswith("[") and "]" in name_str:
                            parts = name_str.split("]", 1)
                            task_str = parts[0][1:].strip()
                            remainder = parts[1].strip().split()
                            if remainder:
                                shot_str = remainder[0]
                                if len(remainder) > 1:
                                    ver_str = remainder[1]
                            clip_color = get_task_color(task_str.lower())
                        else:
                            try:
                                curr_col = itm.GetClipColor()
                                if curr_col and curr_col != "None":
                                    clip_color = curr_col
                            except Exception:
                                pass

                        marker_dur = 1
                        try:
                            if hasattr(itm, "GetDuration"):
                                marker_dur = int(itm.GetDuration())
                            else:
                                marker_dur = int(itm.GetEnd() - itm.GetStart())
                        except Exception:
                            try:
                                marker_dur = int(itm.GetEnd() - itm.GetStart())
                            except Exception:
                                marker_dur = 48
                        if marker_dur < 1:
                            marker_dur = 1

                        start_f = 0
                        try:
                            start_f = int(itm.GetLeftOffset())
                        except Exception:
                            try:
                                start_f = int(itm.GetStart())
                            except Exception:
                                pass
                                
                        note_str = f"Shot: {shot_str}\nTask: {task_str}\nVersion: {ver_str}\nTrack: V{t_idx}"
                        itm.AddMarker(start_f, clip_color, f"Task: {task_str.upper()}", note_str, marker_dur)
                        added_count += 1
                    except Exception:
                        pass
            print(f"-> Successfully applied full-duration markers to {added_count} clips.")
    except Exception as e:
        print(f"Error toggling markers: {e}")

def OnProjectChange(ev):
    proj_name = items["ProjectCombo"].CurrentText
    proj_str = proj_name.lower() if proj_name else "default"
    cfg = SHOW_CONFIGS.get(proj_str, SHOW_CONFIGS.get(proj_name, SHOW_CONFIGS.get("default", {})))
    allow_agx = cfg.get("allow_agx", True)
    if not allow_agx:
        items["AgxCheck"].Checked = False
        items["AgxCheck"].Enabled = False
        items["AgxCheck"].ToolTip = f"AgX Pipeline is disabled by show specification ({proj_name})"
    else:
        items["AgxCheck"].Enabled = True
        items["AgxCheck"].ToolTip = "Apply AgX color pipeline instead of standard LUTs"
        
    if ev is not None and proj_name:
        try:
            items["SeqCombo"].Clear()
            new_seqs = get_sequences(proj_name)
            for s in new_seqs:
                items["SeqCombo"].AddItem(s)
        except Exception as err:
            log(f"Error updating sequences for project {proj_name}: {err}", 2)

win.On.ProjectCombo.CurrentIndexChanged = OnProjectChange
win.On.CleanCacheBtn.Clicked = OnCleanCache
win.On.ToggleMarkersBtn.Clicked = OnToggleMarkers
win.On.BuildBtn.Clicked = OnBuild
win.On.CancelBtn.Clicked = OnCancel
win.On.FlowDialog.Close = OnCancel
win.On.UseHeroCheck.Clicked = OnUseHeroCheck
win.On.ImageSeqCheck.Clicked = OnImageSeqCheck
win.On.AbWipeCheck.Clicked = OnAbWipeCheck
win.On.TaskWipeCheck.Clicked = OnTaskWipeCheck
win.On.UsePresetCheck.Clicked = OnPresetCheck
win.On.ModeCombo.CurrentIndexChanged = OnModeChange
win.On.FindPlaylistBtn.Clicked = OnFindPlaylistBtn
win.On.AllShotsCheck.Clicked = OnAllShotsCheck
win.On.ShowShotsBtn.Clicked = create_show_shots_handler("ShotFilterLine")
win.On.ShowReviewShotsBtn.Clicked = create_show_shots_handler("HeroFilterLine")
win.On.FlowHeaderBtn.Clicked = create_toggle_handler("FlowGrp", "FlowHeaderBtn", "FLOW")
win.On.AbWipeHeaderBtn.Clicked = create_toggle_handler("AbWipeGrp", "AbWipeHeaderBtn", "A/B WIPE")
win.On.ShotHeaderBtn.Clicked = create_toggle_handler("ShotGrp", "ShotHeaderBtn", "SHOT")
win.On.FileHeaderBtn.Clicked = create_toggle_handler("FileGrp", "FileHeaderBtn", "FILE")
win.On.TaskHeaderBtn.Clicked = create_toggle_handler("TaskGrp", "TaskHeaderBtn", "TASKS")
win.On.TimelineHeaderBtn.Clicked = create_toggle_handler("TimelineGrp", "TimelineHeaderBtn", "TIMELINE")
win.On.AdvancedHeaderBtn.Clicked = create_toggle_handler("AdvancedGrp", "AdvancedHeaderBtn", "ADVANCED")

# Initialize AdvancedGrp state to hidden
items["AdvancedGrp"].Hide()
items["AdvancedHeaderBtn"].Text = "▶ ADVANCED"

# Initialize UI state based on default selected project
OnProjectChange(None)

# ==========================================
# EXECUTE UI
# ==========================================
win.Show()
dispatcher.RunLoop()
win.Hide()
