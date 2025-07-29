import os
import json
import threading
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import sqlite3

# Import from existing modules
from src.ai_tagger import get_batched_ai_tags
from src.index_files import start_indexing_threaded
from src.organizer import process_batch, get_category, ORGANIZED, enhanced_history, DESKTOP
from src.db import insert_into_db, DB_PATH

class DesktopFileHandler(FileSystemEventHandler):
    """Handler for desktop file events"""

    def __init__(self, watcher_instance):
        self.watcher = watcher_instance
        super().__init__()

    def on_created(self, event):
        """Handle new file creation"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Skip if it's a temporary file or system file
        if file_path.name.startswith('.') or file_path.suffix.lower() in ['.tmp', '.temp', '.part']:
            return

        # Small delay to ensure file is fully written
        time.sleep(0.5)

        if file_path.exists():
            self.watcher.process_new_file(file_path)

class DesktopWatcher:
    """Real-time desktop file monitoring system"""

    def __init__(self, log_callback=None, status_callback=None):
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.observer = None
        self.is_running = False
        self.settings = self.load_settings()

        # Desktop path
        self.desktop_path = DESKTOP

    def get_desktop_path(self):
        """Get the desktop path based on OS"""
        if os.name == 'nt':  # Windows
            return Path.home() / "Desktop"
        else:  # Linux/Mac
            return Path.home() / "Desktop"

    def load_settings(self):
        """Load watcher settings from config"""
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("watcher_settings", {
                    "live_monitor": False,
                    "auto_ai_tagging": True,
                    "organize_to": "Desktop Folder"  # Options: "Desktop Folder", "Organized Folder", "Do Not Move"
                })
        except:
            return {
                "live_monitor": False,
                "auto_ai_tagging": True,
                "organize_to": "Desktop Folder"
            }

    def save_settings(self):
        """Save watcher settings to config"""
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        except:
            config = {}

        config["watcher_settings"] = self.settings

        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def start_monitoring(self):
        """Start the desktop file monitoring"""
        if self.is_running:
            return

        try:
            if not self.desktop_path.exists():
                if self.log_callback:
                    self.log_callback(f"❌ Desktop path not found: {self.desktop_path}")
                return

            self.observer = Observer()
            self.handler = DesktopFileHandler(self)
            self.observer.schedule(self.handler, str(self.desktop_path), recursive=False)
            self.observer.start()
            self.is_running = True

            if self.log_callback:
                self.log_callback(f"👀 Live monitoring started for: {self.desktop_path}")

            if self.status_callback:
                self.status_callback("🔴 Live Monitor: ON")

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Failed to start monitoring: {e}")

    def stop_monitoring(self):
        """Stop the desktop file monitoring"""
        if not self.is_running:
            return

        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)
                self.observer = None

            self.handler = None
            self.is_running = False

            if self.log_callback:
                self.log_callback("⏹️ Live monitoring stopped")

            if self.status_callback:
                self.status_callback("⚫ Live Monitor: OFF")

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Error stopping monitoring: {e}")

    def process_new_file(self, file_path):
        """Process a newly detected file"""
        try:
            # Always index the file first
            self.index_file(file_path)

            tags = ""
            # Get AI tags if enabled
            if self.settings.get("auto_ai_tagging", True):
                tags = self.get_ai_tags_for_file(file_path)

            # Move file based on settings
            moved_to = self.move_file_based_on_setting(file_path, tags)

            # Create status message
            status_msg = f"📦 Indexed \"{file_path.name}\""
            if tags:
                status_msg += f" → Tagged ✔"
            else:
                status_msg += f" → No tags"

            if moved_to:
                status_msg += f" → Moved to {moved_to}"
            else:
                status_msg += f" → Left in place"

            if self.log_callback:
                self.log_callback(status_msg)

            if self.status_callback:
                self.status_callback(status_msg)

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Error processing {file_path.name}: {e}")

    def index_file(self, file_path):
        """Index a single file in the database"""
        try:
            # Insert into database directly (simpler than threading for single files)
            file_type = file_path.suffix or "unknown"
            insert_into_db(file_path.name, str(file_path), file_type, "")

        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Error indexing {file_path.name}: {e}")

    def get_ai_tags_for_file(self, file_path):
        """Get AI tags for a single file"""
        try:
            tag_map = get_batched_ai_tags([file_path.name])
            return tag_map.get(file_path.name.strip().lower(), "")
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Error getting AI tags for {file_path.name}: {e}")
            return ""

    def move_file_based_on_setting(self, file_path, tags=""):
        """Move file based on the organize_to setting"""
        organize_to = self.settings.get("organize_to", "Desktop Folder")

        if organize_to == "Do Not Move":
            # Update tags in database but don't move
            if tags:
                self.update_file_tags(file_path.name, tags)
            return None

        elif organize_to == "Desktop Folder":
            # Move to Desktop/TidyDesk folder
            tidy_folder = self.desktop_path / "TidyDesk"
            tidy_folder.mkdir(exist_ok=True)

            new_path = tidy_folder / file_path.name
            try:
                import shutil
                shutil.move(str(file_path), str(new_path))

                # Update database with new path and tags
                self.update_file_record(file_path.name, str(new_path), tags)

                # Log to history
                enhanced_history.add_action(file_path, new_path)

                return "Desktop Folder"
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"❌ Error moving to Desktop Folder: {e}")
                return None

        elif organize_to == "Organized Folder":
            # Use existing organization logic
            try:
                from src.organizer import get_category

                category = get_category(file_path.suffix)
                if category:
                    dest_folder = ORGANIZED / category
                else:
                    dest_folder = ORGANIZED / "Misc" / "Other"

                dest_folder.mkdir(parents=True, exist_ok=True)
                new_path = dest_folder / file_path.name

                import shutil
                shutil.move(str(file_path), str(new_path))

                # Update database with new path and tags
                self.update_file_record(file_path.name, str(new_path), tags)

                # Log to history
                enhanced_history.add_action(file_path, new_path)

                return "Organized Folder"

            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"❌ Error moving to Organized Folder: {e}")
                return None

    def update_file_record(self, filename, new_path, tags):
        """Update file record in database"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE files SET new_path = ?, tags = ? WHERE original_name = ?",
                    (new_path, tags, filename)
                )
                conn.commit()
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Error updating database: {e}")

    def update_file_tags(self, filename, tags):
        """Update only tags in database"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE files SET tags = ? WHERE original_name = ?",
                    (tags, filename)
                )
                conn.commit()
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"❌ Error updating tags: {e}")

    def update_setting(self, key, value):
        """Update a specific setting"""
        self.settings[key] = value
        self.save_settings()

    def get_setting(self, key, default=None):
        """Get a specific setting"""
        return self.settings.get(key, default)