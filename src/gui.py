import os
import shutil
import sqlite3
import csv
import json
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, Toplevel, END, WORD, BOTH, LEFT, X, RIGHT, Y, messagebox
from PIL import Image, ImageTk
import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.widgets import Meter
from ttkbootstrap.constants import INFO, SUCCESS, PRIMARY, WARNING, SECONDARY, DANGER, LIGHT

from src.organizer import start_processing_threaded, regroup_by_tags, undo_last_cleanup_threaded, DB_PATH
from src.db import update_tags_in_db
from src.ai_tagger import get_batched_ai_tags, BATCH_SIZE, SKIP_TAGS
from src.ai_tagger import set_ai_enabled
from src.search_window import open_search_window
from src.index_files import start_indexing_threaded, get_index_statistics, clear_index
from src.theme_manager import theme_manager
from src.desktop_watcher import DesktopWatcher
from src.time_machine_gui import show_time_machine_window
from src.file_preview import show_file_preview, preview_file_dialog
import multiprocessing

# Enhanced History Management
HISTORY_LOG_PATH = Path("history_log.json")

class UndoHistoryManager:
    def __init__(self):
        self.history_path = HISTORY_LOG_PATH

    def create_new_session(self, session_name=None):
        """Create a new undo session"""
        if not session_name:
            session_name = f"Session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        history = self.load_history()
        new_session = {
            "id": len(history) + 1,
            "name": session_name,
            "timestamp": datetime.now().isoformat(),
            "actions": [],
            "status": "active"
        }

        history.append(new_session)
        self.save_history(history)
        return new_session["id"]

    def add_action_to_current_session(self, original_path, new_path):
        """Add an action to the most recent active session"""
        history = self.load_history()
        if not history:
            session_id = self.create_new_session()
            history = self.load_history()

        # Find the most recent active session
        current_session = None
        for session in reversed(history):
            if session.get("status") == "active":
                current_session = session
                break

        if not current_session:
            session_id = self.create_new_session()
            history = self.load_history()
            current_session = history[-1]

        current_session["actions"].append({
            "original": str(original_path),
            "new": str(new_path),
            "timestamp": datetime.now().isoformat()
        })

        self.save_history(history)

    def complete_current_session(self):
        """Mark the current session as completed"""
        history = self.load_history()
        for session in reversed(history):
            if session.get("status") == "active":
                session["status"] = "completed"
                session["completed_at"] = datetime.now().isoformat()
                break
        self.save_history(history)

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

    def get_session_list(self):
        """Get a list of all sessions for display"""
        history = self.load_history()
        session_list = []
        for session in reversed(history):  # Most recent first
            action_count = len(session.get("actions", []))
            timestamp = datetime.fromisoformat(session["timestamp"]).strftime("%Y-%m-%d %H:%M")
            status_emoji = "🔄" if session.get("status") == "active" else "✅"
            display_name = f"{status_emoji} {session['name']} ({action_count} files) - {timestamp}"
            session_list.append((session["id"], display_name, session))
        return session_list

    def undo_session(self, session_id, log_callback=None, meter=None):
        """Undo a specific session - delegates to organizer module"""
        from src.organizer import undo_session_by_id
        return undo_session_by_id(session_id, log_callback, meter)

# Global history manager
history_manager = UndoHistoryManager()

# Global variables for sharing between tabs
global_log_area = None
global_meter = None
global_desktop_watcher = None
global_status_label = None

def retag_missing_entries_threaded(log_callback, meter):
    """Threaded version of retag_missing_entries"""
    import threading

    def retag_thread():
        try:
            retag_missing_entries(log_callback, meter)
        except Exception as e:
            log_callback(f"❌ Error during retagging: {e}")

    thread = threading.Thread(target=retag_thread, daemon=True)
    thread.start()
    return thread

