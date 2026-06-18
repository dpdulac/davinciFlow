import os
import sys
import json
import datetime
import urllib.request
import wave

# ==========================================
# FLOW AUTHENTICATION & CONFIG
# ==========================================
CONFIG_PATH = r"W:\jmji\_sandbox\dulacd\Script\Blender\davinciFlow_config.json"

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
    except Exception as e:
        print(f"Failed to load json config: {e}")

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
def get_sequences(project_name):
    print(f"Fetching sequences for project '{project_name}'...")
    try:
        sg = shotgun_api3.Shotgun(FLOW_URL, script_name=SCRIPT_NAME, api_key=SCRIPT_KEY)
        proj = sg.find_one("Project", [["name", "is", project_name]], ["id"])
        if not proj: return []
        filters = [
            ['project', 'is', proj],
            ['code', 'is_not', 'omit'],
            ['sg_status_list', 'is_not', 'omt'],
        ]
        seqs = sg.find("Sequence", filters, ["code"])
        seq_codes = [s['code'] for s in seqs if s.get('code')]
        seq_codes.sort()
        return seq_codes
    except Exception as e:
        print("Failed to fetch sequences:", e)
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
    ui.HGroup([
        ui.Label({"Text": "Project:"}),
        ui.ComboBox({"ID": "ProjectCombo", "Weight": 2})
    ]),
    ui.HGroup([
        ui.Label({"Text": "Sequence Number:"}),
        ui.ComboBox({"ID": "SeqCombo", "Weight": 2})
    ]),
    ui.HGroup([
        ui.Label({"Text": "Highest Task:"}),
        ui.ComboBox({"ID": "HighestTaskCombo", "Weight": 2})
    ]),
    ui.HGroup([
        ui.Label({"Text": "Lowest Task:"}),
        ui.ComboBox({"ID": "LowestTaskCombo", "Weight": 2})
    ]),
    ui.HGroup([
        ui.Label({"Text": "Use Image Sequences:"}),
        ui.CheckBox({"ID": "ImageSeqCheck", "Checked": False})
    ]),
    ui.HGroup([
        ui.Label({'Text': 'Use Flow Audio:'}),
        ui.CheckBox({'ID': 'UseAudio', 'Text': 'Import .wav files from Flow', 'Checked': False})
    ]),
    ui.HGroup([
        ui.Label({'Text': 'Timeline Options:'}),
        ui.CheckBox({'ID': 'UseLatestTimeline', 'Text': 'Update latest timeline (clears existing clips)', 'Checked': True})
    ]),
    ui.VGap(10),
    ui.HGroup({'Weight': 0, 'Spacing': 10}, [
        ui.Button({'ID': 'CancelBtn', 'Text': 'Cancel'}),
        ui.Button({'ID': 'BuildBtn', 'Text': 'Build Sequence'})
    ])
])

