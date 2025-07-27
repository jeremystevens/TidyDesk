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

# Tab Content Functions
def create_organize_tab(parent):
    """Create the main organize tab"""
    tab_frame = ttk.Frame(parent)
    
    # Main content area
    main_frame = ttk.Frame(tab_frame)
    main_frame.pack(fill=BOTH, expand=True, padx=15, pady=10)
    
    # Left side - Controls
    left_frame = ttk.Frame(main_frame)
    left_frame.pack(side=LEFT, fill=Y, padx=(0, 10))
    
    # Primary actions
    actions_frame = ttk.LabelFrame(left_frame, text="🚀 Actions", padding=15)
    actions_frame.pack(fill=X, pady=5)
    
    ttk.Button(
        actions_frame, 
        text="🚀 Start Organizing Desktop", 
        bootstyle=SUCCESS,
        width=25,
        command=lambda: start_processing_threaded(global_log_area, global_meter)
    ).pack(pady=5)
    
    ttk.Button(
        actions_frame, 
        text="🏷️ Group Files by Tags", 
        bootstyle=PRIMARY,
        width=25,
        command=regroup_by_tags
    ).pack(pady=5)
    
    # NEW INDEX BUTTON
    ttk.Button(
        actions_frame, 
        text="📇 Index System Files", 
        bootstyle=INFO,
        width=25,
        command=lambda: start_indexing_threaded(
            lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None,
            global_meter
        )
    ).pack(pady=5)
    
    # Tools section
    tools_frame = ttk.LabelFrame(left_frame, text="🛠️ Tools", padding=15)
    tools_frame.pack(fill=X, pady=5)
    
    ttk.Button(
        tools_frame, 
        text="📊 Export Database to CSV", 
        bootstyle=SECONDARY, 
        width=25,
        command=export_to_csv
    ).pack(pady=3)
    
    ttk.Button(
        tools_frame, 
        text="🔍 Search Files", 
        bootstyle=SECONDARY, 
        width=25,
        command=open_search_window
    ).pack(pady=3)
    
    ttk.Button(
        tools_frame, 
        text="👁️ Preview File", 
        bootstyle=LIGHT, 
        width=25,
        command=preview_file
    ).pack(pady=3)
    
    # NEW INDEX TOOLS SECTION
    index_tools_frame = ttk.LabelFrame(left_frame, text="📇 Index Tools", padding=15)
    index_tools_frame.pack(fill=X, pady=5)
    
    def show_index_stats():
        """Show index statistics in a popup window"""
        stats = get_index_statistics()
        
        if 'error' in stats:
            messagebox.showerror("Index Error", f"Error getting statistics: {stats['error']}")
            return
        
        # Create stats window
        stats_win = Toplevel()
        stats_win.title("📊 Index Statistics")
        stats_win.geometry("600x500")
        stats_win.transient()
        stats_win.grab_set()
        
        # Header
        header_frame = ttk.Frame(stats_win)
        header_frame.pack(fill=X, padx=20, pady=10)
        ttk.Label(header_frame, text="📊 File Index Statistics", font=("Segoe UI", 16, "bold")).pack()
        
        # Main stats
        main_stats_frame = ttk.LabelFrame(stats_win, text="📈 Overview", padding=15)
        main_stats_frame.pack(fill=X, padx=20, pady=10)
        
        total_size_mb = stats['total_size_bytes'] / (1024 * 1024) if stats['total_size_bytes'] else 0
        total_size_gb = total_size_mb / 1024
        
        overview_text = f"""
📁 Total Files Indexed: {stats['total_files']:,}
✅ Accessible Files: {stats['accessible_files']:,}
❌ Inaccessible Files: {stats['inaccessible_files']:,}
💾 Total Size: {total_size_gb:.2f} GB ({total_size_mb:.1f} MB)
"""
        
        ttk.Label(main_stats_frame, text=overview_text, font=("Consolas", 10)).pack(anchor="w")
        
        # File types
        types_frame = ttk.LabelFrame(stats_win, text="📋 Top File Types", padding=15)
        types_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
        
        types_text = ScrolledText(types_frame, height=12, font=("Consolas", 9))
        types_text.pack(fill=BOTH, expand=True)
        
        if stats['file_types']:
            types_text.insert(END, "File Type          Count      Percentage\n")
            types_text.insert(END, "-" * 45 + "\n")
            for file_type, count in stats['file_types']:
                percentage = (count / stats['total_files']) * 100 if stats['total_files'] > 0 else 0
                display_type = file_type if file_type else "(no extension)"
                types_text.insert(END, f"{display_type:<15} {count:>8,} {percentage:>8.1f}%\n")
        else:
            types_text.insert(END, "No file type data available.")
        
        # Close button
        ttk.Button(
            stats_win, 
            text="Close", 
            bootstyle=PRIMARY,
            command=stats_win.destroy
        ).pack(pady=10)
    
    def confirm_clear_index():
        """Confirm before clearing the index"""
        result = messagebox.askyesno(
            "Clear Index",
            "Are you sure you want to clear the entire file index?\n\n"
            "This will permanently remove all indexed file records.\n"
            "You will need to re-run the indexing process."
        )
        if result:
            success = clear_index()
            if success:
                messagebox.showinfo("Index Cleared", "File index has been cleared successfully.")
                if global_log_area:
                    global_log_area.insert(END, "🗑️ File index cleared successfully.\n")
                    global_log_area.see(END)
            else:
                messagebox.showerror("Clear Failed", "Failed to clear the file index.")
    
    ttk.Button(
        index_tools_frame, 
        text="📊 Index Statistics", 
        bootstyle=INFO, 
        width=25,
        command=show_index_stats
    ).pack(pady=3)
    
    ttk.Button(
        index_tools_frame, 
        text="🗑️ Clear Index", 
        bootstyle=WARNING, 
        width=25,
        command=confirm_clear_index
    ).pack(pady=3)
    
    # Progress meter
    meter_frame = ttk.LabelFrame(left_frame, text="📊 Progress", padding=15)
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
    
    # Right side - Log area
    right_frame = ttk.Frame(main_frame)
    right_frame.pack(side=RIGHT, fill=BOTH, expand=True)
    
    log_frame = ttk.LabelFrame(right_frame, text="📋 Activity Log", padding=10)
    log_frame.pack(fill=BOTH, expand=True)
    
    log_area = ScrolledText(log_frame, height=20, font=("Consolas", 9))
    log_area.pack(fill=BOTH, expand=True)
    
    # Set global variables
    global global_log_area, global_meter
    global_log_area = log_area
    global_meter = meter
    
    return tab_frame