def retag_missing_entries(log_callback, meter):
    import sqlite3
    import time
    from src.db import update_tags_in_db
    from src.ai_tagger import get_batched_ai_tags, BATCH_SIZE, SKIP_TAGS
    from src.organizer import DB_PATH, ProgressTracker

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT original_name, new_path, tags FROM files")
        rows = c.fetchall()

    missing = [row for row in rows if not row[2] or not set(row[2].split(", ")).isdisjoint(SKIP_TAGS) == False]
    if not missing:
        log_callback("✅ No files need retagging.")
        return

    # Initialize progress tracker
    progress_tracker = ProgressTracker(len(missing), meter, log_callback)
    log_callback(f"🔄 Starting to retag {len(missing)} files...")

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i:i+BATCH_SIZE]
        filenames = [row[0] for row in batch]

        log_callback(f"🤖 Processing batch {i//BATCH_SIZE + 1}...")
        tag_map = get_batched_ai_tags(filenames)

        # Process the entire batch, then update progress once
        for name in filenames:
            tags = tag_map.get(name.strip().lower(), "")
            if tags:
                update_tags_in_db(name, tags)
                log_callback(f"🔁 Retagged: {name} | Tags: {tags}")
            else:
                log_callback(f"⚠️ No tags found for: {name}")

        # Update progress once per batch instead of per file
        progress_tracker.update(len(filenames))

    progress_tracker.finish()
    log_callback("✅ Retagging complete.")

