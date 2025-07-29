
"""
File Preview Module
Provides comprehensive file preview functionality for various file types
"""

import os
import tkinter as tk
from tkinter import messagebox, END
from pathlib import Path
from datetime import datetime
import subprocess
import platform
import mimetypes

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledText
from ttkbootstrap.constants import INFO, SUCCESS, PRIMARY, WARNING, SECONDARY, DANGER

class FilePreviewWindow:
    """Enhanced file preview window with support for multiple file types"""
    
    def __init__(self, parent, file_path=None):
        self.parent = parent
        self.file_path = Path(file_path) if file_path else None
        self.preview_window = None
        self.current_image = None  # Keep reference to prevent garbage collection
        
        # Supported file types
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.tiff', '.webp'}
        self.text_extensions = {'.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.md', '.csv', '.log', '.ini', '.cfg'}
        self.code_extensions = {'.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', '.php', '.rb', '.go', '.rs', '.ts', '.jsx', '.tsx'}
        self.document_extensions = {'.pdf', '.docx', '.doc', '.rtf', '.odt'}
        self.archive_extensions = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'}
        
        # Maximum file size for preview (10MB)
        self.max_preview_size = 10 * 1024 * 1024
        
    def show_preview(self, file_path=None):
        """Show preview window for the specified file"""
        if file_path:
            self.file_path = Path(file_path)
        
        if not self.file_path or not self.file_path.exists():
            messagebox.showerror("File Not Found", "The selected file does not exist.")
            return
        
        self.create_preview_window()
        
    def create_preview_window(self):
        """Create the main preview window"""
        self.preview_window = ttk.Toplevel(self.parent)
        self.preview_window.title(f"File Preview - {self.file_path.name}")
        self.preview_window.geometry("800x600")
        self.preview_window.transient(self.parent)
        self.preview_window.grab_set()
        
        # Main container
        main_frame = ttk.Frame(self.preview_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header with file info
        self.create_header(main_frame)
        
        # Preview content area
        self.create_preview_area(main_frame)
        
        # Control buttons
        self.create_controls(main_frame)
        
        # Load and display the file
        self.load_file_preview()
    
    def create_header(self, parent):
        """Create header with file information"""
        header_frame = ttk.LabelFrame(parent, text="📄 File Information", padding=10)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Get file stats
        try:
            stat = self.file_path.stat()
            file_size = self.format_file_size(stat.st_size)
            modified_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            mime_type, _ = mimetypes.guess_type(str(self.file_path))
            
            info_text = f"""Name: {self.file_path.name}
Size: {file_size}
Type: {self.file_path.suffix.upper()[1:] if self.file_path.suffix else 'Unknown'}
MIME: {mime_type or 'Unknown'}
Modified: {modified_time}
Location: {self.file_path.parent}"""
            
        except Exception as e:
            info_text = f"Error reading file information: {e}"
        
        info_label = ttk.Label(header_frame, text=info_text, font=("Consolas", 9))
        info_label.pack(anchor="w")
    
    def create_preview_area(self, parent):
        """Create the main preview content area"""
        self.preview_frame = ttk.LabelFrame(parent, text="📋 Preview", padding=10)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create a canvas with scrollbars for content
        self.canvas = tk.Canvas(self.preview_frame, bg="white")
        self.v_scrollbar = ttk.Scrollbar(self.preview_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scrollbar = ttk.Scrollbar(self.preview_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        
        # Pack scrollbars and canvas
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Create frame inside canvas for content
        self.content_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        
        # Bind canvas resize
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        self.content_frame.bind('<Configure>', self.on_frame_configure)
    
    def create_controls(self, parent):
        """Create control buttons"""
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill=tk.X)
        
        # Left side buttons
        left_frame = ttk.Frame(controls_frame)
        left_frame.pack(side=tk.LEFT)
        
        ttk.Button(
            left_frame,
            text="📁 Open Location",
            bootstyle=INFO,
            command=self.open_file_location
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            left_frame,
            text="🔄 Refresh",
            bootstyle=SECONDARY,
            command=self.refresh_preview
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            left_frame,
            text="📂 Choose File",
            bootstyle=PRIMARY,
            command=self.choose_new_file
        ).pack(side=tk.LEFT, padx=5)
        
        # Right side buttons
        right_frame = ttk.Frame(controls_frame)
        right_frame.pack(side=tk.RIGHT)
        
        ttk.Button(
            right_frame,
            text="📋 Copy Path",
            bootstyle=SECONDARY,
            command=self.copy_file_path
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(
            right_frame,
            text="❌ Close",
            bootstyle=DANGER,
            command=self.preview_window.destroy
        ).pack(side=tk.RIGHT, padx=5)
    
    def load_file_preview(self):
        """Load and display file preview based on file type"""
        if not self.file_path.exists():
            self.show_error_message("File not found")
            return
        
        # Check file size
        try:
            file_size = self.file_path.stat().st_size
            if file_size > self.max_preview_size:
                self.show_info_message(
                    f"File too large for preview\n"
                    f"Size: {self.format_file_size(file_size)}\n"
                    f"Maximum: {self.format_file_size(self.max_preview_size)}"
                )
                return
        except Exception as e:
            self.show_error_message(f"Error reading file: {e}")
            return
        
        # Clear previous content
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        # Determine file type and show appropriate preview
        file_ext = self.file_path.suffix.lower()
        
        if file_ext in self.image_extensions:
            self.preview_image()
        elif file_ext in self.text_extensions or file_ext in self.code_extensions:
            self.preview_text()
        elif file_ext == '.pdf':
            self.preview_pdf()
        elif file_ext in self.archive_extensions:
            self.preview_archive()
        elif file_ext in self.document_extensions:
            self.preview_document()
        else:
            self.preview_binary()
    
    def preview_image(self):
        """Preview image files"""
        if not PIL_AVAILABLE:
            self.show_error_message("PIL/Pillow not available for image preview")
            return
        
        try:
            # Open and process image
            with Image.open(self.file_path) as img:
                # Get image info
                width, height = img.size
                mode = img.mode
                format_name = img.format
                
                # Create info label
                info_text = f"Dimensions: {width} x {height} pixels\nMode: {mode}\nFormat: {format_name}"
                info_label = ttk.Label(self.content_frame, text=info_text, font=("Consolas", 9))
                info_label.pack(pady=(0, 10))
                
                # Resize image if too large
                max_width = 750
                max_height = 500
                
                if width > max_width or height > max_height:
                    ratio = min(max_width/width, max_height/height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                self.current_image = ImageTk.PhotoImage(img)
                
                # Display image
                image_label = ttk.Label(self.content_frame, image=self.current_image)
                image_label.pack(pady=10)
                
        except Exception as e:
            self.show_error_message(f"Error loading image: {e}")
    
    def preview_text(self):
        """Preview text files with syntax highlighting"""
        try:
            # Try different encodings
            encodings = ['utf-8', 'utf-16', 'latin1', 'cp1252']
            content = None
            
            for encoding in encodings:
                try:
                    with open(self.file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                self.show_error_message("Could not decode text file")
                return
            
            # Create text widget
            text_widget = ScrolledText(
                self.content_frame, 
                height=25, 
                font=("Consolas", 10),
                wrap=tk.WORD
            )
            text_widget.pack(fill=tk.BOTH, expand=True)
            
            # Insert content
            text_widget.insert("1.0", content)
            text_widget.config(state="readonly")
            
            # Add line numbers for code files
            if self.file_path.suffix.lower() in self.code_extensions:
                self.add_line_numbers(text_widget, content)
                
        except Exception as e:
            self.show_error_message(f"Error reading text file: {e}")
    
    def preview_pdf(self):
        """Preview PDF files (basic info only)"""
        self.show_info_message(
            "PDF Preview\n\n"
            "PDF files require external applications for viewing.\n"
            "Click 'Open Location' to view with your default PDF reader."
        )
    
    def preview_archive(self):
        """Preview archive files by listing contents"""
        try:
            import zipfile
            import tarfile
            
            file_ext = self.file_path.suffix.lower()
            contents = []
            
            if file_ext == '.zip':
                with zipfile.ZipFile(self.file_path, 'r') as zf:
                    for info in zf.infolist():
                        size = self.format_file_size(info.file_size)
                        date = datetime(*info.date_time).strftime("%Y-%m-%d %H:%M")
                        contents.append(f"{info.filename:<50} {size:>10} {date}")
            
            elif file_ext in {'.tar', '.gz', '.bz2'}:
                with tarfile.open(self.file_path, 'r:*') as tf:
                    for member in tf.getmembers():
                        size = self.format_file_size(member.size)
                        date = datetime.fromtimestamp(member.mtime).strftime("%Y-%m-%d %H:%M")
                        contents.append(f"{member.name:<50} {size:>10} {date}")
            
            if contents:
                # Create text widget to show contents
                text_widget = ScrolledText(
                    self.content_frame, 
                    height=20, 
                    font=("Consolas", 9)
                )
                text_widget.pack(fill=tk.BOTH, expand=True)
                
                header = f"{'Filename':<50} {'Size':>10} {'Date'}\n" + "="*75 + "\n"
                text_widget.insert("1.0", header + "\n".join(contents))
                text_widget.config(state="readonly")
            else:
                self.show_info_message("Archive appears to be empty")
                
        except Exception as e:
            self.show_error_message(f"Error reading archive: {e}")
    
    def preview_document(self):
        """Preview document files (basic info)"""
        self.show_info_message(
            "Document Preview\n\n"
            f"Document type: {self.file_path.suffix.upper()}\n"
            "Document files require external applications for viewing.\n"
            "Click 'Open Location' to view with your default application."
        )
    
    def preview_binary(self):
        """Preview binary files (hex dump)"""
        try:
            with open(self.file_path, 'rb') as f:
                # Read first 1KB for hex preview
                data = f.read(1024)
            
            # Create hex dump
            hex_lines = []
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_part = ' '.join(f'{b:02x}' for b in chunk)
                ascii_part = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
                hex_lines.append(f"{i:08x}: {hex_part:<48} |{ascii_part}|")
            
            # Create text widget
            text_widget = ScrolledText(
                self.content_frame, 
                height=20, 
                font=("Consolas", 9)
            )
            text_widget.pack(fill=tk.BOTH, expand=True)
            
            header = "Binary File - Hex Dump (first 1KB)\n" + "="*60 + "\n\n"
            text_widget.insert("1.0", header + "\n".join(hex_lines))
            text_widget.config(state="readonly")
            
        except Exception as e:
            self.show_error_message(f"Error reading binary file: {e}")
    
    def add_line_numbers(self, text_widget, content):
        """Add line numbers to text widget"""
        lines = content.count('\n') + 1
        line_numbers = '\n'.join(str(i) for i in range(1, lines + 1))
        
        # This is a simplified version - full implementation would require
        # a separate text widget for line numbers
        pass
    
    def show_error_message(self, message):
        """Show error message in preview area"""
        error_label = ttk.Label(
            self.content_frame, 
            text=f"❌ Error\n\n{message}",
            font=("Segoe UI", 12),
            foreground="red"
        )
        error_label.pack(expand=True)
    
    def show_info_message(self, message):
        """Show info message in preview area"""
        info_label = ttk.Label(
            self.content_frame, 
            text=f"ℹ️ {message}",
            font=("Segoe UI", 11),
            justify=tk.CENTER
        )
        info_label.pack(expand=True, pady=50)
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def open_file_location(self):
        """Open file location in system file manager"""
        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", "/select,", str(self.file_path)])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", str(self.file_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(self.file_path.parent)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file location:\n{e}")
    
    def refresh_preview(self):
        """Refresh the preview"""
        self.load_file_preview()
    
    def choose_new_file(self):
        """Choose a new file to preview"""
        from tkinter import filedialog
        
        new_file = filedialog.askopenfilename(
            title="Choose file to preview",
            initialdir=self.file_path.parent if self.file_path else os.getcwd()
        )
        
        if new_file:
            self.file_path = Path(new_file)
            self.preview_window.title(f"File Preview - {self.file_path.name}")
            self.load_file_preview()
    
    def copy_file_path(self):
        """Copy file path to clipboard"""
        self.preview_window.clipboard_clear()
        self.preview_window.clipboard_append(str(self.file_path))
        messagebox.showinfo("Copied", "File path copied to clipboard!")
    
    def on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)
    
    def on_frame_configure(self, event):
        """Handle frame resize"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


def show_file_preview(parent, file_path=None):
    """Convenience function to show file preview"""
    preview = FilePreviewWindow(parent, file_path)
    preview.show_preview()


def preview_file_dialog(parent):
    """Show file dialog and preview selected file"""
    from tkinter import filedialog
    
    file_path = filedialog.askopenfilename(
        title="Select file to preview",
        filetypes=[
            ("All files", "*.*"),
            ("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.ico *.tiff *.webp"),
            ("Text files", "*.txt *.py *.js *.html *.css *.json *.xml *.md *.csv *.log"),
            ("Documents", "*.pdf *.docx *.doc *.rtf *.odt"),
            ("Archives", "*.zip *.rar *.7z *.tar *.gz *.bz2")
        ]
    )
    
    if file_path:
        show_file_preview(parent, file_path)


# Example usage and testing
if __name__ == "__main__":
    # Test the preview window
    root = ttk.Window(themename="darkly")
    root.title("File Preview Test")
    root.geometry("300x200")
    
    def test_preview():
        preview_file_dialog(root)
    
    ttk.Button(
        root, 
        text="Test File Preview", 
        command=test_preview
    ).pack(expand=True)
    
    root.mainloop()