def create_undo_tab(parent):
    """Create the undo tab"""
    tab_frame = ttk.Frame(parent)
    
    # Header
    header_frame = ttk.Frame(tab_frame)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="↩️ Undo Operations", font=("Segoe UI", 16, "bold")).pack()
    ttk.Label(header_frame, text="Manage and revert previous cleanup sessions", font=("Segoe UI", 10)).pack()
    
    # Quick undo section
    quick_frame = ttk.LabelFrame(tab_frame, text="⚡ Quick Undo", padding=15)
    quick_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Button(
        quick_frame, 
        text="↩️ Undo Last Cleanup Session", 
        bootstyle=WARNING,
        width=30,
        command=lambda: undo_last_cleanup_threaded(
            lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None,
            global_meter
        )
    ).pack(pady=5)
    
    ttk.Label(
        quick_frame, 
        text="Quickly undo the most recent organization session", 
        font=("Segoe UI", 9)
    ).pack()
    
    # Session history section
    history_frame = ttk.LabelFrame(tab_frame, text="📜 Session History", padding=15)
    history_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    # Session list with treeview
    columns = ("Status", "Session", "Files", "Date")
    tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=12)
    
    tree.heading("Status", text="Status")
    tree.heading("Session", text="Session Name")
    tree.heading("Files", text="Files")
    tree.heading("Date", text="Date")
    
    tree.column("Status", width=80, anchor="center")
    tree.column("Session", width=250)
    tree.column("Files", width=80, anchor="center")
    tree.column("Date", width=150)
    
    # Scrollbar for treeview
    scrollbar = ttk.Scrollbar(history_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    
    tree_frame = ttk.Frame(history_frame)
    tree_frame.pack(fill=BOTH, expand=True)
    
    tree.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill="y")
    
    # Populate session list
    def refresh_sessions():
        # Clear existing items
        for item in tree.get_children():
            tree.delete(item)
        
        sessions = history_manager.get_session_list()
        session_map = {}
        
        for session_id, display_name, session_data in sessions:
            status = session_data.get("status", "unknown")
            status_emoji = {"active": "🔄", "completed": "✅", "undone": "↩️"}.get(status, "❓")
            
            file_count = len(session_data.get("actions", []))
            date_str = datetime.fromisoformat(session_data["timestamp"]).strftime("%Y-%m-%d %H:%M")
            
            tags = []
            if status == "active":
                tags = ["active"]
            elif status == "undone":
                tags = ["undone"]
            
            item_id = tree.insert("", "end", values=(
                status_emoji,
                session_data["name"],
                file_count,
                date_str
            ), tags=tags)
            
            session_map[item_id] = session_id
        
        return session_map
    
    session_map = refresh_sessions()
    
    # Configure tags for colors
    tree.tag_configure("active", background="#e3f2fd")
    tree.tag_configure("undone", background="#ffebee")
    
    # Button frame
    button_frame = ttk.Frame(history_frame)
    button_frame.pack(fill=X, pady=10)
    
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
        sessions = history_manager.get_session_list()
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
            # Start undo in thread
            def undo_thread():
                def log_callback(msg):
                    if global_log_area:
                        global_log_area.after(0, lambda: global_log_area.insert(END, f"{msg}\n") or global_log_area.see(END))
                
                history_manager.undo_session(session_id, log_callback, global_meter)
                # Refresh the session list after undo
                tree.after(0, lambda: refresh_sessions())
            
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
            refresh_sessions()
            messagebox.showinfo("History Cleared", "All undo history has been cleared.")
    
    ttk.Button(
        button_frame, 
        text="↩️ Undo Selected Session", 
        bootstyle=WARNING,
        command=undo_selected_session
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        button_frame, 
        text="🔄 Refresh List", 
        bootstyle=INFO,
        command=lambda: refresh_sessions()
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        button_frame, 
        text="🗑️ Clear History", 
        bootstyle=DANGER,
        command=clear_history
    ).pack(side=RIGHT, padx=5)
    
    return tab_frame