# Main GUI Functions
def create_main_content(parent):
    """Create the main content area with horizontal layout"""

    # Main container
    main_container = ttk.Frame(parent)
    main_container.pack(fill=BOTH, expand=True, padx=10, pady=5)

    # Top section - Main actions and progress (horizontal layout)
    top_section = ttk.Frame(main_container)
    top_section.pack(fill=X, pady=(0, 5))

    # Left: Primary actions
    actions_frame = ttk.LabelFrame(top_section, text="🚀 Primary Actions", padding=10)
    actions_frame.pack(side=LEFT, fill=Y, padx=(0, 5))

    # Create buttons in a grid for compact layout
    btn_frame = ttk.Frame(actions_frame)
    btn_frame.pack()

    ttk.Button(
        btn_frame, 
        text="🚀 Organize Desktop", 
        bootstyle=SUCCESS,
        width=18,
        command=lambda: start_processing_threaded(global_log_area, global_meter)
    ).grid(row=0, column=0, padx=2, pady=2)

    ttk.Button(
        btn_frame, 
        text="🏷️ Group by Tags", 
        bootstyle=PRIMARY,
        width=18,
        command=regroup_by_tags
    ).grid(row=0, column=1, padx=2, pady=2)

    ttk.Button(
        btn_frame, 
        text="📇 Index Files", 
        bootstyle=INFO,
        width=18,
        command=lambda: start_indexing_threaded(
            lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None,
            global_meter
        )
    ).grid(row=1, column=0, padx=2, pady=2)

    ttk.Button(
        btn_frame, 
        text="↩️ Undo Last", 
        bootstyle=WARNING,
        width=18,
        command=lambda: undo_last_cleanup_threaded(
            lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None,
            global_meter
        )
    ).grid(row=1, column=1, padx=2, pady=2)

    # Center: Progress and status
    progress_frame = ttk.LabelFrame(top_section, text="📊 Progress", padding=10)
    progress_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=5)

    meter = Meter(
        progress_frame, 
        bootstyle=INFO, 
        subtext="Ready", 
        textright="files", 
        amounttotal=100,
        amountused=0,
        stripethickness=3,
        showtext=True
    )
    meter.pack(fill=X, pady=5)

    # Right: Live monitoring and tools
    right_section = ttk.Frame(top_section)
    right_section.pack(side=RIGHT, fill=Y, padx=(5, 0))

    # Live monitoring controls
    monitor_frame = ttk.LabelFrame(right_section, text="👀 Live Monitor", padding=8)
    monitor_frame.pack(fill=X, pady=(0, 5))

    # Initialize desktop watcher
    global global_desktop_watcher

    def update_monitor_status(message):
        """Update the status label for live monitoring"""
        if global_status_label:
            global_status_label.config(text=message)

    global_desktop_watcher = DesktopWatcher(
        log_callback=lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None,
        status_callback=update_monitor_status
    )

    # Monitor toggle
    monitor_var = ttk.BooleanVar(value=global_desktop_watcher.get_setting("live_monitor", False))

    def toggle_monitor():
        enabled = monitor_var.get()
        global_desktop_watcher.update_setting("live_monitor", enabled)

        if enabled:
            global_desktop_watcher.start_monitoring()
        else:
            global_desktop_watcher.stop_monitoring()

    ttk.Checkbutton(
        monitor_frame,
        text="Live Monitor",
        variable=monitor_var,
        command=toggle_monitor
    ).pack(anchor="w")

    # AI tagging toggle
    ai_tag_var = ttk.BooleanVar(value=global_desktop_watcher.get_setting("auto_ai_tagging", True))

    def toggle_ai_tagging():
        enabled = ai_tag_var.get()
        global_desktop_watcher.update_setting("auto_ai_tagging", enabled)

        if global_log_area:
            status = "enabled" if enabled else "disabled"
            global_log_area.insert(END, f"🤖 Auto AI Tagging {status}\n")
            global_log_area.see(END)

    ttk.Checkbutton(
        monitor_frame,
        text="Auto AI Tagging",
        variable=ai_tag_var,
        command=toggle_ai_tagging
    ).pack(anchor="w")

    # Organize new files dropdown
    organize_frame = ttk.Frame(monitor_frame)
    organize_frame.pack(fill=X, pady=2)

    ttk.Label(organize_frame, text="Organize To:", font=("Segoe UI", 8)).pack(anchor="w")

    organize_options = ["Desktop Folder", "Organized Folder", "Do Not Move"]
    organize_var = ttk.StringVar(value=global_desktop_watcher.get_setting("organize_to", "Desktop Folder"))

    def on_organize_change(event=None):
        selected = organize_var.get()
        global_desktop_watcher.update_setting("organize_to", selected)

        if global_log_area:
            global_log_area.insert(END, f"📁 Organize new files to: {selected}\n")
            global_log_area.see(END)

    organize_combo = ttk.Combobox(
        organize_frame,
        textvariable=organize_var,
        values=organize_options,
        state="readonly",
        width=15,
        font=("Segoe UI", 8)
    )
    organize_combo.pack(fill=X)
    organize_combo.bind('<<ComboboxSelected>>', on_organize_change)

    # Quick tools
    tools_frame = ttk.LabelFrame(right_section, text="🛠️ Tools", padding=8)
    tools_frame.pack(fill=X)

    tools_btn_frame = ttk.Frame(tools_frame)
    tools_btn_frame.pack(fill=X)

    # Configure grid weights for better spacing
    tools_btn_frame.grid_columnconfigure(0, weight=1)
    tools_btn_frame.grid_columnconfigure(1, weight=1)

    ttk.Button(
        tools_btn_frame, 
        text="🔍 Search", 
        bootstyle=SECONDARY,
        width=17,
        command=open_search_window
    ).grid(row=0, column=0, padx=2, pady=2, sticky="ew")

    ttk.Button(
        tools_btn_frame, 
        text="📊 Export CSV", 
        bootstyle=SECONDARY,
        width=17,
        command=export_to_csv
    ).grid(row=0, column=1, padx=2, pady=2, sticky="ew")

    ttk.Button(
        tools_btn_frame, 
        text="👁️ Preview", 
        bootstyle=LIGHT,
        width=17,
        command=preview_file
    ).grid(row=1, column=0, padx=2, pady=2, sticky="ew")

    ttk.Button(
        tools_btn_frame, 
        text="🕰️ Time Machine", 
        bootstyle=INFO,
        width=18,
        command=lambda: show_time_machine_window(tools_btn_frame.winfo_toplevel())
    ).grid(row=1, column=1, padx=2, pady=2, sticky="ew")

    ttk.Button(
        tools_btn_frame, 
        text="📊 Index Stats", 
        bootstyle=SECONDARY,
        width=17,
        command=show_index_stats
    ).grid(row=2, column=0, columnspan=2, padx=2, pady=2, sticky="ew")

    # Middle section - AI and Analytics in tabs (much more compact)
    middle_section = ttk.Frame(main_container)
    middle_section.pack(fill=BOTH, expand=True, pady=5)

    # Create compact notebook
    compact_notebook = ttk.Notebook(middle_section)
    compact_notebook.pack(fill=BOTH, expand=True)

    # AI Tab (compact)
    ai_tab = create_compact_ai_tab(compact_notebook)
    compact_notebook.add(ai_tab, text="🤖 AI")

    # Analytics Tab (compact)
    analytics_tab = create_compact_analytics_tab(compact_notebook)
    compact_notebook.add(analytics_tab, text="📊 Analytics")

    # History Tab (compact)
    history_tab = create_compact_history_tab(compact_notebook)
    compact_notebook.add(history_tab, text="📜 History")

    # Settings Tab (compact)
    settings_tab = create_compact_settings_tab(compact_notebook)
    compact_notebook.add(settings_tab, text="⚙️ Settings")

    # Bottom section - Log area
    log_frame = ttk.LabelFrame(main_container, text="📋 Activity Log", padding=8)
    log_frame.pack(fill=BOTH, expand=True, pady=(5, 0))

    log_area = ScrolledText(log_frame, height=12, font=("Consolas", 9))
    log_area.pack(fill=BOTH, expand=True)

    # Set global variables
    global global_log_area, global_meter
    global_log_area = log_area
    global_meter = meter

    # Auto-start monitoring if enabled
    if monitor_var.get():
        global_desktop_watcher.start_monitoring()

    return main_container

