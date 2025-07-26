import os
import shutil
import sqlite3
from pathlib import Path
from tkinter import filedialog, Toplevel, END, WORD, BOTH, LEFT, X
from PIL import Image, ImageTk
import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.widgets import Meter
from ttkbootstrap.constants import INFO, SUCCESS, PRIMARY, WARNING, SECONDARY, DANGER, LIGHT

from src.organizer import start_processing, regroup_by_tags, undo_last_cleanup
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

def build_gui():
    app = ttk.Window(themename="superhero", title="Desktop File Organizer", size=(850, 600))
    ttk.Label(app, text="Live File Organizer Log", font=("Segoe UI", 16, "bold")).pack(pady=10)


def retag_missing_entries(log_callback, meter):
    import sqlite3
    from src.db import update_tags_in_db
    from src.ai_tagger import get_batched_ai_tags, BATCH_SIZE, SKIP_TAGS
    from src.organizer import DB_PATH

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT original_name, new_path, tags FROM files")
        rows = c.fetchall()

    missing = [row for row in rows if not row[2] or not set(row[2].split(", ")).isdisjoint(SKIP_TAGS) == False]
    if not missing:
        log_callback("✅ No files need retagging.")
        return

    meter.configure(amounttotal=len(missing), amountused=0)

    for i in range(0, len(missing), BATCH_SIZE):
        batch = missing[i:i+BATCH_SIZE]
        filenames = [row[0] for row in batch]
        tag_map = get_batched_ai_tags(filenames)

        for idx, name in enumerate(filenames):
            tags = tag_map.get(name.strip().lower(), "")
            if tags:
                update_tags_in_db(name, tags)
                log_callback(f"🔁 Retagged: {name} | Tags: {tags}")
            else:
                log_callback(f"⚠️ No tags found for: {name}")
            meter.step()

    log_callback("✅ Retagging complete.")

def build_gui():
    from tkinter import END
    app = ttk.Window(themename="superhero", title="Desktop File Organizer", size=(850, 600))
    ttk.Label(app, text="Live File Organizer Log", font=("Segoe UI", 16, "bold")).pack(pady=10)

    log_area = ScrolledText(app, height=15, font=("Consolas", 10))
    log_area.pack(fill=BOTH, expand=True, padx=20, pady=10)

    meter = Meter(app, bootstyle=INFO, subtext="Tagging Progress", textright="files", amounttotal=1)
    meter.pack(fill=X, padx=20, pady=5)

    frame = ttk.Frame(app)
    frame.pack(pady=10)

    ttk.Button(frame, text="Start Organizing", bootstyle=SUCCESS,
               command=lambda: start_processing(log_area)).pack(side=LEFT, padx=5)

    ttk.Button(frame, text="Retag Missing Files", bootstyle=INFO,
               command=lambda: retag_missing_entries(lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END), meter)).pack(side=LEFT, padx=5)

    ttk.Button(frame, text="Search Files", bootstyle=PRIMARY, command=open_search_window).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Export to CSV", bootstyle=WARNING, command=export_to_csv).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Preview File", bootstyle=SECONDARY, command=preview_file).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Group by Tag", bootstyle=DANGER, command=regroup_by_tags).pack(side=LEFT, padx=5)


    ttk.Button(frame, text="Undo Cleanup", bootstyle=LIGHT,
               command=lambda: undo_last_cleanup(lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END))).pack(side=LEFT, padx=5)
    ai_var = ttk.BooleanVar(value=True)
    ttk.Checkbutton(app, text="Enable AI Tagging", variable=ai_var,
                command=lambda: set_ai_enabled(ai_var.get())).pack(pady=(0, 10))
    app.mainloop()