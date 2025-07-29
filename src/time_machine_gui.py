
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from datetime import datetime
from pathlib import Path

from src.time_machine import time_machine

class TimeMachineWindow:
    """GUI window for Time Machine functionality"""
    
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("🕰️ Filesystem Time Machine")
        self.window.geometry("1000x700")
        self.window.transient(parent)
        
        # Make window modal
        self.window.grab_set()
        
        self.setup_ui()
        self.refresh_data()
        
        # Center window on parent
        self.window.geometry("+%d+%d" % (
            parent.winfo_rootx() + 50,
            parent.winfo_rooty() + 50
        ))

    def setup_ui(self):
        """Setup the user interface"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Watched Folders Tab
        self.setup_watched_folders_tab(notebook)
        
        # Snapshots Tab
        self.setup_snapshots_tab(notebook)
        
        # Compare Tab
        self.setup_compare_tab(notebook)
        
        # Settings Tab
        self.setup_settings_tab(notebook)

    def setup_watched_folders_tab(self, notebook):
        """Setup watched folders management tab"""
        folder_frame = ttk.Frame(notebook)
        notebook.add(folder_frame, text="📂 Watched Folders")
        
        # Control frame
        control_frame = ttk.Frame(folder_frame)
        control_frame.pack(fill=X, padx=10, pady=5)
        
        ttk.Button(control_frame, text="➕ Add Folder", 
                  command=self.add_watched_folder).pack(side=LEFT, padx=5)
        ttk.Button(control_frame, text="➖ Remove", 
                  command=self.remove_watched_folder).pack(side=LEFT, padx=5)
        ttk.Button(control_frame, text="📸 Create Snapshot", 
                  command=self.create_manual_snapshot).pack(side=LEFT, padx=5)
        
        # Separator
        ttk.Separator(control_frame, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)
        
        # Auto snapshot controls
        self.auto_status_label = ttk.Label(control_frame, text="⚫ Auto: OFF")
        self.auto_status_label.pack(side=LEFT, padx=5)
        
        ttk.Button(control_frame, text="▶️ Start Auto", 
                  command=self.start_auto_snapshots).pack(side=LEFT, padx=5)
        ttk.Button(control_frame, text="⏹️ Stop Auto", 
                  command=self.stop_auto_snapshots).pack(side=LEFT, padx=5)
        
        # Folders list
        self.folders_tree = ttk.Treeview(folder_frame, columns=("path", "added", "last_snapshot"), 
                                        show="headings", height=15)
        
        self.folders_tree.heading("path", text="Folder Path")
        self.folders_tree.heading("added", text="Added")
        self.folders_tree.heading("last_snapshot", text="Last Snapshot")
        
        self.folders_tree.column("path", width=400)
        self.folders_tree.column("added", width=150)
        self.folders_tree.column("last_snapshot", width=150)
        
        folders_scrollbar = ttk.Scrollbar(folder_frame, orient=VERTICAL, 
                                         command=self.folders_tree.yview)
        self.folders_tree.configure(yscrollcommand=folders_scrollbar.set)
        
        self.folders_tree.pack(side=LEFT, fill=BOTH, expand=True, padx=(10, 0), pady=5)
        folders_scrollbar.pack(side=RIGHT, fill=Y, padx=(0, 10), pady=5)

    def setup_snapshots_tab(self, notebook):
        """Setup snapshots browsing tab"""
        snapshot_frame = ttk.Frame(notebook)
        notebook.add(snapshot_frame, text="📸 Snapshots")
        
        # Control frame
        control_frame = ttk.Frame(snapshot_frame)
        control_frame.pack(fill=X, padx=10, pady=5)
        
        ttk.Label(control_frame, text="Filter by folder:").pack(side=LEFT, padx=5)
        
        self.folder_filter_var = tk.StringVar()
        self.folder_filter_combo = ttk.Combobox(control_frame, textvariable=self.folder_filter_var,
                                               width=40, state="readonly")
        self.folder_filter_combo.pack(side=LEFT, padx=5)
        self.folder_filter_combo.bind("<<ComboboxSelected>>", self.filter_snapshots)
        
        ttk.Button(control_frame, text="🔄 Refresh", 
                  command=self.refresh_snapshots).pack(side=LEFT, padx=5)
        ttk.Button(control_frame, text="🗑️ Delete", 
                  command=self.delete_snapshot).pack(side=LEFT, padx=5)
        ttk.Button(control_frame, text="↩️ Restore", 
                  command=self.restore_snapshot).pack(side=LEFT, padx=5)
        
        # Snapshots list
        self.snapshots_tree = ttk.Treeview(snapshot_frame, 
                                          columns=("folder", "created", "files", "size"), 
                                          show="headings", height=15)
        
        self.snapshots_tree.heading("folder", text="Folder")
        self.snapshots_tree.heading("created", text="Created")
        self.snapshots_tree.heading("files", text="Files")
        self.snapshots_tree.heading("size", text="Size")
        
        self.snapshots_tree.column("folder", width=300)
        self.snapshots_tree.column("created", width=150)
        self.snapshots_tree.column("files", width=80)
        self.snapshots_tree.column("size", width=100)
        
        snapshots_scrollbar = ttk.Scrollbar(snapshot_frame, orient=VERTICAL, 
                                          command=self.snapshots_tree.yview)
        self.snapshots_tree.configure(yscrollcommand=snapshots_scrollbar.set)
        
        self.snapshots_tree.pack(side=LEFT, fill=BOTH, expand=True, padx=(10, 0), pady=5)
        snapshots_scrollbar.pack(side=RIGHT, fill=Y, padx=(0, 10), pady=5)
        
        # Double-click to browse snapshot
        self.snapshots_tree.bind("<Double-1>", self.browse_snapshot)

    def setup_compare_tab(self, notebook):
        """Setup snapshot comparison tab"""
        compare_frame = ttk.Frame(notebook)
        notebook.add(compare_frame, text="🔍 Compare")
        
        # Selection frame
        selection_frame = ttk.Frame(compare_frame)
        selection_frame.pack(fill=X, padx=10, pady=5)
        
        # Left snapshot selection
        left_frame = ttk.LabelFrame(selection_frame, text="Snapshot 1")
        left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        
        self.left_snapshot_var = tk.StringVar()
        self.left_snapshot_combo = ttk.Combobox(left_frame, textvariable=self.left_snapshot_var,
                                               state="readonly")
        self.left_snapshot_combo.pack(fill=X, padx=5, pady=5)
        
        # Right snapshot selection
        right_frame = ttk.LabelFrame(selection_frame, text="Snapshot 2")
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=5)
        
        self.right_snapshot_var = tk.StringVar()
        self.right_snapshot_combo = ttk.Combobox(right_frame, textvariable=self.right_snapshot_var,
                                                state="readonly")
        self.right_snapshot_combo.pack(fill=X, padx=5, pady=5)
        
        # Compare button
        compare_btn_frame = ttk.Frame(compare_frame)
        compare_btn_frame.pack(fill=X, padx=10, pady=5)
        
        ttk.Button(compare_btn_frame, text="🔍 Compare Snapshots", 
                  command=self.compare_snapshots).pack()
        
        # Results frame
        results_frame = ttk.Frame(compare_frame)
        results_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # Create notebook for different change types
        self.compare_notebook = ttk.Notebook(results_frame)
        self.compare_notebook.pack(fill=BOTH, expand=True)
        
        # Summary tab
        self.summary_text = tk.Text(self.compare_notebook, height=5, wrap=tk.WORD)
        self.compare_notebook.add(self.summary_text, text="📊 Summary")
        
        # Added files tab
        self.added_tree = ttk.Treeview(self.compare_notebook, columns=("path", "size"), 
                                      show="headings")
        self.added_tree.heading("path", text="File Path")
        self.added_tree.heading("size", text="Size")
        self.compare_notebook.add(self.added_tree, text="➕ Added")
        
        # Removed files tab
        self.removed_tree = ttk.Treeview(self.compare_notebook, columns=("path", "size"), 
                                        show="headings")
        self.removed_tree.heading("path", text="File Path")
        self.removed_tree.heading("size", text="Size")
        self.compare_notebook.add(self.removed_tree, text="➖ Removed")
        
        # Modified files tab
        self.modified_tree = ttk.Treeview(self.compare_notebook, 
                                         columns=("path", "old_size", "new_size"), 
                                         show="headings")
        self.modified_tree.heading("path", text="File Path")
        self.modified_tree.heading("old_size", text="Old Size")
        self.modified_tree.heading("new_size", text="New Size")
        self.compare_notebook.add(self.modified_tree, text="📝 Modified")

    def setup_settings_tab(self, notebook):
        """Setup settings tab"""
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="⚙️ Settings")
        
        # Interval setting
        interval_frame = ttk.LabelFrame(settings_frame, text="Snapshot Interval")
        interval_frame.pack(fill=X, padx=10, pady=10)
        
        ttk.Label(interval_frame, text="Automatic snapshot interval (minutes):").pack(anchor=W, padx=5, pady=5)
        
        self.interval_var = tk.StringVar(value=str(time_machine.snapshot_interval // 60))
        interval_spinbox = ttk.Spinbox(interval_frame, from_=1, to=1440, 
                                      textvariable=self.interval_var, width=10)
        interval_spinbox.pack(anchor=W, padx=5, pady=5)
        
        ttk.Button(interval_frame, text="Apply", 
                  command=self.apply_interval).pack(anchor=W, padx=5, pady=5)
        
        # Statistics
        stats_frame = ttk.LabelFrame(settings_frame, text="Statistics")
        stats_frame.pack(fill=X, padx=10, pady=10)
        
        self.stats_text = tk.Text(stats_frame, height=10, wrap=tk.WORD)
        self.stats_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        ttk.Button(stats_frame, text="🔄 Refresh Stats", 
                  command=self.refresh_stats).pack(pady=5)

    def add_watched_folder(self):
        """Add a folder to be watched"""
        folder = filedialog.askdirectory(title="Select folder to watch")
        if folder:
            if time_machine.add_watched_folder(folder):
                self.refresh_watched_folders()
                messagebox.showinfo("Success", f"Added folder to Time Machine:\n{folder}")
            else:
                messagebox.showerror("Error", "Failed to add folder")

    def remove_watched_folder(self):
        """Remove selected watched folder"""
        selection = self.folders_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a folder to remove")
            return
        
        item = self.folders_tree.item(selection[0])
        folder_path = item['values'][0]
        
        if messagebox.askyesno("Confirm", f"Remove folder from Time Machine?\n{folder_path}"):
            if time_machine.remove_watched_folder(folder_path):
                self.refresh_watched_folders()
                messagebox.showinfo("Success", "Folder removed from Time Machine")
            else:
                messagebox.showerror("Error", "Failed to remove folder")

    def create_manual_snapshot(self):
        """Create a manual snapshot of selected folder"""
        selection = self.folders_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a folder to snapshot")
            return
        
        item = self.folders_tree.item(selection[0])
        folder_path = item['values'][0]
        
        snapshot_id = time_machine.create_snapshot(folder_path)
        if snapshot_id:
            self.refresh_data()
            messagebox.showinfo("Success", f"Snapshot created successfully!\nSnapshot ID: {snapshot_id}")
        else:
            messagebox.showerror("Error", "Failed to create snapshot")

    def start_auto_snapshots(self):
        """Start automatic snapshots"""
        time_machine.start_auto_snapshots()
        self.auto_status_label.config(text="🔴 Auto: ON")

    def stop_auto_snapshots(self):
        """Stop automatic snapshots"""
        time_machine.stop_auto_snapshots()
        self.auto_status_label.config(text="⚫ Auto: OFF")

    def refresh_watched_folders(self):
        """Refresh watched folders list"""
        # Clear current items
        for item in self.folders_tree.get_children():
            self.folders_tree.delete(item)
        
        # Load watched folders
        folders = time_machine.get_watched_folders()
        for folder in folders:
            added_date = "Never" if not folder['added_at'] else \
                        datetime.fromisoformat(folder['added_at']).strftime("%Y-%m-%d %H:%M")
            last_snapshot = "Never" if not folder['last_snapshot'] else \
                           datetime.fromisoformat(folder['last_snapshot']).strftime("%Y-%m-%d %H:%M")
            
            self.folders_tree.insert("", "end", values=(
                folder['path'], added_date, last_snapshot))

    def refresh_snapshots(self):
        """Refresh snapshots list"""
        # Clear current items
        for item in self.snapshots_tree.get_children():
            self.snapshots_tree.delete(item)
        
        # Load snapshots
        snapshots = time_machine.get_snapshots()
        
        # Update folder filter combo
        folders = list(set(s['folder_path'] for s in snapshots))
        folders.sort()
        self.folder_filter_combo['values'] = ["All Folders"] + folders
        if not self.folder_filter_var.get():
            self.folder_filter_var.set("All Folders")
        
        # Update snapshot combos for comparison
        snapshot_names = [f"{s['id']}: {s['snapshot_name']}" for s in snapshots]
        self.left_snapshot_combo['values'] = snapshot_names
        self.right_snapshot_combo['values'] = snapshot_names
        
        # Filter snapshots if needed
        filter_folder = self.folder_filter_var.get()
        if filter_folder and filter_folder != "All Folders":
            snapshots = [s for s in snapshots if s['folder_path'] == filter_folder]
        
        # Populate tree
        for snapshot in snapshots:
            created_date = datetime.fromisoformat(snapshot['created_at']).strftime("%Y-%m-%d %H:%M")
            size_mb = snapshot['total_size'] / (1024 * 1024) if snapshot['total_size'] else 0
            
            self.snapshots_tree.insert("", "end", values=(
                Path(snapshot['folder_path']).name,
                created_date,
                snapshot['file_count'],
                f"{size_mb:.1f} MB"
            ), tags=(snapshot['id'],))

    def filter_snapshots(self, event=None):
        """Filter snapshots by selected folder"""
        self.refresh_snapshots()

    def delete_snapshot(self):
        """Delete selected snapshot"""
        selection = self.snapshots_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a snapshot to delete")
            return
        
        # Get snapshot ID from tags
        snapshot_id = self.snapshots_tree.item(selection[0])['tags'][0]
        
        if messagebox.askyesno("Confirm", "Delete this snapshot?\nThis action cannot be undone."):
            # Implementation would go here - deleting from database and filesystem
            messagebox.showinfo("Info", "Snapshot deletion feature coming soon!")

    def restore_snapshot(self):
        """Restore selected snapshot"""
        selection = self.snapshots_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a snapshot to restore")
            return
        
        snapshot_id = self.snapshots_tree.item(selection[0])['tags'][0]
        
        # Ask for destination
        destination = filedialog.askdirectory(title="Select destination for restored files")
        if destination:
            if time_machine.restore_snapshot(int(snapshot_id), destination):
                messagebox.showinfo("Success", f"Snapshot restored to:\n{destination}")
            else:
                messagebox.showerror("Error", "Failed to restore snapshot")

    def browse_snapshot(self, event):
        """Browse snapshot contents (placeholder)"""
        selection = self.snapshots_tree.selection()
        if selection:
            messagebox.showinfo("Info", "Snapshot browsing feature coming soon!")

    def compare_snapshots(self):
        """Compare two selected snapshots"""
        left_selection = self.left_snapshot_var.get()
        right_selection = self.right_snapshot_var.get()
        
        if not left_selection or not right_selection:
            messagebox.showwarning("Warning", "Please select two snapshots to compare")
            return
        
        # Extract snapshot IDs
        left_id = int(left_selection.split(":")[0])
        right_id = int(right_selection.split(":")[0])
        
        # Get comparison results
        diff = time_machine.compare_snapshots(left_id, right_id)
        
        if not diff:
            messagebox.showerror("Error", "Failed to compare snapshots")
            return
        
        # Update summary
        self.summary_text.delete(1.0, tk.END)
        summary = diff['summary']
        summary_text = f"""Comparison Summary:
        