def create_compact_ai_tab(parent):
    """Create compact AI tagging tab"""
    tab_frame = ttk.Frame(parent)

    # Horizontal layout for AI controls
    ai_container = ttk.Frame(tab_frame)
    ai_container.pack(fill=BOTH, expand=True, padx=10, pady=5)

    # Left: AI Settings
    settings_frame = ttk.LabelFrame(ai_container, text="⚙️ AI Settings", padding=8)
    settings_frame.pack(side=LEFT, fill=Y, padx=(0, 5))

    ai_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        settings_frame, 
        text="🤖 Enable AI Tagging", 
        variable=ai_var,
        command=lambda: set_ai_enabled(ai_var.get())
    ).pack(anchor="w", pady=2)

    # Batch size
    batch_frame = ttk.Frame(settings_frame)
    batch_frame.pack(fill=X, pady=3)
    ttk.Label(batch_frame, text="Batch:").pack(side=LEFT)
    batch_var = ttk.IntVar(value=BATCH_SIZE)
    ttk.Spinbox(batch_frame, from_=1, to=100, width=8, textvariable=batch_var).pack(side=LEFT, padx=5)

    # Center: Actions
    actions_frame = ttk.LabelFrame(ai_container, text="🔄 AI Actions", padding=8)
    actions_frame.pack(side=LEFT, fill=Y, padx=5)

    ttk.Button(
        actions_frame, 
        text="🔄 Retag Missing", 
        bootstyle=INFO,
        width=15,
        command=lambda: retag_missing_entries_threaded(
            lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None, 
            global_meter
        )
    ).pack(pady=3)

    # Right: Skip tags
    skip_frame = ttk.LabelFrame(ai_container, text="🚫 Skip Tags", padding=8)
    skip_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(5, 0))

    skip_text = ScrolledText(skip_frame, height=6, font=("Consolas", 8))
    skip_text.pack(fill=BOTH, expand=True)
    skip_text.insert(END, ", ".join(SKIP_TAGS))

    return tab_frame