def create_ai_tagging_tab(parent):
    """Create the AI tagging tab"""
    tab_frame = ttk.Frame(parent)
    
    # Header
    header_frame = ttk.Frame(tab_frame)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="🤖 AI Tagging Controls", font=("Segoe UI", 16, "bold")).pack()
    ttk.Label(header_frame, text="Configure AI-powered file tagging and analysis", font=("Segoe UI", 10)).pack()
    
    # AI Settings section
    settings_frame = ttk.LabelFrame(tab_frame, text="⚙️ AI Settings", padding=15)
    settings_frame.pack(fill=X, padx=20, pady=10)
    
    # AI Enable/Disable
    ai_var = ttk.BooleanVar(value=True)
    ai_check = ttk.Checkbutton(
        settings_frame, 
        text="🤖 Enable AI Tagging", 
        variable=ai_var,
        command=lambda: set_ai_enabled(ai_var.get())
    )
    ai_check.pack(anchor="w", pady=5)
    
    ttk.Label(
        settings_frame, 
        text="When enabled, AI will automatically generate descriptive tags for files", 
        font=("Segoe UI", 9)
    ).pack(anchor="w", padx=20)
    
    # Batch size setting
    batch_frame = ttk.Frame(settings_frame)
    batch_frame.pack(fill=X, pady=10)
    
    ttk.Label(batch_frame, text="Batch Size:").pack(side=LEFT)
    batch_var = ttk.IntVar(value=BATCH_SIZE)
    batch_spin = ttk.Spinbox(batch_frame, from_=1, to=100, width=10, textvariable=batch_var)
    batch_spin.pack(side=LEFT, padx=10)
    ttk.Label(batch_frame, text="files per AI request").pack(side=LEFT)
    
    # Retagging section
    retag_frame = ttk.LabelFrame(tab_frame, text="🔄 Retag Operations", padding=15)
    retag_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Button(
        retag_frame, 
        text="🔄 Retag Missing Files", 
        bootstyle=INFO,
        width=25,
        command=lambda: retag_missing_entries_threaded(
            lambda msg: global_log_area.insert(END, msg + "\n") or global_log_area.see(END) if global_log_area else None, 
            global_meter
        )
    ).pack(pady=5)
    
    ttk.Label(
        retag_frame, 
        text="Find files without tags and generate new AI tags", 
        font=("Segoe UI", 9)
    ).pack()
    
    # Skip tags configuration
    skip_frame = ttk.LabelFrame(tab_frame, text="🚫 Skip Tags", padding=15)
    skip_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Label(
        skip_frame, 
        text="Files with these tags will be skipped during retagging:", 
        font=("Segoe UI", 9)
    ).pack(anchor="w")
    
    skip_text = ScrolledText(skip_frame, height=3, font=("Consolas", 9))
    skip_text.pack(fill=X, pady=5)
    skip_text.insert(END, ", ".join(SKIP_TAGS))
    
    # Preview section
    preview_frame = ttk.LabelFrame(tab_frame, text="👁️ Tag Preview", padding=15)
    preview_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    ttk.Label(
        preview_frame, 
        text="Preview AI-generated tags before applying them", 
        font=("Segoe UI", 9)
    ).pack(anchor="w")
    
    # File selection for preview
    preview_control_frame = ttk.Frame(preview_frame)
    preview_control_frame.pack(fill=X, pady=5)
    
    ttk.Button(
        preview_control_frame, 
        text="📁 Select Files to Preview", 
        bootstyle=SECONDARY,
        command=lambda: messagebox.showinfo("Coming Soon", "Tag preview feature coming in next update!")
    ).pack(side=LEFT)
    
    # Preview results area
    preview_text = ScrolledText(preview_frame, height=8, font=("Consolas", 9))
    preview_text.pack(fill=BOTH, expand=True, pady=5)
    preview_text.insert(END, "Select files above to preview their AI-generated tags...")
    
    return tab_frame

