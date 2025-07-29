"""
Enhanced Search GUI Integration
Replace the open_search_window function in gui.py with this implementation
"""

import tkinter as tk
from tkinter import filedialog, messagebox, END
import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.constants import INFO, SUCCESS, PRIMARY, WARNING, SECONDARY, DANGER
from datetime import datetime, timedelta
from pathlib import Path
import os
import subprocess
import platform


# Import your search module
from src.search_module import FileSearcher, SearchFilter, format_search_results, export_search_results

def open_search_window():
    """Enhanced search window with full functionality"""
    
    # Initialize searcher
    searcher = FileSearcher()
    
    # Create main window
    search_window = ttk.Toplevel()
    search_window.title("🔍 Advanced File Search")
    search_window.geometry("1000x700")
    search_window.transient()
    search_window.grab_set()
    
    # Variables for search criteria
    name_var = ttk.StringVar()
    tags_var = ttk.StringVar()
    file_type_var = ttk.StringVar()
    exact_match_var = ttk.BooleanVar()
    case_sensitive_var = ttk.BooleanVar()
    date_enabled_var = ttk.BooleanVar()
    date_from_var = ttk.StringVar()
    date_to_var = ttk.StringVar()
    regex_mode_var = ttk.BooleanVar()
    
    # Current search results
    current_results = []
    
    # Header
    header_frame = ttk.Frame(search_window)
    header_frame.pack(fill="x", padx=20, pady=10)
    
    ttk.Label(
        header_frame, 
        text="🔍 Advanced File Search", 
        font=("Segoe UI", 16, "bold")
    ).pack()
    
    ttk.Label(
        header_frame, 
        text="Search through your organized files with powerful filters and options", 
        font=("Segoe UI", 10)
    ).pack()
    
    # Create notebook for search tabs
    notebook = ttk.Notebook(search_window)
    notebook.pack(fill="both", expand=True, padx=20, pady=10)
    
    # === BASIC SEARCH TAB ===
    basic_tab = ttk.Frame(notebook)
    notebook.add(basic_tab, text="🔍 Basic Search")
    
    # Basic search controls
    basic_controls_frame = ttk.LabelFrame(basic_tab, text="Search Criteria", padding=15)
    basic_controls_frame.pack(fill="x", padx=10, pady=10)
    
    # # Quick search
    # quick_frame = ttk.Frame(basic_controls_frame)
    # quick_frame.pack(fill="x", pady=5)
    # ttk.Label(quick_frame, text="Quick Search:", width=15).pack(side="left")
    # quick_entry = ttk.Entry(quick_frame, width=40)
    # quick_entry.pack(side="left", padx=5)
    
    # def quick_search():
    #     query = quick_entry.get().strip()
    #     if not query:
    #         messagebox.showwarning("Empty Query", "Please enter a search term.")
    #         return
        
    #     update_status("Searching...")
    #     results = searcher.quick_search(query)
    #     display_results(results)
    #     update_status(f"Found {len(results)} files")
    
    # ttk.Button(
    #     quick_frame, 
    #     text="🚀 Quick Search", 
    #     bootstyle=SUCCESS,
    #     command=quick_search
    # ).pack(side="left", padx=5)
    
    # File name search
    name_frame = ttk.Frame(basic_controls_frame)
    name_frame.pack(fill="x", pady=5)
    ttk.Label(name_frame, text="File Name:", width=15).pack(side="left")
    name_entry = ttk.Entry(name_frame, textvariable=name_var, width=40)
    name_entry.pack(side="left", padx=5)
    
    # Tags search
    tags_frame = ttk.Frame(basic_controls_frame)
    tags_frame.pack(fill="x", pady=5)
    ttk.Label(tags_frame, text="Tags:", width=15).pack(side="left")
    tags_entry = ttk.Entry(tags_frame, textvariable=tags_var, width=40)
    tags_entry.pack(side="left", padx=5)
    
    # File type search with dropdown
    type_frame = ttk.Frame(basic_controls_frame)
    type_frame.pack(fill="x", pady=5)
    ttk.Label(type_frame, text="File Type:", width=15).pack(side="left")
    
    # Get available file types from both tables
    file_types = [""] + searcher.get_all_file_types(include_file_index=True)
    file_type_combo = ttk.Combobox(
        type_frame, 
        textvariable=file_type_var, 
        values=file_types,
        width=37
    )
    file_type_combo.pack(side="left", padx=5)
    
    # Search options
    options_frame = ttk.LabelFrame(basic_controls_frame, text="Search Options", padding=10)
    options_frame.pack(fill="x", pady=10)
    
    options_left = ttk.Frame(options_frame)
    options_left.pack(side="left", fill="x", expand=True)
    
    ttk.Checkbutton(
        options_left, 
        text="Exact match", 
        variable=exact_match_var
    ).pack(anchor="w", pady=2)
    
    ttk.Checkbutton(
        options_left, 
        text="Case sensitive", 
        variable=case_sensitive_var
    ).pack(anchor="w", pady=2)
    
    ttk.Checkbutton(
        options_left, 
        text="Regular expressions", 
        variable=regex_mode_var
    ).pack(anchor="w", pady=2)
    
    # Date range controls
    date_frame = ttk.Frame(options_frame)
    date_frame.pack(side="right")
    
    ttk.Checkbutton(
        date_frame, 
        text="Date range:", 
        variable=date_enabled_var
    ).pack(anchor="w")
    
    date_controls = ttk.Frame(date_frame)
    date_controls.pack(fill="x", pady=5)
    
    ttk.Label(date_controls, text="From:", width=5).pack(side="left")
    date_from_entry = ttk.Entry(date_controls, textvariable=date_from_var, width=12)
    date_from_entry.pack(side="left", padx=2)
    
    ttk.Label(date_controls, text="To:", width=3).pack(side="left", padx=(10,0))
    date_to_entry = ttk.Entry(date_controls, textvariable=date_to_var, width=12)
    date_to_entry.pack(side="left", padx=2)
    
    # Set default dates
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    date_from_var.set(week_ago.strftime("%Y-%m-%d"))
    date_to_var.set(today.strftime("%Y-%m-%d"))
    
    # === ADVANCED SEARCH TAB ===
    advanced_tab = ttk.Frame(notebook)
    notebook.add(advanced_tab, text="⚙️ Advanced")
    
    # Saved searches
    saved_frame = ttk.LabelFrame(advanced_tab, text="Quick Filters", padding=15)
    saved_frame.pack(fill="x", padx=10, pady=10)
    
    quick_filters_frame = ttk.Frame(saved_frame)
    quick_filters_frame.pack(fill="x")
    
    def filter_recent_files():
        results = (SearchFilter()
                  .last_days(7)
                  .search(searcher))
        display_results(results)
        update_status(f"Recent files: {len(results)} found")
    
    def filter_untagged_files():
        results = searcher.search_files(tags_pattern="^$")  # Empty tags
        display_results(results)
        update_status(f"Untagged files: {len(results)} found")
    
    def filter_large_files():
        # This would need file size info in database
        messagebox.showinfo("Filter", "Large files filter will be available when file size tracking is added to the database.")
    
    ttk.Button(
        quick_filters_frame, 
        text="📅 Last 7 Days", 
        bootstyle=INFO,
        command=filter_recent_files
    ).pack(side="left", padx=5)
    
    ttk.Button(
        quick_filters_frame, 
        text="🏷️ Untagged", 
        bootstyle=WARNING,
        command=filter_untagged_files
    ).pack(side="left", padx=5)
    
    ttk.Button(
        quick_filters_frame, 
        text="📊 Large Files", 
        bootstyle=SECONDARY,
        command=filter_large_files
    ).pack(side="left", padx=5)
    
    # Tag suggestions
    tag_suggestions_frame = ttk.LabelFrame(advanced_tab, text="Available Tags", padding=15)
    tag_suggestions_frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    # Get all tags and display them
    all_tags = searcher.get_all_tags()
    
    tags_text = ScrolledText(tag_suggestions_frame, height=8, font=("Consolas", 9))
    tags_text.pack(fill="both", expand=True)
    
    if all_tags:
        tags_text.insert("1.0", "Click on any tag to search:\n\n")
        for i, tag in enumerate(all_tags):
            if i > 0 and i % 8 == 0:  # New line every 8 tags
                tags_text.insert("end", "\n")
            
            # Create clickable tag
            start_pos = tags_text.index("end-1c")
            tags_text.insert("end", f"[{tag}] ")
            end_pos = tags_text.index("end-1c")
            
            # Make tag clickable
            tag_name = f"tag_{i}"
            tags_text.tag_add(tag_name, start_pos, end_pos)
            tags_text.tag_config(tag_name, foreground="blue", underline=True)
            
            def make_tag_click_handler(t):
                return lambda e: search_by_tag(t)
            
            tags_text.tag_bind(tag_name, "<Button-1>", make_tag_click_handler(tag))
    else:
        tags_text.insert("1.0", "No tags found in database. Files need to be tagged first.")
    
    def search_by_tag(tag):
        tags_var.set(tag)
        notebook.select(0)  # Switch to basic tab
        perform_search()
    
    # === RESULTS TAB ===
    results_tab = ttk.Frame(notebook)
    notebook.add(results_tab, text="📋 Results")
    
    # Results controls
    results_controls_frame = ttk.Frame(results_tab)
    results_controls_frame.pack(fill="x", padx=10, pady=5)
    
    # Results info
    results_info_var = ttk.StringVar(value="No search performed yet")
    ttk.Label(
        results_controls_frame, 
        textvariable=results_info_var, 
        font=("Segoe UI", 10, "bold")
    ).pack(side="left")
    
    # Export button
    def export_results():
        if not current_results:
            messagebox.showwarning("No Results", "No search results to export.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Search Results"
        )
        
        if filename:
            try:
                export_path = export_search_results(current_results, filename)
                messagebox.showinfo("Export Successful", f"Results exported to:\n{export_path}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export results:\n{e}")
    
    ttk.Button(
        results_controls_frame, 
        text="📤 Export Results", 
        bootstyle=INFO,
        command=export_results
    ).pack(side="right", padx=5)
    
    # Results display
    results_frame = ttk.LabelFrame(results_tab, text="Search Results", padding=10)
    results_frame.pack(fill="both", expand=True, padx=10, pady=5)
    
    # Results treeview
    columns = ("Name", "Type", "Tags", "Date", "Path")
    results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=15)
    
    # Configure columns
    results_tree.heading("Name", text="File Name")
    results_tree.heading("Type", text="Type")
    results_tree.heading("Tags", text="Tags")
    results_tree.heading("Date", text="Date")
    results_tree.heading("Path", text="Current Path")
    
    results_tree.column("Name", width=200)
    results_tree.column("Type", width=80)
    results_tree.column("Tags", width=200)
    results_tree.column("Date", width=120)
    results_tree.column("Path", width=300)
    
    # Scrollbar for results
    results_scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=results_tree.yview)
    results_tree.configure(yscrollcommand=results_scrollbar.set)
    
    results_tree.pack(side="left", fill="both", expand=True)
    results_scrollbar.pack(side="right", fill="y")
    
    # Double-click to open file location
    def open_file_location(event):
        selection = results_tree.selection()
        if not selection:
            return
        
        item = results_tree.item(selection[0])
        file_path = item['values'][4]  # Path column
        
        if file_path and Path(file_path).exists():
            try:
                if platform.system() == "Windows":
                    os.startfile(Path(file_path).parent)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", str(Path(file_path).parent)])
                else:  # Linux
                    subprocess.run(["xdg-open", str(Path(file_path).parent)])
            except Exception as e:
                messagebox.showerror("Error", f"Could not open file location:\n{e}")
        else:
            messagebox.showwarning("File Not Found", f"File no longer exists at:\n{file_path}")
    
    results_tree.bind("<Double-1>", open_file_location)
    
    # Context menu for results
    def show_context_menu(event):
        selection = results_tree.selection()
        if not selection:
            return
        
        context_menu = tk.Menu(search_window, tearoff=0)
        context_menu.add_command(label="📁 Open File Location", command=lambda: open_file_location(event))
        context_menu.add_command(label="👁️ Preview File", command=preview_selected_file)
        context_menu.add_command(label="📋 Copy Path", command=copy_file_path)
        context_menu.add_command(label="🏷️ Copy Tags", command=copy_file_tags)
        context_menu.add_separator()
        context_menu.add_command(label="📊 File Details", command=show_file_details)
        
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
    
    def copy_file_path():
        selection = results_tree.selection()
        if selection:
            item = results_tree.item(selection[0])
            file_path = item['values'][4]
            search_window.clipboard_clear()
            search_window.clipboard_append(file_path)
            update_status("File path copied to clipboard")
    
    def copy_file_tags():
        selection = results_tree.selection()
        if selection:
            item = results_tree.item(selection[0])
            tags = item['values'][2]
            search_window.clipboard_clear()
            search_window.clipboard_append(tags)
            update_status("Tags copied to clipboard")
    
    def preview_selected_file():
        """Preview the selected file from search results"""
        selection = results_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a file to preview.")
            return
        
        item = results_tree.item(selection[0])
        file_path = item['values'][4]  # Path column
        
        if file_path and Path(file_path).exists():
            from src.file_preview import show_file_preview
            show_file_preview(search_window, file_path)
        else:
            messagebox.showwarning("File Not Found", f"File no longer exists at:\n{file_path}")
    
    def show_file_details():
        selection = results_tree.selection()
        if not selection:
            return
        
        item = results_tree.item(selection[0])
        file_name = item['values'][0]
        file_type = item['values'][1]
        tags = item['values'][2]
        date = item['values'][3]
        path = item['values'][4]
        
        # Find the full result object for more details
        selected_result = None
        for result in current_results:
            if result.original_name == file_name:
                selected_result = result
                break
        
        if selected_result:
            details_window = ttk.Toplevel(search_window)
            details_window.title(f"File Details - {file_name}")
            details_window.geometry("500x400")
            details_window.transient(search_window)
            
            details_text = ScrolledText(details_window, font=("Consolas", 10))
            details_text.pack(fill="both", expand=True, padx=20, pady=20)
            
            details_info = f"""
FILE DETAILS
{'=' * 50}

Original Name: {selected_result.original_name}
File Type: {selected_result.file_type}
Current Path: {selected_result.new_path}
Date Organized: {selected_result.moved_at_display}
Tags: {selected_result.tags or 'No tags'}

FILE STATUS
{'=' * 50}

Database ID: {selected_result.id}
File Exists: {Path(selected_result.new_path).exists() if selected_result.new_path else 'Unknown'}
"""
            
            if selected_result.new_path and Path(selected_result.new_path).exists():
                file_path = Path(selected_result.new_path)
                stat = file_path.stat()
                details_info += f"""
File Size: {stat.st_size} bytes ({stat.st_size / 1024:.1f} KB)
Last Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            details_text.insert("1.0", details_info)
    
    results_tree.bind("<Button-3>", show_context_menu)  # Right-click
    
    # === MAIN SEARCH FUNCTIONS ===
    
    def display_results(results):
        """Display search results in the tree view (for organized files only)"""
        nonlocal current_results
        current_results = results
        
        # Clear existing results
        for item in results_tree.get_children():
            results_tree.delete(item)
        
        # Add new results
        for result in results:
            tags_display = result.tags[:50] + "..." if len(result.tags) > 50 else result.tags
            path_display = str(result.new_path)[:40] + "..." if len(str(result.new_path)) > 40 else str(result.new_path)
            
            results_tree.insert("", "end", values=(
                f"📁 {result.original_name}",
                result.file_type,
                tags_display,
                result.moved_at_display,
                result.new_path
            ))
        
        # Update results info
        results_info_var.set(f"Found {len(results)} file(s)")
        
        # Switch to results tab
        notebook.select(2)
    
    def display_combined_results(combined_results):
        """Display search results from both organized and indexed tables"""
        nonlocal current_results
        
        organized_results = combined_results.get('organized', [])
        indexed_results = combined_results.get('indexed', [])
        
        # Store all results for context menu and export
        current_results = organized_results + indexed_results
        
        # Clear existing results
        for item in results_tree.get_children():
            results_tree.delete(item)
        
        # Add organized files first
        for result in organized_results:
            tags_display = result.tags[:50] + "..." if len(result.tags) > 50 else result.tags
            path_display = str(result.new_path)[:40] + "..." if len(str(result.new_path)) > 40 else str(result.new_path)
            
            results_tree.insert("", "end", values=(
                f"📁 {result.original_name}",
                result.file_type,
                tags_display,
                result.moved_at_display,
                result.new_path
            ))
        
        # Add indexed files
        for result in indexed_results:
            path_display = str(result.file_path)[:40] + "..." if len(str(result.file_path)) > 40 else str(result.file_path)
            size_display = f"{result.file_size / 1024:.1f} KB" if result.file_size > 0 else "Unknown"
            
            results_tree.insert("", "end", values=(
                f"🗃️ {result.file_name}",
                result.file_type,
                size_display,  # Use size instead of tags for indexed files
                result.modified_at_display,
                result.file_path
            ))
        
        # Update results info
        total_found = len(organized_results) + len(indexed_results)
        results_info_var.set(f"Found {total_found} file(s) - {len(organized_results)} organized, {len(indexed_results)} indexed")
        
        # Switch to results tab
        notebook.select(2)
    
    def perform_search():
        """Perform the actual search based on current criteria"""
        update_status("Searching...")
        
        try:
            # Get search parameters
            name_pattern = name_var.get().strip()
            tags_pattern = tags_var.get().strip()
            file_type = file_type_var.get().strip()
            exact_match = exact_match_var.get()
            case_sensitive = case_sensitive_var.get()
            use_regex = regex_mode_var.get()
            
            # Date range
            date_from = None
            date_to = None
            if date_enabled_var.get():
                try:
                    if date_from_var.get():
                        date_from = datetime.strptime(date_from_var.get(), "%Y-%m-%d")
                    if date_to_var.get():
                        date_to = datetime.strptime(date_to_var.get(), "%Y-%m-%d")
                        # Add 23:59:59 to include the entire day
                        date_to = date_to.replace(hour=23, minute=59, second=59)
                except ValueError:
                    messagebox.showerror("Invalid Date", "Please use YYYY-MM-DD format for dates.")
                    return
            
            # Perform search on both tables
            if use_regex and (name_pattern or tags_pattern):
                # Regex search only works on organized files
                organized_results = searcher.search_by_regex(
                    name_regex=name_pattern,
                    tags_regex=tags_pattern
                )
                indexed_results = []
            else:
                # Search both organized files and file index
                organized_results = searcher.search_files(
                    name_pattern=name_pattern,
                    tags_pattern=tags_pattern,
                    file_type=file_type,
                    date_from=date_from,
                    date_to=date_to,
                    exact_match=exact_match,
                    case_sensitive=case_sensitive,
                    limit=1000
                )
                
                # Also search the file index
                indexed_results = searcher.search_file_index(
                    name_pattern=name_pattern,
                    file_type=file_type,
                    date_from=date_from,
                    date_to=date_to,
                    exact_match=exact_match,
                    case_sensitive=case_sensitive,
                    limit=1000
                )
            
            # Combine results for display
            combined_results = {
                'organized': organized_results,
                'indexed': indexed_results
            }
            
            display_combined_results(combined_results)
            
            total_found = len(organized_results) + len(indexed_results)
            update_status(f"Search completed - {total_found} files found ({len(organized_results)} organized, {len(indexed_results)} indexed)")
            
        except Exception as e:
            messagebox.showerror("Search Error", f"An error occurred during search:\n{e}")
            update_status("Search failed")
    
    def clear_search():
        """Clear all search criteria"""
        name_var.set("")
        tags_var.set("")
        file_type_var.set("")
        quick_entry.delete(0, "end")
        exact_match_var.set(False)
        case_sensitive_var.set(False)
        regex_mode_var.set(False)
        date_enabled_var.set(False)
        
        # Clear results
        for item in results_tree.get_children():
            results_tree.delete(item)
        
        current_results.clear()
        results_info_var.set("Search cleared")
        update_status("Ready for new search")
    
    def update_status(message):
        """Update the status bar"""
        try:
            status_label.config(text=f"🔍 {message}")
            search_window.update_idletasks()
        except:
            pass  # Window might be closing
    
    # === CONTROL BUTTONS ===
    
    # Bottom control frame
    control_frame = ttk.Frame(search_window)
    control_frame.pack(fill="x", padx=20, pady=10)
    
    # Left side buttons
    left_buttons = ttk.Frame(control_frame)
    left_buttons.pack(side="left")
    
    ttk.Button(
        left_buttons, 
        text="🔍 Search", 
        bootstyle=PRIMARY,
        command=perform_search
    ).pack(side="left", padx=5)
    
    ttk.Button(
        left_buttons, 
        text="🗑️ Clear", 
        bootstyle=SECONDARY,
        command=clear_search
    ).pack(side="left", padx=5)
    
    # Right side buttons
    right_buttons = ttk.Frame(control_frame)
    right_buttons.pack(side="right")
    
    def show_stats():
        """Show database statistics"""
        stats = searcher.get_search_stats()
        
        stats_window = ttk.Toplevel(search_window)
        stats_window.title("📊 Database Statistics")
        stats_window.geometry("500x400")
        stats_window.transient(search_window)
        
        stats_text = ScrolledText(stats_window, font=("Consolas", 10))
        stats_text.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Extract organized files stats
        org_stats = stats.get('organized_files', {})
        idx_stats = stats.get('indexed_files', {})
        
        stats_info = f"""