Added Files: {summary['added_count']}
Removed Files: {summary['removed_count']}
Modified Files: {summary['modified_count']}
Unchanged Files: {summary['unchanged_count']}
        """
        self.summary_text.insert(1.0, summary_text)
        
        # Clear and populate trees
        for tree in [self.added_tree, self.removed_tree, self.modified_tree]:
            for item in tree.get_children():
                tree.delete(item)
        
        # Added files
        for file_info in diff['added']:
            size_kb = file_info['size'] / 1024
            self.added_tree.insert("", "end", values=(
                file_info['path'], f"{size_kb:.1f} KB"))
        
        # Removed files
        for file_info in diff['removed']:
            size_kb = file_info['size'] / 1024
            self.removed_tree.insert("", "end", values=(
                file_info['path'], f"{size_kb:.1f} KB"))
        
        # Modified files
        for file_info in diff['modified']:
            old_kb = file_info['old_size'] / 1024
            new_kb = file_info['new_size'] / 1024
            self.modified_tree.insert("", "end", values=(
                file_info['path'], f"{old_kb:.1f} KB", f"{new_kb:.1f} KB"))

    def apply_interval(self):
        """Apply new snapshot interval"""
        try:
            minutes = int(self.interval_var.get())
            seconds = minutes * 60
            time_machine.set_snapshot_interval(seconds)
            messagebox.showinfo("Success", f"Snapshot interval set to {minutes} minutes")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number")

    def refresh_stats(self):
        """Refresh statistics display"""
        stats = time_machine.get_statistics()
        
        stats_text = f"""Time Machine Statistics:

Total Snapshots: {stats.get('total_snapshots', 0)}
Total Files Tracked: {stats.get('total_files', 0):,}
Logical Size: {stats.get('total_logical_size', 0) / (1024**3):.2f} GB
Disk Usage: {stats.get('disk_usage', 0) / (1024**2):.1f} MB
Watched Folders: {stats.get('watched_folders', 0)}

Auto Snapshots: {'Running' if stats.get('is_running', False) else 'Stopped'}
Snapshot Interval: {stats.get('snapshot_interval', 0) // 60} minutes
        """
        
        self.stats_text.delete(1.0, tk.END)
        self.stats_text.insert(1.0, stats_text)

    def refresh_data(self):
        """Refresh all data in the window"""
        self.refresh_watched_folders()
        self.refresh_snapshots()
        self.refresh_stats()
        
        # Update auto status
        if time_machine.is_running:
            self.auto_status_label.config(text="🔴 Auto: ON")
        else:
            self.auto_status_label.config(text="⚫ Auto: OFF")

def show_time_machine_window(parent):
    """Show the Time Machine window"""
    return TimeMachineWindow(parent)