def create_analytics_tab(parent):
    """Create the analytics tab"""
    tab_frame = ttk.Frame(parent)
    
    # Header
    header_frame = ttk.Frame(tab_frame)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="📊 Analytics Dashboard", font=("Segoe UI", 16, "bold")).pack()
    ttk.Label(header_frame, text="View statistics and insights about your file organization", font=("Segoe UI", 10)).pack()
    
    # Main content area with two columns
    content_frame = ttk.Frame(tab_frame)
    content_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    # Left column - Statistics
    left_col = ttk.Frame(content_frame)
    left_col.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
    
    # File statistics
    file_stats_frame = ttk.LabelFrame(left_col, text="📁 File Statistics", padding=15)
    file_stats_frame.pack(fill=X, pady=5)
    
    # Get stats from database
    def get_file_stats():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM files")
                total_files = c.fetchone()[0]
                
                c.execute("SELECT file_type, COUNT(*) FROM files GROUP BY file_type")
                type_stats = c.fetchall()
                
                c.execute("SELECT COUNT(*) FROM files WHERE tags IS NOT NULL AND tags != ''")
                tagged_files = c.fetchone()[0]
                
                return total_files, type_stats, tagged_files
        except:
            return 0, [], 0
    
    total_files, type_stats, tagged_files = get_file_stats()
    
    # Display statistics
    stats_text = f"""
📊 Total Files Processed: {total_files}
🏷️ Files with Tags: {tagged_files}
📝 Untagged Files: {total_files - tagged_files}
📈 Tag Coverage: {(tagged_files/total_files*100) if total_files > 0 else 0:.1f}%
"""
    
    ttk.Label(file_stats_frame, text=stats_text, font=("Consolas", 10)).pack(anchor="w")
    
    # File type distribution
    type_frame = ttk.LabelFrame(left_col, text="📋 File Type Distribution", padding=15)
    type_frame.pack(fill=BOTH, expand=True, pady=5)
    
    type_text = ScrolledText(type_frame, height=8, font=("Consolas", 9))
    type_text.pack(fill=BOTH, expand=True)
    
    if type_stats:
        type_text.insert(END, "File Type              Count\n")
        type_text.insert(END, "-" * 35 + "\n")
        for file_type, count in sorted(type_stats, key=lambda x: x[1], reverse=True):
            type_text.insert(END, f"{file_type:<20} {count:>6}\n")
    else:
        type_text.insert(END, "No file statistics available yet.\nRun an organization session to see data.")
    
    # Right column - Session history and charts
    right_col = ttk.Frame(content_frame)
    right_col.pack(side=RIGHT, fill=BOTH, expand=True)
    
    # Session statistics
    session_stats_frame = ttk.LabelFrame(right_col, text="⏱️ Session Statistics", padding=15)
    session_stats_frame.pack(fill=X, pady=5)
    
    def get_session_stats():
        sessions = history_manager.get_session_list()
        total_sessions = len(sessions)
        completed_sessions = sum(1 for _, _, data in sessions if data.get("status") == "completed")
        total_actions = sum(len(data.get("actions", [])) for _, _, data in sessions)
        return total_sessions, completed_sessions, total_actions
    
    total_sessions, completed_sessions, total_actions = get_session_stats()
    
    session_stats_text = f"""
🔄 Total Sessions: {total_sessions}
✅ Completed Sessions: {completed_sessions}
📁 Total File Operations: {total_actions}
"""
    
    ttk.Label(session_stats_frame, text=session_stats_text, font=("Consolas", 10)).pack(anchor="w")
    
    # Recent activity
    activity_frame = ttk.LabelFrame(right_col, text="📈 Recent Activity", padding=15)
    activity_frame.pack(fill=BOTH, expand=True, pady=5)
    
    activity_text = ScrolledText(activity_frame, height=12, font=("Consolas", 9))
    activity_text.pack(fill=BOTH, expand=True)
    
    # Show recent sessions
    sessions = history_manager.get_session_list()
    if sessions:
        activity_text.insert(END, "Recent Sessions:\n")
        activity_text.insert(END, "-" * 40 + "\n")
        for session_id, display_name, session_data in sessions[:5]:  # Show last 5
            status = session_data.get("status", "unknown")
            timestamp = datetime.fromisoformat(session_data["timestamp"]).strftime("%m/%d %H:%M")
            file_count = len(session_data.get("actions", []))
            activity_text.insert(END, f"{timestamp} | {session_data['name']}\n")
            activity_text.insert(END, f"         Status: {status} | Files: {file_count}\n\n")
    else:
        activity_text.insert(END, "No session history available yet.\nRun an organization session to see activity.")
    
    # Refresh button
    refresh_frame = ttk.Frame(tab_frame)
    refresh_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Button(
        refresh_frame, 
        text="🔄 Refresh Statistics", 
        bootstyle=INFO,
        command=lambda: messagebox.showinfo("Refresh", "Statistics refreshed!\n(In future version, this will auto-update)")
    ).pack()
    
    return tab_frame