def create_compact_analytics_tab(parent):
    """Create compact analytics tab"""
    tab_frame = ttk.Frame(parent)

    analytics_container = ttk.Frame(tab_frame)
    analytics_container.pack(fill=BOTH, expand=True, padx=10, pady=5)

    # Left: File stats
    stats_frame = ttk.LabelFrame(analytics_container, text="📁 File Stats", padding=8)
    stats_frame.pack(side=LEFT, fill=Y, padx=(0, 5))

    def get_file_stats():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM files")
                total_files = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM files WHERE tags IS NOT NULL AND tags != ''")
                tagged_files = c.fetchone()[0]
                return total_files, tagged_files
        except:
            return 0, 0

    total_files, tagged_files = get_file_stats()

    stats_text = f"""📊 Total: {total_files}
🏷️ Tagged: {tagged_files}
📝 Untagged: {total_files - tagged_files}
📈 Coverage: {(tagged_files/total_files*100) if total_files > 0 else 0:.1f}%"""

    ttk.Label(stats_frame, text=stats_text, font=("Consolas", 9)).pack(anchor="w")

    # Center: Session stats
    session_frame = ttk.LabelFrame(analytics_container, text="⏱️ Sessions", padding=8)
    session_frame.pack(side=LEFT, fill=Y, padx=5)

    def get_session_stats():
        sessions = history_manager.get_session_list()
        total_sessions = len(sessions)
        completed_sessions = sum(1 for _, _, data in sessions if data.get("status") == "completed")
        total_actions = sum(len(data.get("actions", [])) for _, _, data in sessions)
        return total_sessions, completed_sessions, total_actions

    total_sessions, completed_sessions, total_actions = get_session_stats()

    session_stats = f"""🔄 Total: {total_sessions}
✅ Completed: {completed_sessions}
📁 Operations: {total_actions}"""

    ttk.Label(session_frame, text=session_stats, font=("Consolas", 9)).pack(anchor="w")

    # Right: Recent activity
    activity_frame = ttk.LabelFrame(analytics_container, text="📈 Recent Activity", padding=8)
    activity_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(5, 0))

    activity_text = ScrolledText(activity_frame, height=6, font=("Consolas", 8))
    activity_text.pack(fill=BOTH, expand=True)

    sessions = history_manager.get_session_list()
    if sessions:
        for session_id, display_name, session_data in sessions[:3]:  # Show last 3
            timestamp = datetime.fromisoformat(session_data["timestamp"]).strftime("%m/%d %H:%M")
            file_count = len(session_data.get("actions", []))
            activity_text.insert(END, f"{timestamp} | {file_count} files\n")
    else:
        activity_text.insert(END, "No activity yet...")

    return tab_frame

def create_compact_history_tab(parent):
    """Create compact history tab"""
    tab_frame = ttk.Frame(parent)

    history_container = ttk.Frame(tab_frame)
    history_container.pack(fill=BOTH, expand=True, padx=10, pady=5)

    # Left: Session list
    list_frame = ttk.LabelFrame(history_container, text="📜 Sessions", padding=8)
    list_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 5))

    # Compact treeview
    columns = ("Status", "Name", "Files", "Date")
    tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=6)

    tree.heading("Status", text="📊")
    tree.heading("Name", text="Session")
    tree.heading("Files", text="Files")
    tree.heading("Date", text="Date")

    tree.column("Status", width=40, anchor="center")
    tree.column("Name", width=150)
    tree.column("Files", width=50, anchor="center")
    tree.column("Date", width=100)

    tree.pack(fill=BOTH, expand=True)

    # Right: Actions
    actions_frame = ttk.LabelFrame(history_container, text="🔧 Actions", padding=8)
    actions_frame.pack(side=RIGHT, fill=Y, padx=(5, 0))

    def undo_selected():
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a session.")
            return
        messagebox.showinfo("Undo", "Undo functionality will be implemented!")

    ttk.Button(actions_frame, text="↩️ Undo Selected", bootstyle=WARNING, width=15, command=undo_selected).pack(pady=2)
    ttk.Button(actions_frame, text="🔄 Refresh", bootstyle=INFO, width=15).pack(pady=2)
    ttk.Button(actions_frame, text="🗑️ Clear All", bootstyle=DANGER, width=15).pack(pady=2)

    # Populate sessions
    sessions = history_manager.get_session_list()
    for session_id, display_name, session_data in sessions[:10]:  # Show last 10
        status = "✅" if session_data.get("status") == "completed" else "🔄"
        file_count = len(session_data.get("actions", []))
        date_str = datetime.fromisoformat(session_data["timestamp"]).strftime("%m/%d %H:%M")

        tree.insert("", "end", values=(status, session_data["name"][:20], file_count, date_str))

    return tab_frame

