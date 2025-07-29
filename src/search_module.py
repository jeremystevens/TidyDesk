"""
File Search Module for Desktop File Organizer
Provides comprehensive search functionality for the file database
"""

import sqlite3
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

# Import the database path from your db module
from src.db import DB_PATH

@dataclass
class SearchResult:
    """Data class for search results"""
    id: int
    original_name: str
    new_path: str
    file_type: str
    moved_at: str
    tags: str
    source_table: str = "files"  # Track which table this result came from

    def __post_init__(self):
        """Process the moved_at field for better display"""
        try:
            self.moved_at_datetime = datetime.fromisoformat(self.moved_at)
            self.moved_at_display = self.moved_at_datetime.strftime("%Y-%m-%d %H:%M")
        except:
            self.moved_at_display = self.moved_at

@dataclass
class FileIndexResult:
    """Data class for file index search results"""
    id: int
    file_path: str
    file_name: str
    file_size: int
    file_type: str
    parent_directory: str
    created_at: str
    modified_at: str
    indexed_at: str
    is_accessible: int

    def __post_init__(self):
        """Process date fields for better display"""
        try:
            if self.created_at:
                self.created_at_datetime = datetime.fromisoformat(self.created_at)
                self.created_at_display = self.created_at_datetime.strftime("%Y-%m-%d %H:%M")
            else:
                self.created_at_display = "Unknown"

            if self.modified_at:
                self.modified_at_datetime = datetime.fromisoformat(self.modified_at)
                self.modified_at_display = self.modified_at_datetime.strftime("%Y-%m-%d %H:%M")
            else:
                self.modified_at_display = "Unknown"

            if self.indexed_at:
                self.indexed_at_datetime = datetime.fromisoformat(self.indexed_at)
                self.indexed_at_display = self.indexed_at_datetime.strftime("%Y-%m-%d %H:%M")
            else:
                self.indexed_at_display = "Unknown"
        except:
            self.created_at_display = self.created_at
            self.modified_at_display = self.modified_at
            self.indexed_at_display = self.indexed_at