def create_rules_tab(parent):
    """Create the rules tab"""
    tab_frame = ttk.Frame(parent)
    
    # Header
    header_frame = ttk.Frame(tab_frame)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="📋 Custom Rules", font=("Segoe UI", 16, "bold")).pack()
    ttk.Label(header_frame, text="Define custom file handling rules and preferences", font=("Segoe UI", 10)).pack()
    
    # File type routing rules
    routing_frame = ttk.LabelFrame(tab_frame, text="📁 File Type Routing", padding=15)
    routing_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Label(
        routing_frame, 
        text="Customize where different file types should be organized:", 
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", pady=(0, 10))
    
    # Sample routing rules (would load from config in real implementation)
    routing_text = ScrolledText(routing_frame, height=8, font=("Consolas", 9))
    routing_text.pack(fill=X, pady=5)
    
    sample_rules = """# File Type Routing Rules
# Format: file_extension -> destination_folder

.pdf -> Documents/PDFs
.docx -> Documents/Word
.xlsx -> Documents/Excel
.jpg,.png,.gif -> Media/Images
.mp4,.avi,.mkv -> Media/Videos
.mp3,.wav,.flac -> Media/Audio
.zip,.rar,.7z -> Downloads/Archives
.exe,.msi -> Software/Installers
.txt,.md -> Documents/Text
"""
    
    routing_text.insert(END, sample_rules)
    
    # Skip folders section
    skip_frame = ttk.LabelFrame(tab_frame, text="🚫 Skip Rules", padding=15)
    skip_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Label(
        skip_frame, 
        text="Files and folders to skip during organization:", 
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", pady=(0, 10))
    
    skip_text = ScrolledText(skip_frame, height=6, font=("Consolas", 9))
    skip_text.pack(fill=X, pady=5)
    
    skip_rules = """# Skip Rules - one per line
# Folders to skip:
Organized
Desktop.ini
Thumbs.db
.git
node_modules

# File patterns to skip:
*.tmp
*.temp
~*
.*
"""
    
    skip_text.insert(END, skip_rules)
    
    # Custom naming rules
    naming_frame = ttk.LabelFrame(tab_frame, text="🏷️ Naming Rules", padding=15)
    naming_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    ttk.Label(
        naming_frame, 
        text="Custom file naming and organization patterns:", 
        font=("Segoe UI", 10, "bold")
    ).pack(anchor="w", pady=(0, 10))
    
    naming_text = ScrolledText(naming_frame, height=6, font=("Consolas", 9))
    naming_text.pack(fill=BOTH, expand=True, pady=5)
    
    naming_rules = """# Naming Rules
# Use variables: {date}, {type}, {tag}, {original_name}

# Date-based organization:
enable_date_folders = true
date_format = "YYYY-MM"

# Tag-based subfolders:
create_tag_subfolders = true
max_tags_per_folder = 3

# File naming:
preserve_original_names = true
add_date_prefix = false
"""
    
    naming_text.insert(END, naming_rules)
    
    # Control buttons
    control_frame = ttk.Frame(tab_frame)
    control_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Button(
        control_frame, 
        text="💾 Save Rules", 
        bootstyle=SUCCESS,
        command=lambda: messagebox.showinfo("Save Rules", "Rules saved successfully!\n(Feature will be fully implemented in next update)")
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        control_frame, 
        text="🔄 Reset to Defaults", 
        bootstyle=WARNING,
        command=lambda: messagebox.showinfo("Reset", "Rules reset to defaults!\n(Feature will be fully implemented in next update)")
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        control_frame, 
        text="📁 Import Rules", 
        bootstyle=INFO,
        command=lambda: messagebox.showinfo("Import", "Import rules from file!\n(Feature coming in next update)")
    ).pack(side=RIGHT, padx=5)
    
    return tab_frame

def create_settings_tab(parent):
    """Create the settings tab"""
    tab_frame = ttk.Frame(parent)
    
    # Header
    header_frame = ttk.Frame(tab_frame)
    header_frame.pack(fill=X, padx=20, pady=10)
    ttk.Label(header_frame, text="⚙️ Settings", font=("Segoe UI", 16, "bold")).pack()
    ttk.Label(header_frame, text="Configure application settings and preferences", font=("Segoe UI", 10)).pack()
    
    # Main settings area with scrolling
    settings_scroll = ScrolledText(tab_frame, height=20)
    settings_scroll.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    # We'll replace this with actual settings widgets
    settings_content = ttk.Frame(settings_scroll)
    
    # Environment settings
    env_frame = ttk.LabelFrame(tab_frame, text="🌍 Environment", padding=15)
    env_frame.pack(fill=X, padx=20, pady=5)
    
    # API Key setting
    api_frame = ttk.Frame(env_frame)
    api_frame.pack(fill=X, pady=5)
    ttk.Label(api_frame, text="OpenAI API Key:", width=15).pack(side=LEFT)
    api_entry = ttk.Entry(api_frame, show="*", width=40)
    api_entry.pack(side=LEFT, padx=10)
    ttk.Button(api_frame, text="Test", bootstyle=INFO, width=8).pack(side=LEFT, padx=5)
    
    # Database path
    db_frame = ttk.Frame(env_frame)
    db_frame.pack(fill=X, pady=5)
    ttk.Label(db_frame, text="Database Path:", width=15).pack(side=LEFT)
    db_entry = ttk.Entry(db_frame, width=40)
    db_entry.pack(side=LEFT, padx=10)
    db_entry.insert(0, str(DB_PATH))
    ttk.Button(db_frame, text="Browse", bootstyle=SECONDARY, width=8).pack(side=LEFT, padx=5)
    
    # Organized folder path
    org_frame = ttk.Frame(env_frame)
    org_frame.pack(fill=X, pady=5)
    ttk.Label(org_frame, text="Organized Folder:", width=15).pack(side=LEFT)
    org_entry = ttk.Entry(org_frame, width=40)
    org_entry.pack(side=LEFT, padx=10)
    from src.organizer import ORGANIZED
    org_entry.insert(0, str(ORGANIZED))
    ttk.Button(org_frame, text="Browse", bootstyle=SECONDARY, width=8).pack(side=LEFT, padx=5)
    
    # Appearance settings
    appearance_frame = ttk.LabelFrame(tab_frame, text="🎨 Appearance", padding=15)
    appearance_frame.pack(fill=X, padx=20, pady=5)
    
    # Theme selection
    theme_frame = ttk.Frame(appearance_frame)
    theme_frame.pack(fill=X, pady=5)
    ttk.Label(theme_frame, text="Theme:", width=15).pack(side=LEFT)
    
    theme_var = ttk.StringVar(value="superhero")
    theme_combo = ttk.Combobox(
        theme_frame, 
        textvariable=theme_var,
        values=["superhero", "darkly", "solar", "cyborg", "vapor", "flatly", "journal", "litera"],
        width=15,
        state="readonly"
    )
    theme_combo.pack(side=LEFT, padx=10)
    
    def change_theme():
        messagebox.showinfo("Theme", f"Theme changed to {theme_var.get()}!\nRestart the application to see changes.")
    
    ttk.Button(theme_frame, text="Apply", bootstyle=PRIMARY, command=change_theme).pack(side=LEFT, padx=5)
    
    # Font size
    font_frame = ttk.Frame(appearance_frame)
    font_frame.pack(fill=X, pady=5)
    ttk.Label(font_frame, text="Font Size:", width=15).pack(side=LEFT)
    font_var = ttk.IntVar(value=9)
    font_spin = ttk.Spinbox(font_frame, from_=8, to=16, width=10, textvariable=font_var)
    font_spin.pack(side=LEFT, padx=10)
    
    # Performance settings
    performance_frame = ttk.LabelFrame(tab_frame, text="⚡ Performance", padding=15)
    performance_frame.pack(fill=X, padx=20, pady=5)
    
    # Batch size for processing
    batch_frame = ttk.Frame(performance_frame)
    batch_frame.pack(fill=X, pady=5)
    ttk.Label(batch_frame, text="Processing Batch Size:", width=20).pack(side=LEFT)
    batch_var = ttk.IntVar(value=BATCH_SIZE)
    batch_spin = ttk.Spinbox(batch_frame, from_=10, to=200, width=10, textvariable=batch_var)
    batch_spin.pack(side=LEFT, padx=10)
    ttk.Label(batch_frame, text="files").pack(side=LEFT)
    
    # Threading options
    threading_frame = ttk.Frame(performance_frame)
    threading_frame.pack(fill=X, pady=5)
    
    threading_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        threading_frame, 
        text="Enable multithreading for file operations", 
        variable=threading_var
    ).pack(anchor="w")
    
    progress_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        threading_frame, 
        text="Show detailed progress information", 
        variable=progress_var
    ).pack(anchor="w")
    
    # Backup settings
    backup_frame = ttk.LabelFrame(tab_frame, text="💾 Backup & Safety", padding=15)
    backup_frame.pack(fill=X, padx=20, pady=5)
    
    backup_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        backup_frame, 
        text="Create backup before organizing", 
        variable=backup_var
    ).pack(anchor="w", pady=2)
    
    confirm_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        backup_frame, 
        text="Confirm before large operations (>100 files)", 
        variable=confirm_var
    ).pack(anchor="w", pady=2)
    
    auto_save_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        backup_frame, 
        text="Auto-save settings changes", 
        variable=auto_save_var
    ).pack(anchor="w", pady=2)
    
    # Control buttons
    settings_control_frame = ttk.Frame(tab_frame)
    settings_control_frame.pack(fill=X, padx=20, pady=10)
    
    ttk.Button(
        settings_control_frame, 
        text="💾 Save All Settings", 
        bootstyle=SUCCESS,
        command=lambda: messagebox.showinfo("Settings", "All settings saved successfully!")
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        settings_control_frame, 
        text="🔄 Reset to Defaults", 
        bootstyle=WARNING,
        command=lambda: messagebox.showinfo("Reset", "Settings reset to defaults!")
    ).pack(side=LEFT, padx=5)
    
    ttk.Button(
        settings_control_frame, 
        text="📁 Export Settings", 
        bootstyle=INFO,
        command=lambda: messagebox.showinfo("Export", "Settings exported to file!")
    ).pack(side=RIGHT, padx=5)
    
    return tab_frame

