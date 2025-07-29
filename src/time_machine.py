
import os
import json
import sqlite3
import threading
import time
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import difflib

from src.db import DB_PATH

class FilesystemTimeMachine:
    """Filesystem Time Machine for creating and browsing folder snapshots"""
    
    def __init__(self, log_callback=None):
        self.log_callback = log_callback or (lambda x: print(x))
        self.snapshots_dir = Path("snapshots")
        self.snapshots_dir.mkdir(exist_ok=True)
        self.is_running = False
        self.snapshot_thread = None
        self.watched_folders = set()
        self.snapshot_interval = 3600  # 1 hour default
        self.max_snapshots = 100  # Keep last 100 snapshots
        self.init_db()
        
    def init_db(self):
        """Initialize time machine database tables"""
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            
            # Snapshots table
            c.execute('''CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT,
                snapshot_name TEXT,
                created_at TEXT,
                file_count INTEGER,
                total_size INTEGER,
                hash_signature TEXT
            )''')
            
            # Snapshot files table
            c.execute('''CREATE TABLE IF NOT EXISTS snapshot_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER,
                relative_path TEXT,
                file_size INTEGER,
                modified_at TEXT,
                file_hash TEXT,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots (id)
            )''')
            
            # Watched folders table
            c.execute('''CREATE TABLE IF NOT EXISTS watched_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT UNIQUE,
                added_at TEXT,
                last_snapshot TEXT,
                is_active INTEGER DEFAULT 1
            )''')
            
            conn.commit()
            self.log_callback("✅ Time Machine database initialized")

    def add_watched_folder(self, folder_path: str) -> bool:
        """Add a folder to be watched for snapshots"""
        folder_path = str(Path(folder_path).resolve())
        
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute('''INSERT OR REPLACE INTO watched_folders 
                           (folder_path, added_at, is_active) VALUES (?, ?, ?)''',
                         (folder_path, datetime.now().isoformat(), 1))
                conn.commit()
            
            self.watched_folders.add(folder_path)
            self.log_callback(f"📂 Added folder to Time Machine: {folder_path}")
            return True
            
        except Exception as e:
            self.log_callback(f"❌ Error adding watched folder: {e}")
            return False

    def remove_watched_folder(self, folder_path: str) -> bool:
        """Remove a folder from being watched"""
        folder_path = str(Path(folder_path).resolve())
        
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("UPDATE watched_folders SET is_active = 0 WHERE folder_path = ?", 
                         (folder_path,))
                conn.commit()
            
            self.watched_folders.discard(folder_path)
            self.log_callback(f"🗑️ Removed folder from Time Machine: {folder_path}")
            return True
            
        except Exception as e:
            self.log_callback(f"❌ Error removing watched folder: {e}")
            return False

    def load_watched_folders(self):
        """Load watched folders from database"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("SELECT folder_path FROM watched_folders WHERE is_active = 1")
                folders = [row[0] for row in c.fetchall()]
                self.watched_folders = set(folders)
                self.log_callback(f"📚 Loaded {len(folders)} watched folders")
        except Exception as e:
            self.log_callback(f"❌ Error loading watched folders: {e}")

    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file"""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""

    def create_snapshot(self, folder_path: str) -> Optional[int]:
        """Create a snapshot of a folder"""
        folder_path = Path(folder_path)
        if not folder_path.exists():
            self.log_callback(f"❌ Folder not found: {folder_path}")
            return None

        timestamp = datetime.now()
        snapshot_name = f"{folder_path.name}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        snapshot_dir = self.snapshots_dir / snapshot_name
        
        try:
            # Create snapshot directory
            snapshot_dir.mkdir(exist_ok=True)
            
            # Collect file information
            files_info = []
            total_size = 0
            file_count = 0
            folder_hash_data = []
            
            for root, dirs, files in os.walk(folder_path):
                # Skip hidden directories and common ignore patterns
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'__pycache__', 'node_modules'}]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                        
                    file_path = Path(root) / file
                    relative_path = file_path.relative_to(folder_path)
                    
                    try:
                        stat = file_path.stat()
                        file_size = stat.st_size
                        modified_at = datetime.fromtimestamp(stat.st_mtime).isoformat()
                        file_hash = self.calculate_file_hash(file_path)
                        
                        # Copy file to snapshot directory
                        dest_path = snapshot_dir / relative_path
                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, dest_path)
                        
                        files_info.append({
                            'relative_path': str(relative_path),
                            'file_size': file_size,
                            'modified_at': modified_at,
                            'file_hash': file_hash
                        })
                        
                        total_size += file_size
                        file_count += 1
                        folder_hash_data.append(f"{relative_path}:{file_hash}")
                        
                    except Exception as e:
                        self.log_callback(f"⚠️ Skipped file {file_path}: {e}")
                        continue
            
            # Calculate overall folder signature
            folder_signature = hashlib.sha256(
                '\n'.join(sorted(folder_hash_data)).encode()
            ).hexdigest()
            
            # Save snapshot to database
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                
                # Insert snapshot record
                c.execute('''INSERT INTO snapshots 
                           (folder_path, snapshot_name, created_at, file_count, total_size, hash_signature)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                         (str(folder_path), snapshot_name, timestamp.isoformat(), 
                          file_count, total_size, folder_signature))
                
                snapshot_id = c.lastrowid
                
                # Insert file records
                for file_info in files_info:
                    c.execute('''INSERT INTO snapshot_files 
                               (snapshot_id, relative_path, file_size, modified_at, file_hash)
                               VALUES (?, ?, ?, ?, ?)''',
                             (snapshot_id, file_info['relative_path'], file_info['file_size'],
                              file_info['modified_at'], file_info['file_hash']))
                
                # Update watched folder last snapshot time
                c.execute('''UPDATE watched_folders SET last_snapshot = ? 
                           WHERE folder_path = ?''',
                         (timestamp.isoformat(), str(folder_path)))
                
                conn.commit()
            
            self.log_callback(f"📸 Snapshot created: {snapshot_name} ({file_count} files, {total_size/1024/1024:.1f}MB)")
            
            # Clean up old snapshots
            self.cleanup_old_snapshots(str(folder_path))
            
            return snapshot_id
            
        except Exception as e:
            self.log_callback(f"❌ Error creating snapshot: {e}")
            # Clean up partial snapshot
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir, ignore_errors=True)
            return None

    def cleanup_old_snapshots(self, folder_path: str):
        """Remove old snapshots beyond the limit"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                
                # Get snapshots for this folder, ordered by creation date
                c.execute('''SELECT id, snapshot_name FROM snapshots 
                           WHERE folder_path = ? ORDER BY created_at DESC''',
                         (folder_path,))
                snapshots = c.fetchall()
                
                # Remove excess snapshots
                if len(snapshots) > self.max_snapshots:
                    old_snapshots = snapshots[self.max_snapshots:]
                    
                    for snapshot_id, snapshot_name in old_snapshots:
                        # Delete from database
                        c.execute("DELETE FROM snapshot_files WHERE snapshot_id = ?", (snapshot_id,))
                        c.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
                        
                        # Delete snapshot directory
                        snapshot_dir = self.snapshots_dir / snapshot_name
                        if snapshot_dir.exists():
                            shutil.rmtree(snapshot_dir, ignore_errors=True)
                    
                    conn.commit()
                    self.log_callback(f"🧹 Cleaned up {len(old_snapshots)} old snapshots")
                    
        except Exception as e:
            self.log_callback(f"❌ Error cleaning up snapshots: {e}")

    def get_snapshots(self, folder_path: str = None) -> List[Dict]:
        """Get list of snapshots, optionally filtered by folder"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                
                if folder_path:
                    c.execute('''SELECT id, folder_path, snapshot_name, created_at, 
                               file_count, total_size, hash_signature 
                               FROM snapshots WHERE folder_path = ? 
                               ORDER BY created_at DESC''', (folder_path,))
                else:
                    c.execute('''SELECT id, folder_path, snapshot_name, created_at, 
                               file_count, total_size, hash_signature 
                               FROM snapshots ORDER BY created_at DESC''')
                
                snapshots = []
                for row in c.fetchall():
                    snapshots.append({
                        'id': row[0],
                        'folder_path': row[1],
                        'snapshot_name': row[2],
                        'created_at': row[3],
                        'file_count': row[4],
                        'total_size': row[5],
                        'hash_signature': row[6]
                    })
                
                return snapshots
                
        except Exception as e:
            self.log_callback(f"❌ Error getting snapshots: {e}")
            return []

    def compare_snapshots(self, snapshot1_id: int, snapshot2_id: int) -> Dict:
        """Compare two snapshots and return differences"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                
                # Get files from both snapshots
                c.execute('''SELECT relative_path, file_size, file_hash 
                           FROM snapshot_files WHERE snapshot_id = ?''', (snapshot1_id,))
                files1 = {row[0]: {'size': row[1], 'hash': row[2]} for row in c.fetchall()}
                
                c.execute('''SELECT relative_path, file_size, file_hash 
                           FROM snapshot_files WHERE snapshot_id = ?''', (snapshot2_id,))
                files2 = {row[0]: {'size': row[1], 'hash': row[2]} for row in c.fetchall()}
                
                # Calculate differences
                all_files = set(files1.keys()) | set(files2.keys())
                added = []
                removed = []
                modified = []
                unchanged = []
                
                for file_path in all_files:
                    if file_path in files1 and file_path in files2:
                        if files1[file_path]['hash'] != files2[file_path]['hash']:
                            modified.append({
                                'path': file_path,
                                'old_size': files1[file_path]['size'],
                                'new_size': files2[file_path]['size']
                            })
                        else:
                            unchanged.append(file_path)
                    elif file_path in files2:
                        added.append({
                            'path': file_path,
                            'size': files2[file_path]['size']
                        })
                    else:
                        removed.append({
                            'path': file_path,
                            'size': files1[file_path]['size']
                        })
                
                return {
                    'added': added,
                    'removed': removed,
                    'modified': modified,
                    'unchanged': unchanged,
                    'summary': {
                        'added_count': len(added),
                        'removed_count': len(removed),
                        'modified_count': len(modified),
                        'unchanged_count': len(unchanged)
                    }
                }
                
        except Exception as e:
            self.log_callback(f"❌ Error comparing snapshots: {e}")
            return {}

    def restore_snapshot(self, snapshot_id: int, destination: str = None) -> bool:
        """Restore a snapshot to a destination folder"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute('''SELECT folder_path, snapshot_name FROM snapshots 
                           WHERE id = ?''', (snapshot_id,))
                result = c.fetchone()
                
                if not result:
                    self.log_callback(f"❌ Snapshot {snapshot_id} not found")
                    return False
                
                original_folder, snapshot_name = result
                snapshot_dir = self.snapshots_dir / snapshot_name
                
                if not snapshot_dir.exists():
                    self.log_callback(f"❌ Snapshot directory not found: {snapshot_dir}")
                    return False
                
                # Determine destination
                if destination is None:
                    destination = f"{original_folder}_restored_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                destination_path = Path(destination)
                destination_path.mkdir(parents=True, exist_ok=True)
                
                # Copy snapshot contents to destination
                for item in snapshot_dir.rglob('*'):
                    if item.is_file():
                        relative_path = item.relative_to(snapshot_dir)
                        dest_file = destination_path / relative_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest_file)
                
                self.log_callback(f"✅ Snapshot restored to: {destination}")
                return True
                
        except Exception as e:
            self.log_callback(f"❌ Error restoring snapshot: {e}")
            return False

    def start_auto_snapshots(self):
        """Start automatic snapshot creation"""
        if self.is_running:
            self.log_callback("⚠️ Auto snapshots already running")
            return
        
        self.load_watched_folders()
        if not self.watched_folders:
            self.log_callback("⚠️ No folders being watched for snapshots")
            return
        
        self.is_running = True
        
        def snapshot_worker():
            self.log_callback(f"🚀 Auto snapshots started (interval: {self.snapshot_interval}s)")
            
            while self.is_running:
                for folder_path in self.watched_folders.copy():
                    if not self.is_running:
                        break
                        
                    if Path(folder_path).exists():
                        self.create_snapshot(folder_path)
                    else:
                        self.log_callback(f"⚠️ Watched folder no longer exists: {folder_path}")
                
                # Wait for next interval
                for _ in range(self.snapshot_interval):
                    if not self.is_running:
                        break
                    time.sleep(1)
            
            self.log_callback("⏹️ Auto snapshots stopped")
        
        self.snapshot_thread = threading.Thread(target=snapshot_worker, daemon=True)
        self.snapshot_thread.start()

    def stop_auto_snapshots(self):
        """Stop automatic snapshot creation"""
        self.is_running = False
        if self.snapshot_thread:
            self.snapshot_thread.join(timeout=5)
        self.log_callback("🛑 Auto snapshots stopped")

    def set_snapshot_interval(self, seconds: int):
        """Set the snapshot interval in seconds"""
        self.snapshot_interval = max(60, seconds)  # Minimum 1 minute
        self.log_callback(f"⏰ Snapshot interval set to {self.snapshot_interval} seconds")

    def get_watched_folders(self) -> List[Dict]:
        """Get list of watched folders"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute('''SELECT folder_path, added_at, last_snapshot 
                           FROM watched_folders WHERE is_active = 1 
                           ORDER BY added_at DESC''')
                
                folders = []
                for row in c.fetchall():
                    folders.append({
                        'path': row[0],
                        'added_at': row[1],
                        'last_snapshot': row[2]
                    })
                
                return folders
                
        except Exception as e:
            self.log_callback(f"❌ Error getting watched folders: {e}")
            return []

    def get_statistics(self) -> Dict:
        """Get Time Machine statistics"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                
                # Total snapshots
                c.execute("SELECT COUNT(*) FROM snapshots")
                total_snapshots = c.fetchone()[0]
                
                # Total files in all snapshots
                c.execute("SELECT COUNT(*) FROM snapshot_files")
                total_files = c.fetchone()[0]
                
                # Total size
                c.execute("SELECT SUM(total_size) FROM snapshots")
                total_size = c.fetchone()[0] or 0
                
                # Watched folders count
                c.execute("SELECT COUNT(*) FROM watched_folders WHERE is_active = 1")
                watched_folders_count = c.fetchone()[0]
                
                # Disk usage
                disk_usage = sum(
                    sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                    for path in self.snapshots_dir.iterdir()
                    if path.is_dir()
                )
                
                return {
                    'total_snapshots': total_snapshots,
                    'total_files': total_files,
                    'total_logical_size': total_size,
                    'disk_usage': disk_usage,
                    'watched_folders': watched_folders_count,
                    'is_running': self.is_running,
                    'snapshot_interval': self.snapshot_interval
                }
                
        except Exception as e:
            self.log_callback(f"❌ Error getting statistics: {e}")
            return {}

# Global instance
time_machine = FilesystemTimeMachine()
