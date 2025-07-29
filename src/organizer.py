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

# get desktop path - cross-platform compatible
def get_desktop_path():
    """Get the desktop path for the current OS"""
    import platform
    system = platform.system()
    
    if system == "Windows":
        try:
            import ctypes.wintypes
            CSIDL_DESKTOP = 0
            SHGFP_TYPE_CURRENT = 0
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOP, None, SHGFP_TYPE_CURRENT, buf)
            return Path(buf.value)
        except:
            # Fallback for Windows
            user = os.getenv("USERNAME", "user")
            return Path(f"C:/Users/{user}/Desktop")
    else:
        # Linux/macOS/other Unix-like systems
        user = os.getenv("USER", "user")
        home = Path.home()
        desktop_path = home / "Desktop"
        # Create Desktop directory if it doesn't exist
        desktop_path.mkdir(exist_ok=True)
        return desktop_path

def get_organized_path():
    """Get the organized files path for the current OS"""
    import platform
    system = platform.system()
    user = os.getenv("USER", os.getenv("USERNAME", "user"))
    
    if system == "Windows":
        return Path(f"C:/Users/{user}/Organized")
    else:
        # Linux/macOS - use home directory
        home = Path.home()
        organized_path = home / "Organized"
        organized_path.mkdir(exist_ok=True)
        return organized_path

SKIP_TAGS = {"image", "video", "audio"}
BATCH_SIZE = 50

USER = os.getenv("USER", os.getenv("USERNAME", "user"))
DESKTOP = get_desktop_path()
ORGANIZED = get_organized_path()
DB_PATH = Path("file_index.db")

# Enhanced History Management Integration
HISTORY_LOG_PATH = Path("history_log.json")
LEGACY_UNDO_LOG_PATH = Path("undo_log.json")  # For backward compatibility

class EnhancedHistoryManager:
    """Enhanced history manager integrated with the organizer"""
    
    def __init__(self):
        self.history_path = HISTORY_LOG_PATH
        self.current_session_id = None
        self._migrate_legacy_log()
    
    def _migrate_legacy_log(self):
        """Migrate old undo_log.json to new history format"""
        if LEGACY_UNDO_LOG_PATH.exists() and not self.history_path.exists():
            try:
                with open(LEGACY_UNDO_LOG_PATH, "r", encoding="utf-8") as f:
                    legacy_actions = json.load(f)
                
                if legacy_actions:
                    # Create a legacy session
                    session = {
                        "id": 1,
                        "name": "Legacy Session (Migrated)",
                        "timestamp": datetime.now().isoformat(),
                        "actions": legacy_actions,
                        "status": "completed",
                        "migrated": True
                    }
                    
                    self.save_history([session])
                    # Keep legacy file for backup
                    LEGACY_UNDO_LOG_PATH.rename(LEGACY_UNDO_LOG_PATH.with_suffix('.json.backup'))
                    
            except Exception as e:
                print(f"Warning: Could not migrate legacy undo log: {e}")
    
    def start_new_session(self, session_name=None, log_callback=None):
        """Start a new organizing session"""
        if not session_name:
            session_name = f"Organize_{datetime.now().strftime('%m%d_%H%M')}"
        
        history = self.load_history()
        
        # Complete any active sessions first
        for session in history:
            if session.get("status") == "active":
                session["status"] = "completed"
                session["completed_at"] = datetime.now().isoformat()
        
        new_session = {
            "id": max([s.get("id", 0) for s in history], default=0) + 1,
            "name": session_name,
            "timestamp": datetime.now().isoformat(),
            "actions": [],
            "status": "active",
            "files_processed": 0,
            "files_total": 0
        }
        
        history.append(new_session)
        self.save_history(history)
        self.current_session_id = new_session["id"]
        
        if log_callback:
            log_callback(f"📝 Started new session: {session_name}")
        
        return new_session["id"]
    
    def add_action(self, original_path, new_path):
        """Add an action to the current session"""
        if not self.current_session_id:
            self.start_new_session()
        
        history = self.load_history()
        current_session = None
        
        for session in history:
            if session["id"] == self.current_session_id:
                current_session = session
                break
        
        if current_session:
            current_session["actions"].append({
                "original": str(original_path),
                "new": str(new_path),
                "timestamp": datetime.now().isoformat()
            })
            current_session["files_processed"] = len(current_session["actions"])
            self.save_history(history)
    
    def update_session_total(self, total_files):
        """Update the total files count for the current session"""
        if not self.current_session_id:
            return
        
        history = self.load_history()
        for session in history:
            if session["id"] == self.current_session_id:
                session["files_total"] = total_files
                break
        self.save_history(history)
    
    def complete_current_session(self, log_callback=None):
        """Complete the current session"""
        if not self.current_session_id:
            return
        
        history = self.load_history()
        for session in history:
            if session["id"] == self.current_session_id:
                session["status"] = "completed"
                session["completed_at"] = datetime.now().isoformat()
                if log_callback:
                    files_count = len(session.get("actions", []))
                    log_callback(f"✅ Session '{session['name']}' completed with {files_count} files processed")
                break
        
        self.save_history(history)
        self.current_session_id = None
    
    def load_history(self):
        """Load the history log"""
        if not self.history_path.exists():
            return []
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    
    def save_history(self, history):
        """Save the history log"""
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