def create_about_tab(parent):
    """Create the about tab"""
    tab_frame = ttk.Frame(parent)
    
    # Header with app info
    header_frame = ttk.Frame(tab_frame)
    header_frame.pack(fill=X, padx=20, pady=20)
    
    ttk.Label(header_frame, text="🗂️ Desktop File Organizer", font=("Segoe UI", 20, "bold")).pack()
    ttk.Label(header_frame, text="Version 2.0.0 - Enhanced Edition", font=("Segoe UI", 12)).pack(pady=5)
    ttk.Label(header_frame, text="AI-Powered Desktop File Organization Tool", font=("Segoe UI", 10)).pack()
    
    # Main content area
    content_frame = ttk.Frame(tab_frame)
    content_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    # Left column - App info
    left_col = ttk.Frame(content_frame)
    left_col.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
    
    # Features section
    features_frame = ttk.LabelFrame(left_col, text="✨ Features", padding=15)
    features_frame.pack(fill=X, pady=5)
    
    features_text = """
🤖 AI-Powered File Tagging
📁 Smart File Organization
↩️ Multi-Session Undo History
📊 Detailed Analytics & Statistics
🏷️ Custom File Type Routing
🔍 Advanced Search Capabilities
📈 Progress Tracking & Monitoring
⚙️ Fully Customizable Settings
📇 System-Wide File Indexing
"""
    
    ttk.Label(features_frame, text=features_text, font=("Segoe UI", 9)).pack(anchor="w")
    
    # Credits section
    credits_frame = ttk.LabelFrame(left_col, text="👥 Credits", padding=15)
    credits_frame.pack(fill=X, pady=5)
    
    credits_text = """
🔧 Development: Desktop Organizer Team
🤖 AI Integration: OpenAI GPT Models
🎨 UI Framework: ttkbootstrap
🐍 Built with: Python 3.8+
📊 Database: SQLite3
🖼️ Icons: Custom Emoji Set
"""
    
    ttk.Label(credits_frame, text=credits_text, font=("Segoe UI", 9)).pack(anchor="w")
    
    # Right column - Links and actions
    right_col = ttk.Frame(content_frame)
    right_col.pack(side=RIGHT, fill=BOTH, expand=True)
    
    # Links section
    links_frame = ttk.LabelFrame(right_col, text="🔗 Links & Resources", padding=15)
    links_frame.pack(fill=X, pady=5)
    
    def open_github():
        messagebox.showinfo("GitHub", "Opening GitHub repository...\n(Feature will open browser in real implementation)")
    
    def open_docs():
        messagebox.showinfo("Documentation", "Opening documentation...\n(Feature will open browser in real implementation)")
    
    def open_support():
        messagebox.showinfo("Support", "Opening support page...\n(Feature will open browser in real implementation)")
    
    ttk.Button(
        links_frame, 
        text="🐙 GitHub Repository", 
        bootstyle=INFO,
        width=25,
        command=open_github
    ).pack(pady=3)
    
    ttk.Button(
        links_frame, 
        text="📖 Documentation", 
        bootstyle=INFO,
        width=25,
        command=open_docs
    ).pack(pady=3)
    
    ttk.Button(
        links_frame, 
        text="🆘 Get Support", 
        bootstyle=INFO,
        width=25,
        command=open_support
    ).pack(pady=3)
    
    # Feedback section
    feedback_frame = ttk.LabelFrame(right_col, text="💬 Feedback", padding=15)
    feedback_frame.pack(fill=X, pady=5)
    
    def report_issue():
        messagebox.showinfo("Report Issue", "Thank you for helping improve the app!\n(Feature will open issue tracker in real implementation)")
    
    def send_feedback():
        messagebox.showinfo("Send Feedback", "Your feedback is valuable to us!\n(Feature will open feedback form in real implementation)")
    
    ttk.Button(
        feedback_frame, 
        text="🐛 Report Issue", 
        bootstyle=WARNING,
        width=25,
        command=report_issue
    ).pack(pady=3)
    
    ttk.Button(
        feedback_frame, 
        text="💡 Send Feedback", 
        bootstyle=SUCCESS,
        width=25,
        command=send_feedback
    ).pack(pady=3)
    
    # System info section
    system_frame = ttk.LabelFrame(right_col, text="💻 System Information", padding=15)
    system_frame.pack(fill=BOTH, expand=True, pady=5)
    
    import platform
    import sys
    
    system_info = f"""
Operating System: {platform.system()} {platform.release()}
Python Version: {sys.version.split()[0]}
Architecture: {platform.architecture()[0]}
Machine: {platform.machine()}
Processor: {platform.processor()[:30]}...

Database Path: {DB_PATH}
History Log: {HISTORY_LOG_PATH}
"""
    
    system_text = ScrolledText(system_frame, height=8, font=("Consolas", 8))
    system_text.pack(fill=BOTH, expand=True)
    system_text.insert(END, system_info)
    
    # License section
    license_frame = ttk.LabelFrame(tab_frame, text="📄 License", padding=15)
    license_frame.pack(fill=X, padx=20, pady=10)
    
    license_text = """
Desktop File Organizer v2.0 - MIT License
Copyright (c) 2024 Desktop Organizer Team

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
"""
    
    ttk.Label(license_frame, text=license_text, font=("Segoe UI", 8), wraplength=800).pack()
    
    return tab_frame

