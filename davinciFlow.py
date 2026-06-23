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
    if os.path.exists(r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"):
        _dir = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"
    else:
        _dir = r"W:\jmji\_sandbox\dulacd\Script\Blender"
LOG_PATH = os.path.join(_dir, "davinciFlow.log")



# ==========================================
# FLOW AUTHENTICATION & CONFIG
# ==========================================
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # DaVinci Resolve's embedded interpreter doesn't set __file__
    if os.path.exists(r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"):
        SCRIPT_DIR = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\davinciFlow"
    else:
        SCRIPT_DIR = r"W:\jmji\_sandbox\dulacd\Script\Blender"
    
CONFIG_PATH = os.path.join(SCRIPT_DIR, "davinciFlow_config.json")

# Default fallback values if config fails
FLOW_URL = "https://mikrosanim.priv.shotgunstudio.com/"
SCRIPT_NAME = "resolveTest"
SCRIPT_KEY = "vblervsd(ubdZzxsxtvo5jimv"
PROXY_DOWNLOAD_PATH = r"T:\flowDavinci"
PROJECTS = ["Tmnt2"]
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
            PROJECTS = config.get('projects', PROJECTS)
            MASTER_TASKS = config.get('tasks', MASTER_TASKS)
            EXR_LUT = config.get('exr_lut', '')
    except Exception as e:
        print(f"Failed to load json config: {e}")

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

def _path_exists_smart(p):
    if "%" in p or "#" in p:
        return os.path.exists(os.path.dirname(p))
    return os.path.exists(p)

def resolve_path(raw_path):
    if not raw_path: return None
    
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
    ui.Label({"Text": "--- FLOW ---", "Alignment": {"AlignHCenter": True}}),
    ui.HGroup([
        ui.Label({"Text": "Project:", "ToolTip": "Select the Flow project to load"}),
        ui.ComboBox({"ID": "ProjectCombo", "Weight": 2, "ToolTip": "Select the Flow project to load"})
    ]),
    ui.HGroup([
        ui.Label({"Text": "Sequence Number:", "ToolTip": "Select the sequence to build"}),
        ui.ComboBox({"ID": "SeqCombo", "Weight": 2, "ToolTip": "Select the sequence to build"})
    ]),
    ui.HGroup([
        ui.Label({"Text": "Use Image Sequences:", "ToolTip": "Download and load heavy image sequences instead of proxy movies", "Weight": 0}),
        ui.CheckBox({"ID": "ImageSeqCheck", "Checked": False, "ToolTip": "Download and load heavy image sequences instead of proxy movies", "Weight": 0}),
        ui.VGap(2),
        ui.CheckBox({"ID": "ApplyLutCheck", "Text": "Apply LUT", "Checked": True, "ToolTip": "Apply the color management LUT defined in the config to the EXR sequences", "Weight": 0}),
        ui.Label({"Weight": 1})
    ]),
    ui.HGroup([
        ui.Label({'Text': 'Audio File:', "ToolTip": "Fetch and sync published audio (.wav) from Flow to the timeline", "Weight": 0}),
        ui.CheckBox({'ID': 'UseAudio', 'Checked': False, "ToolTip": "Fetch and sync published audio (.wav) from Flow to the timeline", "Weight": 0}),
        ui.Label({"Weight": 1})
    ]),
    ui.VGap(5),
    
    ui.Label({"Text": "--- TASKS ---", "Alignment": {"AlignHCenter": True}}),
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
    ui.VGap(5),
    
    ui.Label({"Text": "--- TIMELINE ---", "Alignment": {"AlignHCenter": True}}),
    ui.HGroup([
        ui.Label({'Text': 'Load Takes:', "ToolTip": "Choose how many historical versions of a shot to stack into a DaVinci Take"}),
        ui.ComboBox({'ID': 'TakeCountCombo', 'Weight': 2, "ToolTip": "Choose how many historical versions of a shot to stack into a DaVinci Take"})
    ]),
    ui.HGroup([
        ui.Label({'Text': 'Timeline Options:', "ToolTip": "Manage timeline creation", "Weight": 0}),
        ui.CheckBox({'ID': 'UseLatestTimeline', 'Text': 'Update latest timeline (clears existing clips)', 'Checked': True, "ToolTip": "Overwrite the latest matching timeline instead of cluttering your bins with new timelines", "Weight": 0}),
        ui.Label({"Weight": 1})
    ]),
    
    ui.VGap(10),
    ui.HGroup({'Weight': 0, 'Spacing': 10}, [
        ui.Button({'ID': 'CancelBtn', 'Text': 'Cancel', 'ToolTip': 'Close the tool'}),
        ui.Button({'ID': 'BuildBtn', 'Text': 'Build Sequence', 'ToolTip': 'Fetch media from Flow and construct the timeline'})
    ])
])

