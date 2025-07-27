import os
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime
import platform

# Import database functions
from src.db import DB_PATH

# System folders to skip based on OS
WINDOWS_SKIP_FOLDERS = {
    'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData',
    'System Volume Information', '$Recycle.Bin', 'Recovery',
    'MSOCache', 'Intel', 'AMD', 'NVIDIA', 'Boot', 'Documents and Settings',
    'hiberfil.sys', 'pagefile.sys', 'swapfile.sys'
}

MAC_SKIP_FOLDERS = {
    'System', 'Library', 'private', 'usr', 'bin', 'sbin', 'etc',
    'var', 'tmp', 'dev', 'Volumes', '.Spotlight-V100', '.Trashes',
    '.fseventsd', '.DocumentRevisions-V100', '.TemporaryItems'
}

LINUX_SKIP_FOLDERS = {
    'proc', 'sys', 'dev', 'run', 'boot', 'lost+found',
    'tmp', 'var', 'usr', 'bin', 'sbin', 'etc', 'lib',
    'lib64', 'opt', 'mnt', 'media', 'srv'
}

# Common folders to skip across all platforms
COMMON_SKIP_FOLDERS = {
    'node_modules', '.git', '.svn', '.hg', '__pycache__',
    '.pytest_cache', '.vscode', '.idea', 'Thumbs.db',
    'Desktop.ini', '.DS_Store', 'Temporary Internet Files',
    'AppData', '.cache', '.config', '.local', '.mozilla',
    '.chrome', '.firefox', 'Google', 'Mozilla'
}

# File extensions to skip (system/temporary files)
SKIP_EXTENSIONS = {
    '.tmp', '.temp', '.log', '.cache', '.lock', '.pid',
    '.swap', '.bak', '.old', '.~', '.crdownload', '.part'
}