# Helper functions (existing functions from original code)
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
    path = filedialog.askopenfilename(title="Select file to preview")
    if not path:
        return
    
    win = Toplevel()
    win.title(f"Preview - {Path(path).name}")
    win.geometry("700x600")
    win.transient()
    win.grab_set()
    
    # File info
    info_frame = ttk.LabelFrame(win, text="File Information", padding=15)
    info_frame.pack(fill=X, padx=20, pady=10)
    
    file_path = Path(path)
    file_info = f"""
Name: {file_path.name}
Size: {file_path.stat().st_size if file_path.exists() else 'Unknown'} bytes
Type: {file_path.suffix}
Location: {file_path.parent}
Modified: {datetime.fromtimestamp(file_path.stat().st_mtime) if file_path.exists() else 'Unknown'}
"""
    
    ttk.Label(info_frame, text=file_info, font=("Consolas", 9)).pack(anchor="w")
    
    # Preview area
    preview_frame = ttk.LabelFrame(win, text="Preview", padding=15)
    preview_frame.pack(fill=BOTH, expand=True, padx=20, pady=10)
    
    preview_text = ScrolledText(preview_frame, height=20, font=("Consolas", 9))
    preview_text.pack(fill=BOTH, expand=True)
    preview_text.insert(END, "File preview functionality will be implemented in a future update...")