class FileSearcher:
    """Main search engine for file database - supports both organized files and file index"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def search_files(self, 
                    name_pattern: str = "",
                    tags_pattern: str = "",
                    file_type: str = "",
                    date_from: Optional[datetime] = None,
                    date_to: Optional[datetime] = None,
                    exact_match: bool = False,
                    case_sensitive: bool = False,
                    limit: int = 1000) -> List[SearchResult]:
        """
        Comprehensive file search with multiple criteria

        Args:
            name_pattern: Pattern to search in file names
            tags_pattern: Pattern to search in tags
            file_type: Specific file type to filter by
            date_from: Start date for date range search
            date_to: End date for date range search
            exact_match: Whether to use exact matching
            case_sensitive: Whether search is case sensitive
            limit: Maximum number of results to return

        Returns:
            List of SearchResult objects
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()

                # Build the query dynamically
                query_parts = ["SELECT * FROM files WHERE 1=1"]
                params = []

                # Name search
                if name_pattern:
                    if exact_match:
                        if case_sensitive:
                            query_parts.append("AND original_name = ?")
                        else:
                            query_parts.append("AND LOWER(original_name) = LOWER(?)")
                        params.append(name_pattern)
                    else:
                        if case_sensitive:
                            query_parts.append("AND original_name LIKE ?")
                        else:
                            query_parts.append("AND LOWER(original_name) LIKE LOWER(?)")
                        params.append(f"%{name_pattern}%")

                # Tags search
                if tags_pattern:
                    if exact_match:
                        if case_sensitive:
                            query_parts.append("AND tags = ?")
                        else:
                            query_parts.append("AND LOWER(tags) = LOWER(?)")
                        params.append(tags_pattern)
                    else:
                        if case_sensitive:
                            query_parts.append("AND tags LIKE ?")
                        else:
                            query_parts.append("AND LOWER(tags) LIKE LOWER(?)")
                        params.append(f"%{tags_pattern}%")

                # File type search
                if file_type:
                    if case_sensitive:
                        query_parts.append("AND file_type = ?")
                    else:
                        query_parts.append("AND LOWER(file_type) = LOWER(?)")
                    params.append(file_type)

                # Date range search
                if date_from:
                    query_parts.append("AND moved_at >= ?")
                    params.append(date_from.isoformat())

                if date_to:
                    query_parts.append("AND moved_at <= ?")
                    params.append(date_to.isoformat())

                # Add ordering and limit
                query_parts.append("ORDER BY moved_at DESC")
                query_parts.append("LIMIT ?")
                params.append(limit)

                # Execute query
                query = " ".join(query_parts)
                print(f"🔍 Executing query: {query}")
                print(f"📝 With parameters: {params}")
                c.execute(query, params)
                rows = c.fetchall()
                print(f"📊 Query returned {len(rows)} results")

                # Convert to SearchResult objects
                results = []
                for row in rows:
                    result = SearchResult(
                        id=row[0],
                        original_name=row[1],
                        new_path=row[2],
                        file_type=row[3],
                        moved_at=row[4],
                        tags=row[5] or ""
                    )
                    results.append(result)

                return results

        except Exception as e:
            print(f"Search error: {e}")
            return []

    def search_file_index(self,
                         name_pattern: str = "",
                         file_type: str = "",
                         size_min: Optional[int] = None,
                         size_max: Optional[int] = None,
                         date_from: Optional[datetime] = None,
                         date_to: Optional[datetime] = None,
                         parent_directory: str = "",
                         exact_match: bool = False,
                         case_sensitive: bool = False,
                         accessible_only: bool = True,
                         limit: int = 1000) -> List[FileIndexResult]:
        """
        Search the file_index table for filesystem files

        Args:
            name_pattern: Pattern to search in file names
            file_type: Specific file type to filter by
            size_min: Minimum file size in bytes
            size_max: Maximum file size in bytes
            date_from: Start date for date range search (uses modified_at)
            date_to: End date for date range search (uses modified_at)
            parent_directory: Pattern to search in parent directory
            exact_match: Whether to use exact matching
            case_sensitive: Whether search is case sensitive
            accessible_only: Only include accessible files
            limit: Maximum number of results to return

        Returns:
            List of FileIndexResult objects
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()

                # Build the query dynamically
                query_parts = ["SELECT * FROM file_index WHERE 1=1"]
                params = []

                # Only accessible files filter
                if accessible_only:
                    query_parts.append("AND is_accessible = 1")

                # Name search
                if name_pattern:
                    if exact_match:
                        if case_sensitive:
                            query_parts.append("AND file_name = ?")
                        else:
                            query_parts.append("AND LOWER(file_name) = LOWER(?)")
                        params.append(name_pattern)
                    else:
                        if case_sensitive:
                            query_parts.append("AND file_name LIKE ?")
                        else:
                            query_parts.append("AND LOWER(file_name) LIKE LOWER(?)")
                        params.append(f"%{name_pattern}%")

                # File type search
                if file_type:
                    if case_sensitive:
                        query_parts.append("AND file_type = ?")
                    else:
                        query_parts.append("AND LOWER(file_type) = LOWER(?)")
                    params.append(file_type)

                # Parent directory search
                if parent_directory:
                    if exact_match:
                        if case_sensitive:
                            query_parts.append("AND parent_directory = ?")
                        else:
                            query_parts.append("AND LOWER(parent_directory) = LOWER(?)")
                        params.append(parent_directory)
                    else:
                        if case_sensitive:
                            query_parts.append("AND parent_directory LIKE ?")
                        else:
                            query_parts.append("AND LOWER(parent_directory) LIKE LOWER(?)")
                        params.append(f"%{parent_directory}%")

                # File size filters
                if size_min is not None:
                    query_parts.append("AND file_size >= ?")
                    params.append(size_min)

                if size_max is not None:
                    query_parts.append("AND file_size <= ?")
                    params.append(size_max)

                # Date range search (using modified_at)
                if date_from:
                    query_parts.append("AND modified_at >= ?")
                    params.append(date_from.isoformat())

                if date_to:
                    query_parts.append("AND modified_at <= ?")
                    params.append(date_to.isoformat())

                # Add ordering and limit
                query_parts.append("ORDER BY modified_at DESC")
                query_parts.append("LIMIT ?")
                params.append(limit)

                # Execute query
                query = " ".join(query_parts)
                print(f"🔍 Executing query: {query}")
                print(f"📝 With parameters: {params}")
                c.execute(query, params)
                rows = c.fetchall()
                print(f"📊 Query returned {len(rows)} results")

                # Convert to FileIndexResult objects
                results = []
                for row in rows:
                    result = FileIndexResult(
                        id=row[0],
                        file_path=row[1],
                        file_name=row[2],
                        file_size=row[3] or 0,
                        file_type=row[4] or "",
                        parent_directory=row[5] or "",
                        created_at=row[6] or "",
                        modified_at=row[7] or "",
                        indexed_at=row[8] or "",
                        is_accessible=row[9] or 0
                    )
                    results.append(result)

                return results

        except Exception as e:
            print(f"File index search error: {e}")
            return []

    def search_both_tables(self,
                          name_pattern: str = "",
                          file_type: str = "",
                          exact_match: bool = False,
                          case_sensitive: bool = False,
                          limit: int = 1000) -> Dict[str, List]:
        """
        Search both organized files and file index tables

        Returns:
            Dictionary with 'organized' and 'indexed' keys containing respective results
        """
        # Search organized files
        organized_results = self.search_files(
            name_pattern=name_pattern,
            file_type=file_type,
            exact_match=exact_match,
            case_sensitive=case_sensitive,
            limit=limit
        )

        # Search file index
        indexed_results = self.search_file_index(
            name_pattern=name_pattern,
            file_type=file_type,
            exact_match=exact_match,
            case_sensitive=case_sensitive,
            limit=limit
        )

        return {
            'organized': organized_results,
            'indexed': indexed_results
        }

    def search_by_regex(self, 
                       name_regex: str = "",
                       tags_regex: str = "") -> List[SearchResult]:
        """
        Search using regular expressions (more advanced pattern matching)

        Args:
            name_regex: Regular expression for file names
            tags_regex: Regular expression for tags

        Returns:
            List of SearchResult objects
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT * FROM files")
                all_rows = c.fetchall()

                results = []

                for row in all_rows:
                    original_name = row[1] or ""
                    tags = row[5] or ""

                    name_match = True
                    tags_match = True

                    # Check name regex
                    if name_regex:
                        try:
                            name_match = bool(re.search(name_regex, original_name, re.IGNORECASE))
                        except re.error:
                            name_match = False

                    # Check tags regex
                    if tags_regex:
                        try:
                            tags_match = bool(re.search(tags_regex, tags, re.IGNORECASE))
                        except re.error:
                            tags_match = False

                    if name_match and tags_match:
                        result = SearchResult(
                            id=row[0],
                            original_name=row[1],
                            new_path=row[2],
                            file_type=row[3],
                            moved_at=row[4],
                            tags=row[5] or ""
                        )
                        results.append(result)

                return results

        except Exception as e:
            print(f"Regex search error: {e}")
            return []

    def get_all_file_types(self, include_file_index: bool = True) -> List[str]:
        """Get all unique file types in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()

                # Get file types from organized files table
                c.execute("SELECT DISTINCT file_type FROM files WHERE file_type IS NOT NULL")
                organized_types = set(row[0] for row in c.fetchall())

                # Get file types from file index if requested
                if include_file_index:
                    c.execute("SELECT DISTINCT file_type FROM file_index WHERE file_type IS NOT NULL AND file_type != ''")
                    indexed_types = set(row[0] for row in c.fetchall())
                    all_types = organized_types | indexed_types
                else:
                    all_types = organized_types

                return sorted(list(all_types))
        except:
            return []

    def get_all_tags(self) -> List[str]:
        """Get all unique tags in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute("SELECT DISTINCT tags FROM files WHERE tags IS NOT NULL AND tags != ''")
                all_tags = set()
                for row in c.fetchall():
                    tags = row[0].split(", ")
                    all_tags.update(tag.strip() for tag in tags if tag.strip())
                return sorted(list(all_tags))
        except:
            return []

    def get_search_stats(self) -> Dict[str, Any]:
        """Get statistics about both database tables for search context"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()

                # Organized files stats
                c.execute("SELECT COUNT(*) FROM files")
                total_organized_files = c.fetchone()[0]

                c.execute("SELECT COUNT(*) FROM files WHERE tags IS NOT NULL AND tags != ''")
                tagged_files = c.fetchone()[0]

                c.execute("SELECT MIN(moved_at), MAX(moved_at) FROM files")
                organized_date_range = c.fetchone()

                c.execute("SELECT file_type, COUNT(*) as count FROM files GROUP BY file_type ORDER BY count DESC LIMIT 5")
                organized_top_types = c.fetchall()

                # File index stats
                c.execute("SELECT COUNT(*) FROM file_index")
                total_indexed_files = c.fetchone()[0]

                c.execute("SELECT COUNT(*) FROM file_index WHERE is_accessible = 1")
                accessible_files = c.fetchone()[0]

                c.execute("SELECT MIN(modified_at), MAX(modified_at) FROM file_index WHERE modified_at IS NOT NULL")
                index_date_range = c.fetchone()

                c.execute("SELECT file_type, COUNT(*) as count FROM file_index GROUP BY file_type ORDER BY count DESC LIMIT 5")
                index_top_types = c.fetchall()

                c.execute("SELECT SUM(file_size) FROM file_index WHERE file_size IS NOT NULL")
                total_size = c.fetchone()[0] or 0

                return {
                    "organized_files": {
                        "total_files": total_organized_files,
                        "tagged_files": tagged_files,
                        "untagged_files": total_organized_files - tagged_files,
                        "date_range": organized_date_range,
                        "top_file_types": organized_top_types
                    },
                    "indexed_files": {
                        "total_files": total_indexed_files,
                        "accessible_files": accessible_files,
                        "inaccessible_files": total_indexed_files - accessible_files,
                        "date_range": index_date_range,
                        "top_file_types": index_top_types,
                        "total_size_bytes": total_size
                    }
                }
        except Exception as e:
            print(f"Stats error: {e}")
            return {
                "organized_files": {
                    "total_files": 0,
                    "tagged_files": 0,
                    "untagged_files": 0,
                    "date_range": (None, None),
                    "top_file_types": []
                },
                "indexed_files": {
                    "total_files": 0,
                    "accessible_files": 0,
                    "inaccessible_files": 0,
                    "date_range": (None, None),
                    "top_file_types": [],
                    "total_size_bytes": 0
                }
            }

    def quick_search(self, query: str, search_index: bool = True) -> Dict[str, List]:
        """
        Quick search that searches across name and tags simultaneously

        Args:
            query: Search query string
            search_index: Whether to also search the file index

        Returns:
            Dictionary with search results from both tables
        """
        if search_index:
            return self.search_both_tables(
                name_pattern=query,
                exact_match=False,
                case_sensitive=False
            )
        else:
            organized_results = self.search_files(
                name_pattern=query,
                tags_pattern=query,
                exact_match=False,
                case_sensitive=False
            )
            return {
                'organized': organized_results,
                'indexed': []
            }

    def search_by_size(self, 
                      min_size: Optional[int] = None,
                      max_size: Optional[int] = None,
                      name_pattern: str = "",
                      file_type: str = "") -> List[FileIndexResult]:
        """
        Search files by size (only available for file index)

        Args:
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            name_pattern: Optional name pattern
            file_type: Optional file type filter

        Returns:
            List of FileIndexResult objects
        """
        return self.search_file_index(
            name_pattern=name_pattern,
            file_type=file_type,
            size_min=min_size,
            size_max=max_size
        )

    def search_by_directory(self, directory_pattern: str) -> List[FileIndexResult]:
        """
        Search files by parent directory (only available for file index)

        Args:
            directory_pattern: Pattern to search in parent directory

        Returns:
            List of FileIndexResult objects
        """
        return self.search_file_index(parent_directory=directory_pattern)

class SearchFilter:
    """Helper class for building complex search filters"""

    def __init__(self):
        self.filters = {}

    def by_name(self, pattern: str, exact: bool = False, case_sensitive: bool = False):
        """Add name filter"""
        self.filters['name_pattern'] = pattern
        self.filters['exact_match'] = exact
        self.filters['case_sensitive'] = case_sensitive
        return self

    def by_tags(self, pattern: str):
        """Add tags filter"""
        self.filters['tags_pattern'] = pattern
        return self

    def by_file_type(self, file_type: str):
        """Add file type filter"""
        self.filters['file_type'] = file_type
        return self

    def by_date_range(self, from_date: datetime = None, to_date: datetime = None):
        """Add date range filter"""
        if from_date:
            self.filters['date_from'] = from_date
        if to_date:
            self.filters['date_to'] = to_date
        return self

    def last_days(self, days: int):
        """Filter for files from last N days"""
        self.filters['date_from'] = datetime.now() - timedelta(days=days)
        return self

    def limit(self, count: int):
        """Limit number of results"""
        self.filters['limit'] = count
        return self

    def search(self, searcher: FileSearcher) -> List[SearchResult]:
        """Execute the search with built filters"""
        return searcher.search_files(**self.filters)

def format_search_results(results, include_path: bool = True) -> str:
    """
    Format search results for display (supports both SearchResult and FileIndexResult)

    Args:
        results: List of search results or dict with organized/indexed results
        include_path: Whether to include full path in output

    Returns:
        Formatted string of results
    """
    # Handle dictionary input from search_both_tables
    if isinstance(results, dict):
        output_lines = []

        if results.get('organized'):
            output_lines.append(f"📁 ORGANIZED FILES ({len(results['organized'])} found):")
            output_lines.append("=" * 60)
            organized_output = format_search_results(results['organized'], include_path)
            if organized_output.startswith("No files"):
                output_lines.append("No organized files found.")
            else:
                output_lines.extend(organized_output.split('\n')[2:])  # Skip header
            output_lines.append("")

        if results.get('indexed'):
            output_lines.append(f"🗃️ INDEXED FILES ({len(results['indexed'])} found):")
            output_lines.append("=" * 60)
            indexed_output = format_file_index_results(results['indexed'], include_path)
            if indexed_output.startswith("No files"):
                output_lines.append("No indexed files found.")
            else:
                output_lines.extend(indexed_output.split('\n')[2:])  # Skip header

        return "\n".join(output_lines)

    # Handle list of SearchResult objects
    if not results:
        return "No files found matching your criteria."

    output_lines = [f"Found {len(results)} file(s):\n"]
    output_lines.append("-" * 80)

    for i, result in enumerate(results, 1):
        line = f"{i:3}. {result.original_name}"

        if result.file_type:
            line += f" ({result.file_type})"

        if include_path and result.new_path:
            line += f"\n     → {result.new_path}"

        if hasattr(result, 'tags') and result.tags:
            line += f"\n     🏷️ {result.tags}"

        if hasattr(result, 'moved_at_display'):
            line += f"\n     📅 {result.moved_at_display}"

        output_lines.append(line)
        output_lines.append("")

    return "\n".join(output_lines)

def format_file_index_results(results: List[FileIndexResult], include_path: bool = True) -> str:
    """
    Format file index search results for display

    Args:
        results: List of FileIndexResult objects
        include_path: Whether to include full path in output

    Returns:
        Formatted string of results
    """
    if not results:
        return "No files found matching your criteria."

    output_lines = [f"Found {len(results)} file(s):\n"]
    output_lines.append("-" * 80)

    for i, result in enumerate(results, 1):
        line = f"{i:3}. {result.file_name}"

        if result.file_type:
            line += f" ({result.file_type})"

        if include_path and result.file_path:
            line += f"\n     📍 {result.file_path}"

        if result.file_size > 0:
            size_str = format_file_size(result.file_size)
            line += f"\n     💾 {size_str}"

        line += f"\n     📅 Modified: {result.modified_at_display}"
        line += f"\n     📂 {result.parent_directory}"

        if not result.is_accessible:
            line += "\n     ⚠️ File not accessible"

        output_lines.append(line)
        output_lines.append("")

    return "\n".join(output_lines)

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.1f} PB"

def export_search_results(results: List[SearchResult], filename: str = None) -> str:
    """
    Export search results to CSV file

    Args:
        results: List of search results
        filename: Output filename (optional)

    Returns:
        Path to exported file
    """
    import csv
    from pathlib import Path

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_results_{timestamp}.csv"

    output_path = Path(filename)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Original Name", "New Path", "File Type", "Moved At", "Tags"])

        for result in results:
            writer.writerow([
                result.id,
                result.original_name,
                result.new_path,
                result.file_type,
                result.moved_at,
                result.tags
            ])

    return str(output_path)

# Example usage and testing
if __name__ == "__main__":
    # Initialize searcher
    searcher = FileSearcher()

    # Example searches
    print("=== Basic Search Examples ===")

    # Search by name
    results = searcher.search_files(name_pattern="document", exact_match=False)
    print(f"Files containing 'document': {len(results)} found")

    # Search by tags
    results = searcher.search_files(tags_pattern="important")
    print(f"Files tagged with 'important': {len(results)} found")

    # Search with multiple criteria
    results = searcher.search_files(
        name_pattern="report",
        file_type=".pdf",
        tags_pattern="work"
    )
    print(f"PDF reports tagged with 'work': {len(results)} found")

    # Quick search
    results = searcher.quick_search("presentation")
    print(f"Quick search for 'presentation': {len(results)} found")

    # Using SearchFilter
    filter_results = (SearchFilter()
                     .by_name("budget")
                     .by_file_type(".xlsx")
                     .last_days(30)
                     .limit(10)
                     .search(searcher))
    print(f"Excel budget files from last 30 days: {len(filter_results)} found")

    # Get database stats
    stats = searcher.get_search_stats()
    print(f"\n=== Database Statistics ===")
    print(f"Total files: {stats['total_files']}")
    print(f"Tagged files: {stats['tagged_files']}")
    print(f"Top file types: {stats['top_file_types'][:3]}")