win = dispatcher.AddWindow({
    "ID": "FlowDialog",
    "Geometry": [400, 400, 500, 300],
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

# Set defaults for task ranges
if MASTER_TASKS:
    items["HighestTaskCombo"].CurrentIndex = 0
    items["LowestTaskCombo"].CurrentIndex = len(MASTER_TASKS) - 1

# ==========================================
# FETCH DATA
# ==========================================
def fetch_flow_data(project_name, sequence_name, highest_idx, lowest_idx, use_image_seq, use_audio):
    print(f"Connecting to Flow as '{SCRIPT_NAME}'...")
    try:
        sg = shotgun_api3.Shotgun(FLOW_URL, script_name=SCRIPT_NAME, api_key=SCRIPT_KEY)
    except Exception as e:
        print(f"Connection Failed: {e}")
        return None

    project = sg.find_one("Project", [["name", "is", project_name]], ["id", "name"])
    if not project:
        print(f"Project '{project_name}' not found.")
        return None

    # Fetch all shots in sequence to get timing and ID
    print(f"\nQuerying Shots for Sequence {sequence_name}...")
    shot_filters = [
        ['project', 'is', project],
        ['sg_sequence', 'name_is', sequence_name]
    ]
    shot_fields = ['id', 'code', 'sg_cut_in', 'sg_cut_out', 'sg_head_in']
    shots = sg.find('Shot', shot_filters, shot_fields)
    
    if not shots:
        print("No shots found.")
        return None
        
    shot_dict = {s['id']: s for s in shots}
    
    # Query Audio files dynamically only if requested
    audio_dict = {}
    if use_audio:
        print("Querying Sequence Audio...")
        audio_filters = [
            ['project', 'is', project],
            ['published_file_type.PublishedFileType.code', 'in', ['EditingSound', 'Sound']]
        ]
        audio_pubs = sg.find('PublishedFile', audio_filters, ['code', 'entity', 'path'])
        for p in audio_pubs:
            ent = p.get('entity')
            ent_name = ent.get('name') if ent else ''
            path = p.get('path', {}).get('local_path_windows')
            
            if path and sequence_name in ent_name: 
                # Fix Path mapping for the local machine (Paris W: / Montreal V:)
                audio_dict[ent_name] = resolve_path(path)
    
    valid_tasks = MASTER_TASKS[highest_idx:lowest_idx+1]
    
    # Query all versions for these shots in the valid tasks
    v_filters = [
        ['project', 'is', project],
        ['entity', 'in', shots],
        ['sg_task.Task.content', 'in', valid_tasks]
    ]
    v_fields = ['entity', 'code', 'sg_path_to_movie', 'sg_path_to_frames', 'created_at', 'sg_uploaded_movie_mp4', 'sg_task']
    versions = sg.find('Version', v_filters, v_fields)
    
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
                        media_dict[shot_id] = {
                            'shot_code': shot_code,
                            'task': task,
                            'path': path_to_use,
                            'audio_path': audio_path,
                            'is_web_proxy': is_web_proxy,
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
def OnBuild(ev):
    project_name = items["ProjectCombo"].CurrentText
    seq_str = items["SeqCombo"].CurrentText.strip()
    seq_padded = seq_str.zfill(4)
    highest_idx = int(items["HighestTaskCombo"].CurrentIndex)
    lowest_idx = int(items["LowestTaskCombo"].CurrentIndex)
    use_img = items["ImageSeqCheck"].Checked
    use_audio = items["UseAudio"].Checked
    use_latest_timeline = items["UseLatestTimeline"].Checked
    
    if highest_idx > lowest_idx:
        print("Error: Highest task must be above Lowest task in the hierarchy.")
        return
        
    dispatcher.ExitLoop()
    
    print(f"\n--- Starting Build for {project_name} Sequence {seq_padded} ---")
    # 1. Fetch
    media_data = fetch_flow_data(project_name, seq_padded, highest_idx, lowest_idx, use_img, use_audio)
    if not media_data:
        print("No media data gathered.")
        return
        
    seq_bin = get_or_create_bin(seq_padded)
    media_bin = get_or_create_sub_bin(seq_bin, "media")
    movies_bin = get_or_create_sub_bin(media_bin, "movies")
    audio_bin = get_or_create_sub_bin(media_bin, "audio")
    timeline_bin = get_or_create_sub_bin(seq_bin, "timeline")
    
    media_pool.SetCurrentFolder(media_bin)
    
    video_clip_infos = []
    audio_clip_infos = []
    
    sorted_shots = sorted(media_data.values(), key=lambda x: x['shot_code'])
    
    print("\n=== Resolving Media Paths ===")
    for data in sorted_shots:
        path = data['path']
        is_missing = (path == 'MISSING')
        is_web_proxy = data.get('is_web_proxy', False)
        
        if is_missing:
            path = get_missing_media_path()
            print(f"Processing {data['shot_code']} -> MISSING MEDIA. Using placeholder.")
        elif is_web_proxy:
            if not os.path.exists(PROXY_DOWNLOAD_PATH):
                os.makedirs(PROXY_DOWNLOAD_PATH, exist_ok=True)
                
            safe_name = f"{data['shot_code']}_{data['task']}_proxy.mp4"
            local_proxy_path = os.path.join(PROXY_DOWNLOAD_PATH, safe_name)
            
            print(f"Processing {data['shot_code']} ({data['task']}) -> Downloading Web Proxy...")
            if not os.path.exists(local_proxy_path):
                try:
                    urllib.request.urlretrieve(path, local_proxy_path)
                except Exception as e:
                    print(f"Failed to download proxy for {data['shot_code']}: {e}")
            
            path = local_proxy_path
        else:
            print(f"Processing {data['shot_code']} ({data['task']}) -> {path}")
        
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
                    clip_info["startFrame"] = 0
                    clip_info["endFrame"] = duration
                    print(f"  -> Applying Duration constraint: {duration} frames (0 to {duration})")
                
            video_clip_infos.append(clip_info)
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
    media_pool.AppendToTimeline(video_clip_infos)
    
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
    win.Hide()

def OnCancel(ev):
    dispatcher.ExitLoop()

win.On.BuildBtn.Clicked = OnBuild
win.On.CancelBtn.Clicked = OnCancel
win.On.FlowDialog.Close = OnCancel

# ==========================================
# EXECUTE UI
# ==========================================
win.Show()
dispatcher.RunLoop()
win.Hide()