DATABASE STATISTICS
{'=' * 50}

ORGANIZED FILES (TidyDesk Database)
{'=' * 50}
Total Files: {org_stats.get('total_files', 0)}
Tagged Files: {org_stats.get('tagged_files', 0)}
Untagged Files: {org_stats.get('untagged_files', 0)}

Tag Coverage: {(org_stats.get('tagged_files', 0)/org_stats.get('total_files', 1)*100) if org_stats.get('total_files', 0) > 0 else 0:.1f}%

INDEXED FILES (System Index)
{'=' * 50}
Total Files: {idx_stats.get('total_files', 0):,}
Accessible: {idx_stats.get('accessible_files', 0):,}
Inaccessible: {idx_stats.get('inaccessible_files', 0):,}
Total Size: {idx_stats.get('total_size_bytes', 0) / (1024**3):.2f} GB

TOP ORGANIZED FILE TYPES
{'=' * 50}
"""
        
        for file_type, count in org_stats.get('top_file_types', []):
            stats_info += f"{file_type:<15} {count:>6} files\n"
        
        stats_info += f"\nTOP INDEXED FILE TYPES\n{'=' * 50}\n"
        for file_type, count in idx_stats.get('top_file_types', []):
            stats_info += f"{file_type:<15} {count:>6} files\n"
        
        org_date_range = org_stats.get('date_range', (None, None))
        if org_date_range[0] and org_date_range[1]:
            stats_info += f"\nOrganized Date Range: {org_date_range[0]} to {org_date_range[1]}"
        
        stats_text.insert("1.0", stats_info)
    
    ttk.Button(
        right_buttons, 
        text="📊 Stats", 
        bootstyle=INFO,
        command=show_stats
    ).pack(side="right", padx=5)
    
    ttk.Button(
        right_buttons, 
        text="❌ Close", 
        bootstyle=DANGER,
        command=search_window.destroy
    ).pack(side="right", padx=5)
    
    # Status bar
    status_frame = ttk.Frame(search_window)
    status_frame.pack(fill="x", padx=20, pady=5)
    
    status_label = ttk.Label(
        status_frame, 
        text="🔍 Ready to search - Use Quick Search or set criteria in Basic Search tab", 
        font=("Segoe UI", 9)
    )
    status_label.pack(side="left")
    
    # Keyboard shortcuts
    def on_enter(event):
        if notebook.index(notebook.select()) == 0:  # Basic search tab
            perform_search()
        return "break"
    
    def on_escape(event):
        search_window.destroy()
        return "break"
    
    search_window.bind("<Return>", on_enter)
    search_window.bind("<Escape>", on_escape)
    
    # Set focus to quick search entry
   # quick_entry.focus_set()
    
    # Load initial stats to show database status
    stats = searcher.get_search_stats()
    organized_count = stats.get('organized_files', {}).get('total_files', 0)
    indexed_count = stats.get('indexed_files', {}).get('total_files', 0)
    update_status(f"Database ready - {organized_count} organized files, {indexed_count} indexed files")

# Usage: Replace the existing open_search_window() function in gui.py with this implementation