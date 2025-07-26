import os
import shutil
import sqlite3
import csv
from pathlib import Path
from tkinter import filedialog, Toplevel, END, WORD, BOTH, LEFT, X
from PIL import Image, ImageTk
import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.widgets import Meter
from ttkbootstrap.constants import INFO, SUCCESS, PRIMARY, WARNING, SECONDARY, DANGER, LIGHT

from src.organizer import start_processing_threaded, regroup_by_tags, undo_last_cleanup_threaded, DB_PATH
from src.db import update_tags_in_db
from src.ai_tagger import get_batched_ai_tags, BATCH_SIZE, SKIP_TAGS
from src.ai_tagger import set_ai_enabled


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
    app = ttk.Window(themename="superhero", title="Desktop File Organizer", size=(900, 700))
    ttk.Label(app, text="Desktop File Organizer", font=("Segoe UI", 18, "bold")).pack(pady=15)

    log_area = ScrolledText(app, height=15, font=("Consolas", 10))
    log_area.pack(fill=BOTH, expand=True, padx=20, pady=10)

    # Enhanced meter with better styling
    meter = Meter(
        app, 
        bootstyle=INFO, 
        subtext="Ready to start", 
        textright="files", 
        amounttotal=100,
        amountused=0,
        stripethickness=4,
        showtext=True
    )
    meter.pack(fill=X, padx=20, pady=10)

    # Main buttons frame
    main_frame = ttk.Frame(app)
    main_frame.pack(pady=15)

    # Top row of buttons
    top_frame = ttk.Frame(main_frame)
    top_frame.pack(pady=5)

    ttk.Button(
        top_frame, 
        text="🚀 Start Organizing", 
        bootstyle=SUCCESS,
        width=20,
        command=lambda: start_processing_threaded(log_area, meter)
    ).pack(side=LEFT, padx=5)

    ttk.Button(
        top_frame, 
        text="🔄 Retag Missing Files", 
        bootstyle=INFO,
        width=20,
        command=lambda: retag_missing_entries_threaded(
            lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END), 
            meter
        )
    ).pack(side=LEFT, padx=5)

    ttk.Button(
        top_frame, 
        text="↩️ Undo Cleanup", 
        bootstyle=WARNING,
        width=20,
        command=lambda: undo_last_cleanup_threaded(
            lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END),
            meter
        )
    ).pack(side=LEFT, padx=5)

    # Bottom row of buttons
    bottom_frame = ttk.Frame(main_frame)
    bottom_frame.pack(pady=5)

    ttk.Button(
        bottom_frame, 
        text="🔍 Search Files", 
        bootstyle=PRIMARY, 
        width=15,
        command=open_search_window
    ).pack(side=LEFT, padx=5)

    ttk.Button(
        bottom_frame, 
        text="📊 Export to CSV", 
        bootstyle=SECONDARY, 
        width=15,
        command=export_to_csv
    ).pack(side=LEFT, padx=5)

    ttk.Button(
        bottom_frame, 
        text="👁️ Preview File", 
        bootstyle=LIGHT, 
        width=15,
        command=preview_file
    ).pack(side=LEFT, padx=5)

    ttk.Button(
        bottom_frame, 
        text="🏷️ Group by Tag", 
        bootstyle=DANGER, 
        width=15,
        command=regroup_by_tags
    ).pack(side=LEFT, padx=5)

    # AI toggle at the bottom
    ai_frame = ttk.Frame(app)
    ai_frame.pack(pady=10)
    
    ai_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(
        ai_frame, 
        text="🤖 Enable AI Tagging", 
        variable=ai_var,
        command=lambda: set_ai_enabled(ai_var.get())
    ).pack()

    # Status label
    status_label = ttk.Label(app, text="Ready to organize your desktop files", font=("Segoe UI", 10))
    status_label.pack(pady=(0, 10))

    app.mainloop()