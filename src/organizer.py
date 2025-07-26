from datetime import datetime
import json
import shutil
import sqlite3
import os 
import ctypes.wintypes
from pathlib import Path
from src.ai_tagger import get_batched_ai_tags
from src.db import delete_file_record # this is used to delete records from the database

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

ALLOWED_EXTENSIONS = CONFIG["ALLOWED_EXTENSIONS"]


# get desktop path 
def get_windows_desktop_path():
    CSIDL_DESKTOP = 0  # Windows Desktop constant
    SHGFP_TYPE_CURRENT = 0
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOP, None, SHGFP_TYPE_CURRENT, buf)
    return Path(buf.value)

SKIP_TAGS = {"image", "video", "audio"}
BATCH_SIZE = 50

USER = os.getlogin()
DESKTOP = get_windows_desktop_path()
ORGANIZED = Path(f"C:/Users/{USER}/Organized")
DB_PATH = Path("file_index.db")

def get_category(extension):
    for category, ext_list in ALLOWED_EXTENSIONS.items():
        if extension.lower() in ext_list:
            return category
    return None

def process_batch(file_paths, tag_map, log_callback):
    for file_path in file_paths:
        if file_path.is_dir():
            dest_folder = ORGANIZED / "Misc" / "Folders" / file_path.name
            try:
                shutil.move(str(file_path), str(dest_folder))
                log_undo_action(file_path, dest_folder)
                from src.db import insert_into_db
                insert_into_db(file_path.name, str(dest_folder), "folder", "")
                log_callback(f"📁 Folder moved: {file_path.name} → Misc/Folders/")
            except Exception as e:
                log_callback(f"❌ Error moving folder {file_path.name}: {e}")
            continue

        if file_path.suffix.lower() == '.lnk':
            log_callback(f"⏭️ Skipped shortcut: {file_path.name}")
            continue

        category = get_category(file_path.suffix)
        if category:
            dest_folder = ORGANIZED / category
        else:
            dest_folder = ORGANIZED / "Misc" / "Other"

        dest_folder.mkdir(parents=True, exist_ok=True)
        new_path = dest_folder / file_path.name

        try:
            shutil.move(str(file_path), str(new_path))
            log_undo_action(file_path, new_path)
            tags = tag_map.get(file_path.name.strip().lower(), "")
            from src.db import insert_into_db
            insert_into_db(file_path.name, str(new_path), file_path.suffix or "unknown", tags)
            log_callback(f"📄 Moved: {file_path.name} → {dest_folder.name} | Tags: {tags}")
        except Exception as e:
            log_callback(f"❌ Error moving {file_path.name}: {e}")

def regroup_by_tags():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT original_name, new_path, tags FROM files")
        for name, path, tags in c.fetchall():
            if not tags:
                continue
            tag = tags.split(", ")[0]
            new_folder = ORGANIZED / "GroupedByTag" / tag
            new_folder.mkdir(parents=True, exist_ok=True)
            new_path = new_folder / Path(path).name
            try:
                shutil.move(path, new_path)
                c.execute("UPDATE files SET new_path = ? WHERE original_name = ?", (str(new_path), name))
            except Exception as e:
                print(f"Error regrouping {name}: {e}")
        conn.commit()


def start_processing(log_area):
    all_files = [f for f in DESKTOP.iterdir() if f.name != "Organized"]

    def log_callback(msg):
        log_area.insert("end", f"{msg}\n")
        log_area.see("end")
        print(msg)

    if not all_files:
        log_callback("⚠️ No files found on Desktop.")
        return

    for i in range(0, len(all_files), BATCH_SIZE):
        batch = all_files[i:i+BATCH_SIZE]
        file_names = [f.name for f in batch if not f.is_dir() and f.suffix.lower() != '.lnk']

        log_callback(f"Sending batch of {len(file_names)} files to OpenAI...")
        tag_map = get_batched_ai_tags(file_names)
        log_callback("Tagging complete. Applying results...\n")

        process_batch(batch, tag_map, log_callback)


UNDO_LOG_PATH = Path("undo_log.json")

def log_undo_action(original_path, new_path):
    log = []
    if UNDO_LOG_PATH.exists():
        try:
            with open(UNDO_LOG_PATH, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []

    log.append({"original": str(original_path), "new": str(new_path)})
    with open(UNDO_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)

def undo_last_cleanup(log_callback=None):
    if not UNDO_LOG_PATH.exists():
        if log_callback:
            log_callback("⚠️ No undo log found.")
        return

    try:
        with open(UNDO_LOG_PATH, "r", encoding="utf-8") as f:
            actions = json.load(f)
    except Exception as e:
        if log_callback:
            log_callback(f"❌ Error reading undo log: {e}")
        return

    for entry in reversed(actions):
        original = Path(entry["original"])
        moved = Path(entry["new"])
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(moved), str(original))
            delete_file_record(original.name)
            if log_callback:
                log_callback(f"↩️ Restored: {moved.name} → {original}")
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Could not restore {moved.name}: {e}")

    UNDO_LOG_PATH.unlink()
    if log_callback:
        log_callback("✅ Undo complete. Cleanup reversed.")
