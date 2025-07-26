from datetime import datetime
import json
import shutil
import sqlite3
import os 
import ctypes.wintypes
from pathlib import Path
from src.ai_tagger import get_batched_ai_tags
from src.db import delete_file_record # this is used to delete records from the database
import time
import threading

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

class ProgressTracker:
    def __init__(self, total_files, meter=None, log_callback=None):
        self.total_files = total_files
        self.processed_files = 0
        self.start_time = time.time()
        self.meter = meter
        self.log_callback = log_callback
        self.last_update_time = 0
        self.update_interval = 0.5  # Update every 500ms instead of every file
        
        if self.meter:
            self.meter.configure(amounttotal=total_files, amountused=0)
    
    def update(self, increment=1):
        self.processed_files += increment
        current_time = time.time()
        
        # Only update GUI every 500ms to reduce overhead
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            elapsed_time = current_time - self.start_time
            
            if self.meter:
                # Schedule meter update on main thread
                self.meter.after(0, lambda: self.meter.configure(amountused=self.processed_files))
            
            # Calculate ETA and speed only during updates
            if self.processed_files > 0 and elapsed_time > 0:
                speed = self.processed_files / elapsed_time
                remaining_files = self.total_files - self.processed_files
                eta_seconds = remaining_files / speed if speed > 0 else 0
                
                # Format ETA
                if eta_seconds < 60:
                    eta_str = f"{eta_seconds:.0f}s"
                elif eta_seconds < 3600:
                    eta_str = f"{eta_seconds/60:.1f}m"
                else:
                    eta_str = f"{eta_seconds/3600:.1f}h"
                
                # Update meter subtitle with progress info
                if self.meter:
                    progress_text = f"Progress: {self.processed_files}/{self.total_files} | Speed: {speed:.1f}/s | ETA: {eta_str}"
                    self.meter.after(0, lambda: self.meter.configure(subtext=progress_text))
    
    def finish(self):
        elapsed_time = time.time() - self.start_time
        if self.log_callback:
            self.log_callback(f"✅ Processing complete! Total time: {elapsed_time:.1f}s")
        if self.meter:
            self.meter.after(0, lambda: self.meter.configure(subtext="Complete!"))

def process_batch(file_paths, tag_map, log_callback, progress_tracker=None):
    # Process files in batches for better performance
    for file_path in file_paths:
        if file_path.is_dir():
            dest_folder = ORGANIZED / "Misc" / "Folders" / file_path.name
            try:
                dest_folder.mkdir(parents=True, exist_ok=True)
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
    
    # Update progress once per batch instead of per file
    if progress_tracker:
        progress_tracker.update(len(file_paths))

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


def start_processing_threaded(log_area, meter=None):
    """Threaded version of start_processing to prevent GUI freezing"""
    def processing_thread():
        try:
            start_processing(log_area, meter)
        except Exception as e:
            def log_error():
                log_area.insert("end", f"❌ Error during processing: {e}\n")
                log_area.see("end")
            # Schedule the GUI update on the main thread
            log_area.after(0, log_error)
    
    thread = threading.Thread(target=processing_thread, daemon=True)
    thread.start()
    return thread

def start_processing(log_area, meter=None):
    all_files = [f for f in DESKTOP.iterdir() if f.name != "Organized"]

    def log_callback(msg):
        def update_log():
            log_area.insert("end", f"{msg}\n")
            log_area.see("end")
        # Schedule GUI updates on the main thread
        log_area.after(0, update_log)
        print(msg)

    if not all_files:
        log_callback("⚠️ No files found on Desktop.")
        return

    # Initialize progress tracker
    progress_tracker = ProgressTracker(len(all_files), meter, log_callback)
    
    log_callback(f"🚀 Starting to process {len(all_files)} files...")

    for i in range(0, len(all_files), BATCH_SIZE):
        batch = all_files[i:i+BATCH_SIZE]
        file_names = [f.name for f in batch if not f.is_dir() and f.suffix.lower() != '.lnk']

        if file_names:  # Only call AI tagging if there are actual files to tag
            log_callback(f"🤖 Sending batch of {len(file_names)} files to OpenAI...")
            tag_map = get_batched_ai_tags(file_names)
            log_callback("✨ Tagging complete. Applying results...\n")
        else:
            tag_map = {}

        process_batch(batch, tag_map, log_callback, progress_tracker)
    
    progress_tracker.finish()


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

def undo_last_cleanup_threaded(log_callback=None, meter=None):
    """Threaded version of undo_last_cleanup"""
    def undo_thread():
        try:
            undo_last_cleanup(log_callback, meter)
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Error during undo: {e}")
    
    thread = threading.Thread(target=undo_thread, daemon=True)
    thread.start()
    return thread

def undo_last_cleanup(log_callback=None, meter=None):
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

    # Initialize progress tracker for undo
    if meter:
        progress_tracker = ProgressTracker(len(actions), meter, log_callback)
    else:
        progress_tracker = None

    # Process files in batches for better performance
    batch_size = 10  # Smaller batch for undo operations
    for i in range(0, len(actions), batch_size):
        batch = actions[i:i+batch_size]
        
        for entry in reversed(batch):
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
        
        # Update progress once per batch
        if progress_tracker:
            progress_tracker.update(len(batch))

    UNDO_LOG_PATH.unlink()
    if log_callback:
        log_callback("✅ Undo complete. Cleanup reversed.")
    
    if progress_tracker:
        progress_tracker.finish()