class FileIndexer:
    def __init__(self, log_callback=None, meter=None):
        self.log_callback = log_callback or (lambda x: print(x))
        self.meter = meter
        self.is_running = False
        self.total_files = 0
        self.processed_files = 0
        self.indexed_files = 0
        self.skipped_files = 0
        
        # Get OS-specific skip folders
        system = platform.system()
        if system == "Windows":
            self.skip_folders = WINDOWS_SKIP_FOLDERS | COMMON_SKIP_FOLDERS
        elif system == "Darwin":  # macOS
            self.skip_folders = MAC_SKIP_FOLDERS | COMMON_SKIP_FOLDERS
        else:  # Linux and others
            self.skip_folders = LINUX_SKIP_FOLDERS | COMMON_SKIP_FOLDERS
        
        self.log_callback(f"🖥️ Detected OS: {system}")
        self.log_callback(f"🚫 Will skip {len(self.skip_folders)} system folder types")

    def init_index_db(self):
        """Initialize the file index database table"""
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS file_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE,
                file_name TEXT,
                file_size INTEGER,
                file_type TEXT,
                parent_directory TEXT,
                created_at TEXT,
                modified_at TEXT,
                indexed_at TEXT,
                is_accessible INTEGER DEFAULT 1
            )''')
            conn.commit()
            self.log_callback("✅ File index database table initialized")

    def should_skip_folder(self, folder_path):
        """Check if a folder should be skipped"""
        folder_name = Path(folder_path).name
        
        # Skip hidden folders (starting with .)
        if folder_name.startswith('.') and folder_name not in {'.', '..'}:
            return True
        
        # Skip system folders
        if folder_name in self.skip_folders:
            return True
        
        # Skip if folder path contains system paths
        path_parts = Path(folder_path).parts
        for part in path_parts:
            if part in self.skip_folders:
                return True
        
        return False

    def should_skip_file(self, file_path):
        """Check if a file should be skipped"""
        file_path = Path(file_path)
        
        # Skip hidden files
        if file_path.name.startswith('.') and file_path.name not in {'.', '..'}:
            return True
        
        # Skip by extension
        if file_path.suffix.lower() in SKIP_EXTENSIONS:
            return True
        
        # Skip very large files (>2GB) to avoid memory issues
        try:
            if file_path.stat().st_size > 2 * 1024 * 1024 * 1024:  # 2GB
                return True
        except (OSError, PermissionError):
            return True
        
        return False

    def count_total_files(self, start_paths):
        """Count total files to process for progress tracking"""
        self.log_callback("📊 Counting files for progress tracking...")
        total = 0
        
        for start_path in start_paths:
            try:
                for root, dirs, files in os.walk(start_path):
                    # Skip entire directories if they should be skipped
                    if self.should_skip_folder(root):
                        dirs.clear()  # Don't recurse into subdirectories
                        continue
                    
                    # Remove skip directories from dirs list to avoid walking into them
                    dirs[:] = [d for d in dirs if not self.should_skip_folder(os.path.join(root, d))]
                    
                    # Count files that won't be skipped
                    for file in files:
                        file_path = os.path.join(root, file)
                        if not self.should_skip_file(file_path):
                            total += 1
                    
                    # Update progress every 1000 files counted
                    if total % 1000 == 0:
                        self.log_callback(f"📊 Counted {total} files so far...")
                        
            except (PermissionError, FileNotFoundError) as e:
                self.log_callback(f"⚠️ Cannot access {start_path}: {e}")
                continue
        
        self.total_files = total
        self.log_callback(f"📊 Total files to index: {total}")
        return total

    def index_file(self, file_path):
        """Index a single file into the database"""
        try:
            file_path = Path(file_path)
            
            # Get file stats
            stat = file_path.stat()
            file_size = stat.st_size
            created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
            modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
            indexed_at = datetime.now().isoformat()
            
            # Determine file type
            file_type = file_path.suffix.lower() if file_path.suffix else 'no_extension'
            
            # Insert into database
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute('''INSERT OR REPLACE INTO file_index 
                           (file_path, file_name, file_size, file_type, parent_directory, 
                            created_at, modified_at, indexed_at, is_accessible)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (str(file_path), file_path.name, file_size, file_type,
                          str(file_path.parent), created_at, modified_at, indexed_at, 1))
                conn.commit()
            
            self.indexed_files += 1
            return True
            
        except (PermissionError, FileNotFoundError, OSError) as e:
            # Log inaccessible files but don't stop processing
            try:
                with sqlite3.connect(DB_PATH) as conn:
                    c = conn.cursor()
                    c.execute('''INSERT OR REPLACE INTO file_index 
                               (file_path, file_name, is_accessible, indexed_at)
                               VALUES (?, ?, ?, ?)''',
                             (str(file_path), Path(file_path).name, 0, datetime.now().isoformat()))
                    conn.commit()
            except:
                pass  # If we can't even log it, just skip
            
            self.skipped_files += 1
            return False

    def update_progress(self):
        """Update the progress meter and log"""
        if self.meter and self.total_files > 0:
            progress_percent = (self.processed_files / self.total_files) * 100
            self.meter.configure(amountused=self.processed_files, amounttotal=self.total_files)
            
        # Log progress every 100 files
        if self.processed_files % 100 == 0:
            self.log_callback(f"📈 Progress: {self.processed_files}/{self.total_files} files "
                            f"({self.indexed_files} indexed, {self.skipped_files} skipped)")

    def index_files(self, start_paths=None):
        """Main indexing function"""
        if self.is_running:
            self.log_callback("⚠️ Indexing is already running!")
            return
        
        self.is_running = True
        
        try:
            # Initialize database
            self.init_index_db()
            
            # Default start paths based on OS
            if start_paths is None:
                system = platform.system()
                if system == "Windows":
                    # Start from all available drives
                    start_paths = [f"{chr(i)}:\\" for i in range(ord('A'), ord('Z')+1) 
                                 if os.path.exists(f"{chr(i)}:\\")]
                elif system == "Darwin":  # macOS
                    start_paths = ["/Users", "/Applications"]
                else:  # Linux
                    start_paths = ["/home", "/opt", "/usr/local"]
            
            self.log_callback(f"🚀 Starting file indexing from: {', '.join(start_paths)}")
            
            # Count total files first
            self.count_total_files(start_paths)
            
            # Initialize progress
            self.processed_files = 0
            self.indexed_files = 0
            self.skipped_files = 0
            
            if self.meter:
                self.meter.configure(amountused=0, amounttotal=self.total_files)
            
            # Start indexing
            start_time = time.time()
            
            for start_path in start_paths:
                if not self.is_running:  # Check if cancelled
                    break
                    
                self.log_callback(f"📁 Indexing path: {start_path}")
                
                try:
                    for root, dirs, files in os.walk(start_path):
                        if not self.is_running:  # Check if cancelled
                            break
                        
                        # Skip entire directories if they should be skipped
                        if self.should_skip_folder(root):
                            self.log_callback(f"⏭️ Skipping system folder: {root}")
                            dirs.clear()  # Don't recurse into subdirectories
                            continue
                        
                        # Remove skip directories from dirs list
                        original_dirs = dirs[:]
                        dirs[:] = [d for d in dirs if not self.should_skip_folder(os.path.join(root, d))]
                        skipped_dirs = set(original_dirs) - set(dirs)
                        for skipped_dir in skipped_dirs:
                            self.log_callback(f"⏭️ Skipping: {os.path.join(root, skipped_dir)}")
                        
                        # Process files in current directory
                        for file in files:
                            if not self.is_running:  # Check if cancelled
                                break
                                
                            file_path = os.path.join(root, file)
                            
                            if self.should_skip_file(file_path):
                                self.skipped_files += 1
                            else:
                                self.index_file(file_path)
                            
                            self.processed_files += 1
                            self.update_progress()
                            
                            # Brief pause every 50 files to keep UI responsive
                            if self.processed_files % 50 == 0:
                                time.sleep(0.01)
                                
                except (PermissionError, FileNotFoundError) as e:
                    self.log_callback(f"⚠️ Cannot access {start_path}: {e}")
                    continue
            
            # Final statistics
            end_time = time.time()
            duration = end_time - start_time
            
            if self.is_running:  # Only show completion if not cancelled
                self.log_callback("=" * 50)
                self.log_callback("✅ File indexing completed!")
                self.log_callback(f"📊 Total files processed: {self.processed_files}")
                self.log_callback(f"📊 Files successfully indexed: {self.indexed_files}")
                self.log_callback(f"📊 Files skipped/inaccessible: {self.skipped_files}")
                self.log_callback(f"⏱️ Time taken: {duration:.2f} seconds")
                self.log_callback(f"🚀 Average speed: {self.processed_files/duration:.0f} files/second")
                
                if self.meter:
                    self.meter.configure(amountused=self.total_files, amounttotal=self.total_files)
            else:
                self.log_callback("⚠️ File indexing was cancelled")
                
        except Exception as e:
            self.log_callback(f"❌ Error during indexing: {e}")
            
        finally:
            self.is_running = False

    def cancel_indexing(self):
        """Cancel the current indexing operation"""
        self.is_running = False
        self.log_callback("🛑 Indexing cancellation requested...")