def create_compact_settings_tab(parent):
    """Create compact settings tab"""
    tab_frame = ttk.Frame(parent)

    settings_container = ttk.Frame(tab_frame)
    settings_container.pack(fill=BOTH, expand=True, padx=10, pady=5)

    # Left: Environment
    env_frame = ttk.LabelFrame(settings_container, text="🌍 Environment", padding=8)
    env_frame.pack(side=LEFT, fill=Y, padx=(0, 5))

    # API Key
    api_frame = ttk.Frame(env_frame)
    api_frame.pack(fill=X, pady=2)
    ttk.Label(api_frame, text="API Key:", width=10).pack(side=LEFT)
    api_key_var = ttk.StringVar()
    api_entry = ttk.Entry(api_frame, show="*", width=20, textvariable=api_key_var)
    api_entry.pack(side=LEFT, padx=2)

    # DB Path (Read-only)
    db_frame = ttk.Frame(env_frame)
    db_frame.pack(fill=X, pady=2)
    ttk.Label(db_frame, text="DB Path:", width=10).pack(side=LEFT)
    db_entry = ttk.Entry(db_frame, width=20, state="readonly")
    db_entry.pack(side=LEFT, padx=2)
    # Insert the value before making it readonly
    db_entry.config(state="normal")
    db_entry.insert(0, str(DB_PATH))
    db_entry.config(state="readonly")

    # Environment action buttons
    env_buttons_frame = ttk.Frame(env_frame)
    env_buttons_frame.pack(fill=X, pady=5)

    # Add status label for environment feedback
    env_status_frame = ttk.Frame(env_frame)
    env_status_frame.pack(fill=X, pady=2)
    env_status_label = ttk.Label(env_status_frame, text="", font=("Segoe UI", 8))
    env_status_label.pack(side=LEFT)

    def update_env_status(message, color="info"):
        """Update environment status label"""
        env_status_label.config(text=message)
        if global_log_area:
            global_log_area.insert(END, f"{message}\n")
            global_log_area.see(END)

    def save_environment():
        """Save API key to .env file"""
        api_key = api_key_var.get().strip()
        if not api_key:
            update_env_status("⚠️ Please enter an API key before saving")
            return

        try:
            env_path = Path(".env")
            env_content = ""

            # Read existing .env file if it exists
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # Update existing OPENAI_API_KEY or add it
                updated = False
                for i, line in enumerate(lines):
                    if line.strip().startswith("OPENAI_API_KEY"):
                        lines[i] = f"OPENAI_API_KEY={api_key}\n"
                        updated = True
                        break

                env_content = "".join(lines)
                if not updated:
                    env_content += f"\nOPENAI_API_KEY={api_key}\n"
            else:
                env_content = f"OPENAI_API_KEY={api_key}\n"

            # Write to .env file
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)

            update_env_status("✅ API key saved successfully")

        except Exception as e:
            update_env_status(f"❌ Failed to save: {str(e)[:50]}...")

    def load_environment():
        """Load API key from .env file"""
        try:
            env_path = Path(".env")
            if not env_path.exists():
                update_env_status("⚠️ No .env file found")
                return

            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("OPENAI_API_KEY="):
                        api_key = line.split("=", 1)[1]
                        api_key_var.set(api_key)
                        update_env_status("✅ API key loaded successfully")
                        return

            update_env_status("⚠️ API key not found in .env file")

        except Exception as e:
            update_env_status(f"❌ Failed to load: {str(e)[:50]}...")

    # Save and Load buttons
    ttk.Button(
        env_buttons_frame, 
        text="💾 Save", 
        bootstyle=SUCCESS, 
        width=8,
        command=save_environment
    ).pack(side=LEFT, padx=2)

    ttk.Button(
        env_buttons_frame, 
        text="📂 Load", 
        bootstyle=INFO, 
        width=8,
        command=load_environment
    ).pack(side=LEFT, padx=2)

    # Auto-load on startup
    load_environment()
    
    # Check initial API key status
    if api_key_var.get():
        update_env_status("✅ API key configured")
    else:
        update_env_status("⚠️ No API key configured")

    # Center: Appearance
    appearance_frame = ttk.LabelFrame(settings_container, text="🎨 Appearance", padding=8)
    appearance_frame.pack(side=LEFT, fill=Y, padx=5)

    # Theme selection with functional integration
    theme_frame = ttk.Frame(appearance_frame)
    theme_frame.pack(fill=X, pady=2)
    ttk.Label(theme_frame, text="Theme:", width=8).pack(side=LEFT)

    theme_var = ttk.StringVar(value=theme_manager.current_theme)
    theme_combo = ttk.Combobox(
        theme_frame, 
        textvariable=theme_var,
        values=[theme_manager.get_theme_display_name(theme) for theme in theme_manager.get_available_themes()],
        width=18,
        state="readonly"
    )
    theme_combo.pack(side=LEFT, padx=2)

    # Store theme names for mapping
    theme_names = theme_manager.get_available_themes()

    def on_theme_change(event=None):
        """Handle theme change"""
        selected_display = theme_var.get()
        # Find the actual theme name from display name
        selected_theme = None
        for theme_name in theme_names:
            if theme_manager.get_theme_display_name(theme_name) == selected_display:
                selected_theme = theme_name
                break

        if selected_theme:
            # Get the root window to apply theme
            root_window = theme_frame.winfo_toplevel()
            success = theme_manager.apply_theme(selected_theme, root_window)

            if success:
                # Update log if available
                if global_log_area:
                    global_log_area.insert(END, f"✨ Theme changed to: {selected_display}\n")
                    global_log_area.see(END)

                # Show restart notice for full effect
                messagebox.showinfo(
                    "Theme Applied", 
                    f"Theme '{selected_display}' applied!\n\nFor complete theme integration, restart the application."
                )
            else:
                messagebox.showerror("Theme Error", "Failed to apply theme. Please try again.")

    theme_combo.bind('<<ComboboxSelected>>', on_theme_change)

    # Theme preview button
    preview_btn = ttk.Button(
        theme_frame,
        text="👀",
        width=3,
        command=lambda: show_theme_preview(theme_var.get())
    )
    preview_btn.pack(side=LEFT, padx=2)

    # Right: Performance
    perf_frame = ttk.LabelFrame(settings_container, text="⚡ Performance", padding=8)
    perf_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(5, 0))

    batch_frame = ttk.Frame(perf_frame)
    batch_frame.pack(fill=X, pady=2)
    ttk.Label(batch_frame, text="Batch Size:", width=12).pack(side=LEFT)
    ttk.Spinbox(batch_frame, from_=10, to=200, width=8, value=BATCH_SIZE).pack(side=LEFT, padx=2)

    ttk.Checkbutton(perf_frame, text="Enable multithreading").pack(anchor="w", pady=1)
    ttk.Checkbutton(perf_frame, text="Show detailed progress").pack(anchor="w", pady=1)
    ttk.Checkbutton(perf_frame, text="Create backups").pack(anchor="w", pady=1)

    return tab_frame

