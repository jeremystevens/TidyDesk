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

def open_undo_history_window(log_area, meter):
    """Open the undo history selection window"""
    win = Toplevel()
    win.title("Undo History")
    win.geometry("800x600")
    win.transient()
    win.grab_set()
    
    # Header
    header_frame = ttk.Frame(win)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="📜 Undo History", font=("Segoe UI", 16, "bold")).pack()
    ttk.Label(header_frame, text="Select a session to undo", font=("Segoe UI", 10)).pack()
    
    # Session list
    list_frame = ttk.Frame(win)
    list_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    # Treeview for better organization
    columns = ("Status", "Session", "Files", "Date", "Actions")
    tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
    
    # Configure columns
    tree.heading("Status", text="Status")
    tree.heading("Session", text="Session Name")
    tree.heading("Files", text="Files")
    tree.heading("Date", text="Date")
    tree.heading("Actions", text="Actions")
    
    tree.column("Status", width=80, anchor="center")
    tree.column("Session", width=200)
    tree.column("Files", width=80, anchor="center")
    tree.column("Date", width=150)
    tree.column("Actions", width=100, anchor="center")
    
    # Scrollbar for treeview
    scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    
    tree.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill="y")
    
    # Populate session list
    sessions = history_manager.get_session_list()
    session_map = {}
    
    for session_id, display_name, session_data in sessions:
        status = session_data.get("status", "unknown")
        status_emoji = {"active": "🔄", "completed": "✅", "undone": "↩️"}.get(status, "❓")
        
        file_count = len(session_data.get("actions", []))
        date_str = datetime.fromisoformat(session_data["timestamp"]).strftime("%Y-%m-%d %H:%M")
        
        # Color coding based on status
        tags = []
        if status == "active":
            tags = ["active"]
        elif status == "undone":
            tags = ["undone"]
        
        item_id = tree.insert("", "end", values=(
            status_emoji,
            session_data["name"],
            file_count,
            date_str,
            "Available" if status != "undone" else "Already undone"
        ), tags=tags)
        
        session_map[item_id] = session_id
    
    # Configure tags for colors
    tree.tag_configure("active", background="#e3f2fd")
    tree.tag_configure("undone", background="#ffebee")
    
    # Details panel
    details_frame = ttk.LabelFrame(win, text="Session Details", padding=10)
    details_frame.pack(fill=X, padx=20, pady=10)
    
    details_text = ScrolledText(details_frame, height=6, font=("Consolas", 9))
    details_text.pack(fill=BOTH, expand=True)
    
    def on_session_select(event):
        selection = tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        session_id = session_map.get(item_id)
        if not session_id:
            return
        
        # Find session data
        for _, _, session_data in sessions:
            if session_data["id"] == session_id:
                details_text.delete(1.0, END)
                details_text.insert(END, f"Session: {session_data['name']}\n")
                details_text.insert(END, f"Status: {session_data.get('status', 'unknown')}\n")
                details_text.insert(END, f"Created: {datetime.fromisoformat(session_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                if session_data.get('completed_at'):
                    details_text.insert(END, f"Completed: {datetime.fromisoformat(session_data['completed_at']).strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                if session_data.get('undone_at'):
                    details_text.insert(END, f"Undone: {datetime.fromisoformat(session_data['undone_at']).strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                details_text.insert(END, f"\nActions ({len(session_data.get('actions', []))}):\n")
                details_text.insert(END, "-" * 40 + "\n")
                
                for i, action in enumerate(session_data.get('actions', [])[:10]):  # Show first 10
                    original_name = Path(action['original']).name
                    new_name = Path(action['new']).name
                    details_text.insert(END, f"{i+1}. {original_name} → {new_name}\n")
                
                if len(session_data.get('actions', [])) > 10:
                    details_text.insert(END, f"... and {len(session_data.get('actions', [])) - 10} more\n")
                break
    
    tree.bind("<<TreeviewSelect>>", on_session_select)
    
    # Buttons
    button_frame = ttk.Frame(win)
    button_frame.pack(fill=X, padx=20, pady=10)
    
    def undo_selected_session():
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a session to undo.")
            return
        
        item_id = selection[0]
        session_id = session_map.get(item_id)
        if not session_id:
            return
        
        # Find session data for confirmation
        session_data = None
        for _, _, data in sessions:
            if data["id"] == session_id:
                session_data = data
                break
        
        if not session_data:
            return
        
        if session_data.get("status") == "undone":
            messagebox.showinfo("Already Undone", "This session has already been undone.")
            return
        
        # Confirmation dialog
        file_count = len(session_data.get("actions", []))
        result = messagebox.askyesno(
            "Confirm Undo",
            f"Are you sure you want to undo session '{session_data['name']}'?\n\n"
            f"This will restore {file_count} files to their original locations.\n\n"
            f"This action cannot be reversed."
        )
        
        if result:
            win.destroy()
            # Start undo in thread
            def undo_thread():
                def log_callback(msg):
                    log_area.after(0, lambda: log_area.insert(END, f"{msg}\n") or log_area.see(END))
                
                history_manager.undo_session(session_id, log_callback, meter)
            
            import threading
            thread = threading.Thread(target=undo_thread, daemon=True)
            thread.start()
    
    def clear_history():
        result = messagebox.askyesno(
            "Clear History",
            "Are you sure you want to clear all undo history?\n\n"
            "This will permanently remove all session records.\n"
            "Active sessions will be lost!"
        )
        if result:
            history_manager.save_history([])
            messagebox.showinfo("History Cleared", "All undo history has been cleared.")
            win.destroy()
    
    ttk.Button(
        button_frame, 
        text="↩️ Undo Selected Session", 
        bootstyle=WARNING,
        command=undo_selected_session
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        button_frame, 
        text="🗑️ Clear History", 
        bootstyle=DANGER,
        command=clear_history
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        button_frame, 
        text="❌ Cancel", 
        bootstyle=SECONDARY,
        command=win.destroy
    ).pack(side=RIGHT, padx=5)

def open_search_window():
    win = Toplevel()
    win.title("Search Files")
    win.geometry("700x500")

def export_to_csv():
    dest = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
    if not dest:
        return
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM files")
        rows = c.fetchall()
    with open(dest, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Original Name", "New Path", "File Type", "Moved At", "Tags"])
        writer.writerows(rows)

def preview_file():
    path = filedialog.askopenfilename()
    if not path:
        return
    win = Toplevel()
    win.title("Preview")
    win.geometry("700x600")

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

def build_gui():
    from tkinter import END
    app = ttk.Window(themename="superhero", title="Desktop File Organizer v2.0", size=(1200, 690))
    
    # Main header - more compact
    header_frame = ttk.Frame(app)
    header_frame.pack(fill=X, pady=(10, 5))
    ttk.Label(header_frame, text="🗂️ Desktop File Organizer", font=("Segoe UI", 18, "bold")).pack()
    ttk.Label(header_frame, text="Enhanced with Multi-Session Undo History", font=("Segoe UI", 9)).pack()

    # Main content area - side by side layout
    main_frame = ttk.Frame(app)
    main_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

    # Left side - Controls and Actions
    left_frame = ttk.Frame(main_frame)
    left_frame.pack(side=LEFT, fill=Y, padx=(0, 10))

    # Top row of action buttons - more compact
    actions_frame = ttk.LabelFrame(left_frame, text="🚀 Actions", padding=10)
    actions_frame.pack(fill=X, pady=5)
    
    # Primary actions in a grid layout
    primary_grid = ttk.Frame(actions_frame)
    primary_grid.pack()
    
    ttk.Button(
        primary_grid, 
        text="🚀 Start Organizing", 
        bootstyle=SUCCESS,
        width=16,
        command=lambda: start_processing_threaded(log_area, meter)
    ).grid(row=0, column=0, padx=3, pady=2)

    ttk.Button(
        primary_grid, 
        text="🔄 Retag Files", 
        bootstyle=INFO,
        width=16,
        command=lambda: retag_missing_entries_threaded(
            lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END), 
            meter
        )
    ).grid(row=0, column=1, padx=3, pady=2)

    ttk.Button(
        primary_grid, 
        text="🏷️ Group by Tags", 
        bootstyle=PRIMARY,
        width=16,
        command=regroup_by_tags
    ).grid(row=1, column=0, padx=3, pady=2)

    # Undo section - compact
    undo_frame = ttk.LabelFrame(left_frame, text="↩️ Undo", padding=10)
    undo_frame.pack(fill=X, pady=5)
    
    undo_grid = ttk.Frame(undo_frame)
    undo_grid.pack()
    
    ttk.Button(
        undo_grid, 
        text="↩️ Quick Undo", 
        bootstyle=WARNING,
        width=16,
        command=lambda: undo_last_cleanup_threaded(
            lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END),
            meter
        )
    ).grid(row=0, column=0, padx=3, pady=2)

    ttk.Button(
        undo_grid, 
        text="📜 Undo History", 
        bootstyle=WARNING,
        width=16,
        command=lambda: open_undo_history_window(log_area, meter)
    ).grid(row=0, column=1, padx=3, pady=2)

    # Tools section - compact
    tools_frame = ttk.LabelFrame(left_frame, text="🛠️ Tools", padding=10)
    tools_frame.pack(fill=X, pady=5)
    
    tools_grid = ttk.Frame(tools_frame)
    tools_grid.pack()

    ttk.Button(
        tools_grid, 
        text="🔍 Search", 
        bootstyle=SECONDARY, 
        width=12,
        command=open_search_window
    ).grid(row=0, column=0, padx=2, pady=2)

    ttk.Button(
        tools_grid, 
        text="📊 Export", 
        bootstyle=SECONDARY, 
        width=12,
        command=export_to_csv
    ).grid(row=0, column=1, padx=2, pady=2)

    ttk.Button(
        tools_grid, 
        text="👁️ Preview", 
        bootstyle=LIGHT, 
        width=12,
        command=preview_file
    ).grid(row=0, column=2, padx=2, pady=2)

    # Settings section - inline
    settings_frame = ttk.LabelFrame(left_frame, text="⚙️ Settings", padding=10)
    settings_frame.pack(fill=X, pady=5)
    
    ai_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        settings_frame, 
        text="🤖 Enable AI Tagging", 
        variable=ai_var,
        command=lambda: set_ai_enabled(ai_var.get())
    ).pack()

    # Progress meter - more compact
    meter_frame = ttk.LabelFrame(left_frame, text="📊 Progress", padding=10)
    meter_frame.pack(fill=X, pady=5)
    
    meter = Meter(
        meter_frame, 
        bootstyle=INFO, 
        subtext="Ready to start organizing", 
        textright="files", 
        amounttotal=100,
        amountused=0,
        stripethickness=4,
        showtext=True
    )
    meter.pack(fill=X)

    # Right side - Log area taking most of the space
    right_frame = ttk.Frame(main_frame)
    right_frame.pack(side=RIGHT, fill=BOTH, expand=True)

    log_frame = ttk.LabelFrame(right_frame, text="📋 Activity Log", padding=10)
    log_frame.pack(fill=BOTH, expand=True)
    
    log_area = ScrolledText(log_frame, height=20, font=("Consolas", 9))
    log_area.pack(fill=BOTH, expand=True)

    # Status bar - more compact
    status_frame = ttk.Frame(app)
    status_frame.pack(fill=X, pady=(5, 10))
    
    status_label = ttk.Label(
        status_frame, 
        text="✨ Ready to organize desktop files with enhanced undo capabilities", 
        font=("Segoe UI", 9)
    )
    status_label.pack()

    app.mainloop()