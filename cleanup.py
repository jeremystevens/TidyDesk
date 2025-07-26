# smart3.py - Advanced File Organizer with Tagging, Search, Export, Preview

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import openai
import json
import csv
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.widgets import Meter
from tkinter import filedialog, Toplevel, Text, PhotoImage
from PIL import Image, ImageTk
from textwrap import dedent
from dotenv import load_dotenv
import os
import json

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
# CONFIG
ENABLE_AI_TAGS = True
BATCH_SIZE = 50
SKIP_TAGS = {"image", "video", "audio"}
with open("config.json", "r", encoding="utf-8") as f:
    ALLOWED_EXTENSIONS = json.load(f)["ALLOWED_EXTENSIONS"]
USER = os.getlogin()
DESKTOP = Path(f"C:/Users/{USER}/Desktop")
ORGANIZED = Path(f"C:/Users/{USER}/Organized")
DB_PATH = Path("file_index.db")

# --- Helpers ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT,
            new_path TEXT,
            file_type TEXT,
            moved_at TEXT,
            tags TEXT
        )''')
        conn.commit()

def get_category(extension):
    for category, ext_list in ALLOWED_EXTENSIONS.items():
        if extension.lower() in ext_list:
            return category
    return None

def get_batched_ai_tags(file_names):
    if not ENABLE_AI_TAGS or not file_names:
        return {}

    prompt = dedent(f"""
        You will receive a list of 50 filenames.
        Return a JSON array where each object contains:
        - name: the filename
        - tags: a list of 2–5 descriptive tags (single words only)

        Example: 
        [
          {{"name": "invoice_2023_q1.pdf", "tags": ["invoice", "finance", "Q1"]}},
          ...
        ]

        Filenames:
        {chr(10).join(file_names)}
    """)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response['choices'][0]['message']['content']

        print("\n🔍 AI RAW RESPONSE:\n")
        print(content[:1000])

        with open("openai_log.json", "a", encoding="utf-8") as f:
            f.write(content + "\n\n")

        parsed = json.loads(content)
        return {entry["name"].strip().lower(): ", ".join(entry["tags"]) for entry in parsed}
    except Exception as e:
        print(f"OpenAI error during batch tagging: {e}")
        return {}

def insert_into_db(original_name, new_path, file_type, tags):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO files (original_name, new_path, file_type, moved_at, tags) VALUES (?, ?, ?, ?, ?)',
                  (original_name, new_path, file_type, datetime.now().isoformat(), tags))
        conn.commit()

def update_tags_in_db(filename, tags):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('UPDATE files SET tags = ? WHERE original_name = ?', (tags, filename))
        conn.commit()

def process_batch(file_paths, tag_map, log_callback):
    for file_path in file_paths:
        if file_path.is_dir():
            dest_folder = ORGANIZED / "Misc" / "Folders" / file_path.name
            try:
                shutil.move(str(file_path), str(dest_folder))
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
            tags = tag_map.get(file_path.name.strip().lower(), "")
            print(f"📦 File: {file_path.name} | Tags found: {tags}")
            insert_into_db(file_path.name, str(new_path), file_path.suffix or "unknown", tags)
            log_callback(f"📄 Moved: {file_path.name} → {dest_folder.name} | Tags: {tags}")
        except Exception as e:
            log_callback(f"❌ Error moving {file_path.name}: {e}")

def retag_missing_entries(log_callback, meter):
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

def start_processing(log_area):
    all_files = [f for f in DESKTOP.iterdir() if f.name != "Organized"]

    def log_callback(msg):
        log_area.insert(END, f"{msg}\n")
        log_area.see(END)
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

# --- Search UI ---
def open_search_window():
    win = Toplevel()
    win.title("Search Files")
    win.geometry("700x500")

    result_area = ScrolledText(win, height=25)
    result_area.pack(fill=BOTH, expand=True, padx=10, pady=10)

    entry = ttk.Entry(win, width=40)
    entry.pack(pady=5)

    def search():
        query = entry.get().lower()
        result_area.delete(1.0, END)
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT original_name, new_path, tags FROM files")
            results = [row for row in c.fetchall() if query in row[0].lower() or query in (row[2] or '').lower()]
            for r in results:
                result_area.insert(END, f"{r[0]}\n→ {r[1]}\nTags: {r[2]}\n\n")

    ttk.Button(win, text="Search", command=search).pack()

# --- CSV Export ---
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

# --- File Preview ---
def preview_file():
    path = filedialog.askopenfilename()
    if not path:
        return
    win = Toplevel()
    win.title("Preview")
    win.geometry("700x600")

    ext = Path(path).suffix.lower()
    if ext in ['.txt', '.md', '.py', '.json', '.csv']:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        box = ScrolledText(win, wrap=WORD)
        box.insert(END, content)
        box.pack(fill=BOTH, expand=True)
    elif ext in ['.jpg', '.jpeg', '.png', '.gif']:
        img = Image.open(path)
        img.thumbnail((600, 500))
        photo = ImageTk.PhotoImage(img)
        label = ttk.Label(win, image=photo)
        label.image = photo
        label.pack()
    elif ext == '.pdf':
        ttk.Label(win, text="PDF preview not implemented. Use external viewer.", font=("Segoe UI", 12)).pack(pady=20)
    else:
        ttk.Label(win, text="Unsupported preview type.").pack(pady=20)

# --- Tag-based Folder Grouping ---
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

# --- GUI Layout ---
def build_gui():
    app = ttk.Window(themename="superhero", title="Desktop File Organizer", size=(850, 600))
    ttk.Label(app, text="Live File Organizer Log", font=("Segoe UI", 16, "bold")).pack(pady=10)

    log_area = ScrolledText(app, height=15, font=("Consolas", 10))
    log_area.pack(fill=BOTH, expand=True, padx=20, pady=10)

    meter = Meter(app, bootstyle=INFO, subtext="Tagging Progress", textright="files", amounttotal=1)
    meter.pack(fill=X, padx=20, pady=5)

    frame = ttk.Frame(app)
    frame.pack(pady=10)

    ttk.Button(frame, text="Start Organizing", bootstyle=SUCCESS, command=lambda: start_processing(log_area)).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Retag Missing Files", bootstyle=INFO, command=lambda: retag_missing_entries(lambda msg: log_area.insert(END, msg + "\n") or log_area.see(END), meter)).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Search Files", bootstyle=PRIMARY, command=open_search_window).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Export to CSV", bootstyle=WARNING, command=export_to_csv).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Preview File", bootstyle=SECONDARY, command=preview_file).pack(side=LEFT, padx=5)
    ttk.Button(frame, text="Group by Tag", bootstyle=DANGER, command=regroup_by_tags).pack(side=LEFT, padx=5)

    app.mainloop()

if __name__ == "__main__":
    init_db()
    build_gui()