def show_theme_preview(theme_display_name):
    """Show a preview of the selected theme"""
    # Find actual theme name
    theme_name = None
    for name in theme_manager.get_available_themes():
        if theme_manager.get_theme_display_name(name) == theme_display_name:
            theme_name = name
            break

    if not theme_name:
        return

    # Create preview window
    preview_win = Toplevel()
    preview_win.title(f"Theme Preview - {theme_display_name}")
    preview_win.geometry("400x300")
    preview_win.transient()
    preview_win.grab_set()

    # Get theme colors for preview
    colors = theme_manager.get_theme_preview_colors(theme_name)

    # Configure preview window
    preview_win.configure(bg=colors['bg'])

    # Header
    header_frame = ttk.Frame(preview_win)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(
        header_frame, 
        text=f"🎨 {theme_display_name}", 
        font=("Segoe UI", 14, "bold")
    ).pack()

    # Sample content
    content_frame = ttk.LabelFrame(preview_win, text="Preview Content", padding=15)
    content_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

    # Sample widgets
    ttk.Label(content_frame, text="Sample text with this theme").pack(pady=5)

    button_frame = ttk.Frame(content_frame)
    button_frame.pack(pady=10)

    ttk.Button(button_frame, text="Primary", bootstyle=PRIMARY).pack(side=LEFT, padx=5)
    ttk.Button(button_frame, text="Success", bootstyle=SUCCESS).pack(side=LEFT, padx=5)
    ttk.Button(button_frame, text="Info", bootstyle=INFO).pack(side=LEFT, padx=5)

    # Sample progress
    progress = ttk.Progressbar(content_frame, length=200, mode='determinate', value=75)
    progress.pack(pady=10)

    # Close button
    ttk.Button(
        preview_win, 
        text="Close Preview", 
        bootstyle=SECONDARY,
        command=preview_win.destroy
    ).pack(pady=10)