# Global history manager instance
enhanced_history = EnhancedHistoryManager()

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
    """Process files in batches for better performance"""
    for file_path in file_paths:
        if file_path.is_dir():
            dest_folder = ORGANIZED / "Misc" / "Folders" / file_path.name
            try:
                dest_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(file_path), str(dest_folder))
                
                # Log to enhanced history
                enhanced_history.add_action(file_path, dest_folder / file_path.name)
                
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
            
            # Log to enhanced history instead of legacy system
            enhanced_history.add_action(file_path, new_path)
            
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
    """Regroup files by their tags"""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT original_name, new_path, tags FROM files")
        files_to_regroup = c.fetchall()
    
    if not files_to_regroup:
        return
    
    # Start a new session for regrouping
    session_id = enhanced_history.start_new_session("Regroup_by_Tags")
    enhanced_history.update_session_total(len([f for f in files_to_regroup if f[2]]))
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        for name, path, tags in files_to_regroup:
            if not tags:
                continue
            tag = tags.split(", ")[0]
            new_folder = ORGANIZED / "GroupedByTag" / tag
            new_folder.mkdir(parents=True, exist_ok=True)
            new_path = new_folder / Path(path).name
            try:
                if Path(path).exists():
                    # Log to history before moving
                    enhanced_history.add_action(Path(path), new_path)
                    shutil.move(path, new_path)
                    c.execute("UPDATE files SET new_path = ? WHERE original_name = ?", (str(new_path), name))
            except Exception as e:
                print(f"Error regrouping {name}: {e}")
        conn.commit()
    
    enhanced_history.complete_current_session()

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
    """Enhanced start processing with session management"""
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

    # Start a new organizing session
    session_name = f"Desktop_Cleanup_{datetime.now().strftime('%m%d_%H%M')}"
    session_id = enhanced_history.start_new_session(session_name, log_callback)
    enhanced_history.update_session_total(len(all_files))

    # Initialize progress tracker
    progress_tracker = ProgressTracker(len(all_files), meter, log_callback)
    
    log_callback(f"🚀 Starting to process {len(all_files)} files...")

    try:
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
        enhanced_history.complete_current_session(log_callback)
        
    except Exception as e:
        log_callback(f"❌ Error during processing: {e}")
        # Mark session as failed
        history = enhanced_history.load_history()
        for session in history:
            if session["id"] == session_id:
                session["status"] = "failed"
                session["error"] = str(e)
                session["failed_at"] = datetime.now().isoformat()
                break
        enhanced_history.save_history(history)

# Legacy compatibility functions
def log_undo_action(original_path, new_path):
    """Legacy function - now redirects to enhanced history"""
    enhanced_history.add_action(original_path, new_path)

def undo_last_cleanup_threaded(log_callback=None, meter=None):
    """Threaded version of undo_last_cleanup - now uses enhanced history"""
    def undo_thread():
        try:
            undo_last_cleanup(log_callback, meter)
        except Exception as e:
            if log_callback:
                log_callback(f"❌ Error during undo: {e}")
    
    thread = threading.Thread(target=undo_thread, daemon=True)
    thread.start()
    return thread

def undo_session_by_id(session_id, log_callback=None, meter=None):
    """Undo a specific session by ID"""
    history = enhanced_history.load_history()
    target_session = None
    
    for session in history:
        if session["id"] == session_id:
            target_session = session
            break
    
    if not target_session:
        if log_callback:
            log_callback(f"❌ Session {session_id} not found.")
        return False
    
    actions = target_session.get("actions", [])
    if not actions:
        if log_callback:
            log_callback(f"⚠️ No actions found in session '{target_session['name']}'.")
        return False
    
    # Initialize progress tracker
    if meter:
        progress_tracker = ProgressTracker(len(actions), meter, log_callback)
    else:
        progress_tracker = None
    
    if log_callback:
        log_callback(f"🔄 Undoing session: {target_session['name']} ({len(actions)} actions)")
    
    # Process undo in batches
    batch_size = 10
    success_count = 0
    
    for i in range(0, len(actions), batch_size):
        batch = actions[i:i+batch_size]
        
        for entry in reversed(batch):  # Undo in reverse order
            original = Path(entry["original"])
            moved = Path(entry["new"])
            try:
                if moved.exists():
                    original.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(moved), str(original))
                    # Remove from database
                    delete_file_record(original.name)
                    success_count += 1
                    if log_callback:
                        log_callback(f"↩️ Restored: {moved.name} → {original}")
                else:
                    if log_callback:
                        log_callback(f"⚠️ File not found: {moved}")
            except Exception as e:
                if log_callback:
                    log_callback(f"❌ Could not restore {moved.name}: {e}")
        
        # Update progress
        if progress_tracker:
            progress_tracker.update(len(batch))
    
    # Mark session as undone
    target_session["status"] = "undone"
    target_session["undone_at"] = datetime.now().isoformat()
    enhanced_history.save_history(history)
    
    if log_callback:
        log_callback(f"✅ Session undo complete. {success_count}/{len(actions)} files restored.")
    
    if progress_tracker:
        progress_tracker.finish()
    
    return True

def undo_last_cleanup(log_callback=None, meter=None):
    """Legacy undo function - now finds and undoes the most recent completed session"""
    history = enhanced_history.load_history()
    
    # Find the most recent completed session
    most_recent_session = None
    for session in reversed(history):
        if session.get("status") == "completed":
            most_recent_session = session
            break
    
    if not most_recent_session:
        if log_callback:
            log_callback("⚠️ No completed sessions found to undo.")
        return
    
    # Use the local undo function
    success = undo_session_by_id(
        most_recent_session["id"], 
        log_callback, 
        meter
    )
    
    if success and log_callback:
        log_callback(f"✅ Successfully undid session: {most_recent_session['name']}")

# Backward compatibility for old undo log
UNDO_LOG_PATH = LEGACY_UNDO_LOG_PATH