win = dispatcher.AddWindow({
    "ID": "FlowDialog",
    "Geometry": [400, 400, 550, 450],
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

if user_presets:
    for preset_name in user_presets.keys():
        items["TaskPresetCombo"].AddItem(preset_name)

items["TakeCountCombo"].AddItem("None (Latest Only)")
items["TakeCountCombo"].AddItem("Last 2 Versions")
items["TakeCountCombo"].AddItem("Last 3 Versions")
items["TakeCountCombo"].AddItem("Last 4 Versions")
items["TakeCountCombo"].AddItem("Last 5 Versions")
items["TakeCountCombo"].AddItem("All Versions")

# Set defaults for task ranges
if MASTER_TASKS:
    items["HighestTaskCombo"].CurrentIndex = 0
    items["LowestTaskCombo"].CurrentIndex = len(MASTER_TASKS) - 1

# ==========================================
# FETCH DATA
# ==========================================
PROJECT_CACHE = {}

def fetch_flow_data(project_name, sequence_name, valid_tasks, use_image_seq, use_audio, max_versions):
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

    # Fetch all shots in sequence to get timing and ID
    log(f"\nQuerying Shots for Sequence {sequence_name}...")
    shot_filters = [
        ['project', 'is', project],
        ['sg_sequence', 'name_is', sequence_name]
    ]
    shot_fields = ['id', 'code', 'sg_cut_in', 'sg_cut_out', 'sg_head_in']
    shots = retry_sg(lambda: sg.find('Shot', shot_filters, shot_fields))
    
    if not shots:
        print("No shots found.")
        return None
        
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
    
    # Query all versions for these shots in the valid tasks
    v_filters = [
        ['project', 'is', project],
        ['entity', 'in', shots],
        ['sg_task.Task.content', 'in', valid_tasks]
    ]
    v_fields = ['entity', 'code', 'sg_path_to_movie', 'sg_path_to_frames', 'created_at', 'sg_uploaded_movie_mp4', 'sg_task']
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
        
        for task in valid_tasks:
            if found_media:
                break
                
            found_versions_dict = {}
            
            for v in versions:
                v_shot_id = v.get('entity', {}).get('id')
                v_task_name = v.get('sg_task', {}).get('name')
                
                if v_shot_id == shot_id and v_task_name == task:
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
                                'created_at': v.get('created_at') or ''
                            }
                        
            if found_versions_dict:
                found_versions = list(found_versions_dict.values())
                found_versions.sort(key=lambda x: x['created_at'], reverse=True)
                
                if max_versions > 0:
                    found_versions = found_versions[:max_versions]
                    
                base_ver = found_versions[0]
                takes_list = found_versions[1:]
                
                media_dict[shot_id] = {
                    'shot_code': shot_code,
                    'task': task,
                    'path': base_ver['path'],
                    'audio_path': audio_path,
                    'is_web_proxy': base_ver['is_web_proxy'],
                    'takes': takes_list,
                    'cut_in': shot_data.get('sg_cut_in'),
                    'cut_out': shot_data.get('sg_cut_out'),
                    'head_in': shot_data.get('sg_head_in')
                }
                found_media = True
                break 
                        
        if not found_media:
            media_dict[shot_id] = {
                'shot_code': shot_code,
                'task': 'NONE',
                'path': 'MISSING',
                'audio_path': audio_path,
                'is_web_proxy': False,
                'cut_in': shot_data.get('sg_cut_in'),
                'cut_out': shot_data.get('sg_cut_out'),
                'head_in': shot_data.get('sg_head_in')
            }
                        
    return media_dict

# ==========================================
# EVENT HANDLERS
# ==========================================
# Set initial state
items["TaskPresetCombo"].Enabled = False
items["HighestTaskCombo"].Enabled = True
items["LowestTaskCombo"].Enabled = True

def OnPresetCheck(ev):
    checked = items["UsePresetCheck"].Checked
    items["TaskPresetCombo"].Enabled = checked
    items["HighestTaskCombo"].Enabled = not checked
    items["LowestTaskCombo"].Enabled = not checked

def OnBuild(ev):
    project_name = items["ProjectCombo"].CurrentText
    seq_str = items["SeqCombo"].CurrentText.strip()
    seq_padded = seq_str.zfill(4)
    highest_idx = int(items["HighestTaskCombo"].CurrentIndex)
    lowest_idx = items["LowestTaskCombo"].CurrentIndex
    use_img = items["ImageSeqCheck"].Checked
    use_lut = items["ApplyLutCheck"].Checked
    use_audio = items["UseAudio"].Checked
    use_latest_timeline = items["UseLatestTimeline"].Checked
    
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
        
    log(f"\n--- Starting Build for {project_name} Sequence {seq_padded} ---", level=2)
    # 1. Fetch
    media_data = fetch_flow_data(project_name, seq_padded, valid_tasks, use_img, use_audio, max_versions)
    if not media_data:
        log("No media data gathered.", level=2)
        return
        
    seq_bin = get_or_create_bin(seq_padded)
    media_bin = get_or_create_sub_bin(seq_bin, "media")
    movies_bin = get_or_create_sub_bin(media_bin, "movies")
    audio_bin = get_or_create_sub_bin(media_bin, "audio")
    timeline_bin = get_or_create_sub_bin(seq_bin, "timeline")
    
    media_pool.SetCurrentFolder(media_bin)
    
    video_clip_infos = []
    audio_clip_infos = []
    pending_takes_to_attach = []
    
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
            clip_info = {
                "mediaPoolItem": existing_clip
            }
            if use_audio:
                clip_info["mediaType"] = 1 # Strip the embedded video audio
                
            if is_missing:
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
    if use_latest_timeline:
        matched_timelines = []
        for i in range(1, dvr_project.GetTimelineCount() + 1):
            tl = dvr_project.GetTimelineByIndex(i)
            if tl.GetName().startswith(seq_padded):
                matched_timelines.append(tl)
                
        if matched_timelines:
            matched_timelines.sort(key=lambda t: t.GetName())
            target_timeline = matched_timelines[-1]
            print(f"Found latest timeline: {target_timeline.GetName()}. Clearing existing clips...")
            
            dvr_project.SetCurrentTimeline(target_timeline)
            
            for t_type in ['video', 'audio', 'subtitle']:
                t_count = target_timeline.GetTrackCount(t_type)
                for t_idx in range(1, t_count + 1):
                    t_items = target_timeline.GetItemListInTrack(t_type, t_idx)
                    if t_items:
                        target_timeline.DeleteClips(t_items)
                        
    if not target_timeline:
        date_str = datetime.datetime.now().strftime("%Y_%m_%d")
        tl_name = f"{seq_padded}_{date_str}"
        print(f"Creating New Timeline: {tl_name} in 'timeline' bin.")
        target_timeline = media_pool.CreateEmptyTimeline(tl_name)
    
    if target_timeline:
        dvr_project.SetCurrentTimeline(target_timeline)
    
    print(f"Appending {len(video_clip_infos)} video clips to timeline...")
    appended_items = media_pool.AppendToTimeline(video_clip_infos)
    
    if use_img and use_lut and 'EXR_LUT' in globals() and EXR_LUT and appended_items:
        print(f"Applying OCIO Editorial LUT '{EXR_LUT}' to EXR clips...")
        try:
            dvr_project.RefreshLUTList()
            resolve.OpenPage("color")
            for item in appended_items:
                item.SetLUT(1, EXR_LUT)
            resolve.OpenPage("edit")
        except Exception as e:
            print(f"Warning: Failed to apply OCIO LUT: {e}")
            
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

win.On.BuildBtn.Clicked = OnBuild
win.On.CancelBtn.Clicked = OnCancel
win.On.FlowDialog.Close = OnCancel
win.On.UsePresetCheck.Clicked = OnPresetCheck

# ==========================================
# EXECUTE UI
# ==========================================
win.Show()
dispatcher.RunLoop()
win.Hide()