def start_indexing_threaded(log_callback, meter, start_paths=None):
    """Start file indexing in a separate thread"""
    def indexing_thread():
        indexer = FileIndexer(log_callback, meter)
        indexer.index_files(start_paths)
    
    thread = threading.Thread(target=indexing_thread, daemon=True)
    thread.start()
    return thread

def get_index_statistics():
    """Get statistics about the file index"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            
            # Total files
            c.execute("SELECT COUNT(*) FROM file_index")
            total_files = c.fetchone()[0]
            
            # Files by type
            c.execute("SELECT file_type, COUNT(*) FROM file_index GROUP BY file_type ORDER BY COUNT(*) DESC LIMIT 10")
            file_types = c.fetchall()
            
            # Accessible vs inaccessible
            c.execute("SELECT is_accessible, COUNT(*) FROM file_index GROUP BY is_accessible")
            accessibility = dict(c.fetchall())
            
            # Total size
            c.execute("SELECT SUM(file_size) FROM file_index WHERE file_size IS NOT NULL")
            total_size = c.fetchone()[0] or 0
            
            return {
                'total_files': total_files,
                'file_types': file_types,
                'accessible_files': accessibility.get(1, 0),
                'inaccessible_files': accessibility.get(0, 0),
                'total_size_bytes': total_size
            }
    except Exception as e:
        return {'error': str(e)}

def clear_index():
    """Clear the entire file index"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM file_index")
            conn.commit()
        return True
    except Exception as e:
        return False, str(e)