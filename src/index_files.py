import os
import sqlite3
import threading
import time
from pathlib import Path
from datetime import datetime
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import multiprocessing

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
    def __init__(self, log_callback=None, meter=None, max_workers=None):
        self.log_callback = log_callback or (lambda x: print(x))
        self.meter = meter
        self.is_running = False
        self.total_files = 0
        self.processed_files = 0
        self.indexed_files = 0
        self.skipped_files = 0
        
        # Threading setup
        self.max_workers = max_workers or min(32, (multiprocessing.cpu_count() or 1) + 4)
        self.file_queue = Queue()
        self.batch_size = 1000  # Process files in batches for better performance
        self.lock = threading.Lock()
        
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
        self.log_callback(f"⚡ Using {self.max_workers} worker threads for parallel processing")

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

    

    def index_file_batch(self, file_paths):
        """Index a batch of files into the database for better performance"""
        indexed_count = 0
        skipped_count = 0
        batch_data = []
        inaccessible_data = []
        
        for file_path in file_paths:
            if not self.is_running:
                break
                
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
                
                batch_data.append((
                    str(file_path), file_path.name, file_size, file_type,
                    str(file_path.parent), created_at, modified_at, indexed_at, 1
                ))
                indexed_count += 1
                
            except (PermissionError, FileNotFoundError, OSError):
                inaccessible_data.append((
                    str(file_path), Path(file_path).name, 0, datetime.now().isoformat()
                ))
                skipped_count += 1
        
        # Batch insert into database
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                
                # Insert accessible files
                if batch_data:
                    c.executemany('''INSERT OR REPLACE INTO file_index 
                                   (file_path, file_name, file_size, file_type, parent_directory, 
                                    created_at, modified_at, indexed_at, is_accessible)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', batch_data)
                
                # Insert inaccessible files
                if inaccessible_data:
                    c.executemany('''INSERT OR REPLACE INTO file_index 
                                   (file_path, file_name, is_accessible, indexed_at)
                                   VALUES (?, ?, ?, ?)''', inaccessible_data)
                
                conn.commit()
        except Exception as e:
            self.log_callback(f"❌ Database error in batch: {e}")
        
        # Update counters thread-safely
        with self.lock:
            self.indexed_files += indexed_count
            self.skipped_files += skipped_count
            self.processed_files += len(file_paths)
        
        return indexed_count, skipped_count

    def collect_all_files(self, start_paths):
        """Collect all file paths that need to be indexed"""
        all_files = []
        
        self.log_callback("📊 Scanning filesystem for indexable files...")
        
        for start_path in start_paths:
            if not self.is_running:
                break
                
            try:
                for root, dirs, files in os.walk(start_path):
                    if not self.is_running:
                        break
                    
                    # Skip entire directories if they should be skipped
                    if self.should_skip_folder(root):
                        dirs.clear()
                        continue
                    
                    # Remove skip directories from dirs list
                    dirs[:] = [d for d in dirs if not self.should_skip_folder(os.path.join(root, d))]
                    
                    # Collect files that won't be skipped
                    for file in files:
                        if not self.is_running:
                            break
                            
                        file_path = os.path.join(root, file)
                        if not self.should_skip_file(file_path):
                            all_files.append(file_path)
                            
                            # Log progress every 10000 files
                            if len(all_files) % 10000 == 0:
                                self.log_callback(f"📊 Found {len(all_files)} files so far...")
                    
            except (PermissionError, FileNotFoundError) as e:
                self.log_callback(f"⚠️ Cannot access {start_path}: {e}")
                continue
        
        return all_files

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
        """Main indexing function with multi-threading support"""
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
            
            self.log_callback(f"🚀 Starting parallel file indexing from: {', '.join(start_paths)}")
            self.log_callback(f"⚡ Using {self.max_workers} worker threads")
            
            # Initialize progress
            self.processed_files = 0
            self.indexed_files = 0
            self.skipped_files = 0
            
            start_time = time.time()
            
            # Step 1: Collect all files first
            self.log_callback("🔍 Phase 1: Collecting file paths...")
            all_files = self.collect_all_files(start_paths)
            
            if not all_files:
                self.log_callback("⚠️ No files found to index!")
                return
            
            self.total_files = len(all_files)
            self.log_callback(f"📊 Found {self.total_files:,} files to index")
            
            # Initialize progress meter
            if self.meter:
                self.meter.configure(amounttotal=self.total_files, amountused=0)
            
            # Step 2: Process files in batches using thread pool
            self.log_callback("⚡ Phase 2: Multi-threaded indexing...")
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Create batches
                batches = []
                for i in range(0, len(all_files), self.batch_size):
                    batch = all_files[i:i + self.batch_size]
                    batches.append(batch)
                
                self.log_callback(f"📦 Created {len(batches)} batches of ~{self.batch_size} files each")
                
                # Submit all batches to thread pool
                futures = {executor.submit(self.index_file_batch, batch): batch for batch in batches}
                
                completed_batches = 0
                
                # Process completed futures
                for future in as_completed(futures):
                    if not self.is_running:
                        break
                        
                    try:
                        indexed_count, skipped_count = future.result()
                        completed_batches += 1
                        
                        # Update progress
                        self.update_progress()
                        
                        # Log progress every 10 batches or every 10%
                        progress_percent = (self.processed_files / self.total_files) * 100
                        if completed_batches % 10 == 0 or completed_batches % max(1, len(batches) // 10) == 0:
                            self.log_callback(f"📈 Progress: {self.processed_files:,}/{self.total_files:,} files "
                                            f"({progress_percent:.1f}%) - {self.indexed_files:,} indexed, "
                                            f"{self.skipped_files:,} skipped")
                            
                    except Exception as e:
                        self.log_callback(f"❌ Error processing batch: {e}")
                        completed_batches += 1
            
            # Final statistics
            end_time = time.time()
            duration = end_time - start_time
            
            if self.is_running:  # Only show completion if not cancelled
                self.log_callback("=" * 50)
                self.log_callback("✅ Multi-threaded file indexing completed!")
                self.log_callback(f"📊 Total files processed: {self.processed_files:,}")
                self.log_callback(f"📊 Files successfully indexed: {self.indexed_files:,}")
                self.log_callback(f"📊 Files skipped/inaccessible: {self.skipped_files:,}")
                self.log_callback(f"⏱️ Time taken: {duration:.2f} seconds")
                if duration > 0:
                    self.log_callback(f"🚀 Average speed: {self.processed_files/duration:.0f} files/second")
                self.log_callback(f"⚡ Performance boost from {self.max_workers} threads")
                
                if self.meter:
                    self.meter.configure(amountused=self.total_files, amounttotal=self.total_files)
            else:
                self.log_callback("⚠️ File indexing was cancelled")
                
        except Exception as e:
            self.log_callback(f"❌ Error during indexing: {e}")
            import traceback
            self.log_callback(f"❌ Traceback: {traceback.format_exc()}")
            
        finally:
            self.is_running = False

    def cancel_indexing(self):
        """Cancel the current indexing operation"""
        self.is_running = False
        self.log_callback("🛑 Indexing cancellation requested...")

def start_indexing_threaded(log_callback, meter, start_paths=None, max_workers=None):
    """Start file indexing in a separate thread with optional worker count"""
    def indexing_thread():
        indexer = FileIndexer(log_callback, meter, max_workers)
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