def show_index_stats():
    """Show index statistics in a popup window"""
    stats = get_index_statistics()

    if 'error' in stats:
        messagebox.showerror("Index Error", f"Error getting statistics: {stats['error']}")
        return

    # Create stats window
    stats_win = Toplevel()
    stats_win.title("📊 Index Statistics")
    stats_win.geometry("500x400")
    stats_win.transient()
    stats_win.grab_set()

    # Header
    header_frame = ttk.Frame(stats_win)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="📊 File Index Statistics", font=("Segoe UI", 14, "bold")).pack()

    # Main stats
    main_stats_frame = ttk.LabelFrame(stats_win, text="📈 Overview", padding=10)
    main_stats_frame.pack(fill=X, padx=20, pady=5)

    total_size_mb = stats['total_size_bytes'] / (1024 * 1024) if stats['total_size_bytes'] else 0
    total_size_gb = total_size_mb / 1024

    overview_text = f"""📁 Total Files: {stats['total_files']:,}
✅ Accessible: {stats['accessible_files']:,}
❌ Inaccessible: {stats['inaccessible_files']:,}
💾 Total Size: {total_size_gb:.2f} GB"""

    ttk.Label(main_stats_frame, text=overview_text, font=("Consolas", 9)).pack(anchor="w")

    # File types
    types_frame = ttk.LabelFrame(stats_win, text="📋 Top File Types", padding=10)
    types_frame.pack(fill=BOTH, expand=True, padx=20, pady=5)

    types_text = ScrolledText(types_frame, height=10, font=("Consolas", 8))
    types_text.pack(fill=BOTH, expand=True)

    if stats['file_types']:
        types_text.insert(END, "Type           Count    %\n")
        types_text.insert(END, "-" * 25 + "\n")
        for file_type, count in stats['file_types'][:15]:
            percentage = (count / stats['total_files']) * 100 if stats['total_files'] > 0 else 0
            display_type = file_type if file_type else "(none)"
            types_text.insert(END, f"{display_type:<12} {count:>6,} {percentage:>5.1f}%\n")

    ttk.Button(stats_win, text="Close", bootstyle=PRIMARY, command=stats_win.destroy).pack(pady=10)

# Helper functions
def export_to_csv():
    dest = filedialog.asksaveasfilename(
        defaultextension=".csv", 
        filetypes=[("CSV Files", "*.csv")],
        title="Export Database to CSV"
    )
    if not dest:
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM files")
            rows = c.fetchall()

        with open(dest, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Original Name", "New Path", "File Type", "Moved At", "Tags"])
            writer.writerows(rows)

        messagebox.showinfo("Export Complete", f"Database exported to:\n{dest}")
    except Exception as e:
        messagebox.showerror("Export Error", f"Failed to export database:\n{e}")

def preview_file():
    from src.file_preview import preview_file_dialog
    
    # Use the new comprehensive file preview module
    preview_file_dialog(ttk.Window())

def build_gui():
    """Build the main GUI with horizontal compact layout"""
    app = ttk.Window(
        themename=theme_manager.current_theme, 
        title="TidyDesk v2.1 - Declutter Your Desktop, Reclaim Your Focus.", 
        size=(1500, 800)  # Increased width to accommodate better layout
    )

    # Compact header
    header_frame = ttk.Frame(app)
    header_frame.pack(fill=X, pady=5)
    ttk.Label(
        header_frame, 
        text="🗂️ Tidy Desk v2.0 - Declutter Your Desktop, Reclaim Your Focus.", 
        font=("Segoe UI", 16, "bold")
    ).pack()

    # Create main content
    main_content = create_main_content(app)

    # Compact status bar
    status_frame = ttk.Frame(app)
    status_frame.pack(fill=X, pady=2)

    global global_status_label
    global_status_label = ttk.Label(
        status_frame, 
        text="✨ All Set – Sleek. Smart. Sorted.",
        font=("Segoe UI", 8)
    )
    global_status_label.pack()

    # Cleanup function for safe shutdown
    def on_closing():
        if global_desktop_watcher and global_desktop_watcher.is_running:
            global_desktop_watcher.stop_monitoring()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)

    # Start the application
    app.mainloop()

if __name__ == "__main__":
    build_gui()