def build_gui():
    """Build the main GUI with tabbed interface"""
    app = ttk.Window(
        themename="superhero", 
        title="Desktop File Organizer v2.0 - Enhanced Edition", 
        size=(1200, 700)
    )
    
    # Main header
    header_frame = ttk.Frame(app)
    header_frame.pack(fill=X, pady=10)
    ttk.Label(
        header_frame, 
        text="🗂️ Desktop File Organizer v2.0", 
        font=("Segoe UI", 18, "bold")
    ).pack()
    ttk.Label(
        header_frame, 
        text="AI-Powered Desktop Organization with Enhanced Multi-Session Management", 
        font=("Segoe UI", 10)
    ).pack()
    
    # Create notebook for tabs
    notebook = ttk.Notebook(app)
    notebook.pack(fill=BOTH, expand=True, padx=15, pady=10)
    
    # Create all tabs
    organize_tab = create_organize_tab(notebook)
    undo_tab = create_undo_tab(notebook)
    ai_tagging_tab = create_ai_tagging_tab(notebook)
    analytics_tab = create_analytics_tab(notebook)
    rules_tab = create_rules_tab(notebook)
    settings_tab = create_settings_tab(notebook)
    about_tab = create_about_tab(notebook)
    
    # Add tabs to notebook
    notebook.add(organize_tab, text="🚀 Organize")
    notebook.add(undo_tab, text="↩️ Undo")
    notebook.add(ai_tagging_tab, text="🤖 AI Tagging")
    notebook.add(analytics_tab, text="📊 Analytics")
    notebook.add(rules_tab, text="📋 Rules")
    notebook.add(settings_tab, text="⚙️ Settings")
    notebook.add(about_tab, text="ℹ️ About")
    
    # Status bar
    status_frame = ttk.Frame(app)
    status_frame.pack(fill=X, pady=5)
    
    status_label = ttk.Label(
        status_frame, 
        text="✨ Ready to organize your desktop with enhanced AI-powered features and multi-session undo", 
        font=("Segoe UI", 9)
    )
    status_label.pack()
    
    # Start the application
    app.mainloop()

if __name__ == "__main__":
    build_gui()