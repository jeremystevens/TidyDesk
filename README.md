
# 🧠 TidyDesk v2.0.1: Smart Desktop Organizer

**TidyDesk** is an intelligent desktop cleanup tool that uses AI to automatically tag and organize your cluttered files and folders. With an intuitive GUI, powerful backend features, live monitoring capabilities, advanced search functionality, and comprehensive file management tools, it keeps your digital workspace clean and productive.

![TidyDesk Screenshot](https://i.ibb.co/BHp8x37w/tidydesk.png)


---

## 🚀 Features

### 🔍 **Core Organization**
- 🤖 **AI File Tagging** (Optional): Uses OpenAI to understand and categorize files intelligently
- 🗂️ **Automatic Organization**: Sorts files into folders based on AI tags or default rules
- 🔄 **Complete Undo System**: Restore all files to their original locations from any session
- 🧠 **Local File Indexing**: Maintains a SQLite database of moved files for tracking and reliability
- 🎛️ **Toggle AI Usage**: Disable AI tagging to save API usage and rely on standard rules
- 📜 **Real-time Activity Log**: See live status updates for each file processed
- 🏷️ **Tag-Based Regrouping**: Reorganize existing files by their AI-generated tags

### 📡 **Live Desktop Monitoring** ⭐ *NEW*
- 🔄 **Real-time File Detection**: Automatically monitors `~/Desktop` for new files using watchdog
- 🤖 **Auto AI Tagging**: Configurable AI tagging for newly detected files
- 📂 **Smart Organization Modes**: Three organization options:
  - `Desktop Folder` → Creates `~/Desktop/TidyDesk` and moves files there
  - `Organized Folder` → Uses existing cleanup logic with categorization
  - `Do Not Move` → Index and tag only, leave files in place
- 📊 **Live Status Updates**: Real-time activity log with detailed file processing status
- 💾 **Persistent Settings**: All monitoring preferences saved automatically

### ⚡ **Performance & Multi-Threading** ⭐ *NEW*
- 🚀 **Parallel File Indexing**: Multi-threaded processing using ThreadPoolExecutor
- 🎮 **CUDA-Ready Architecture**: Optimized for systems with CUDA capabilities
- 🧠 **Intelligent Worker Scaling**: Automatically adjusts thread count based on CPU cores
- 📦 **Batch Processing**: Processes files in optimized batches for better performance
- 📈 **Progress Tracking**: Real-time progress updates with file count and speed metrics
- 💾 **Memory Optimization**: Efficient memory usage for large file sets

### 🕰️ **Filesystem Time Machine** ⭐ *NEW*
- 📸 **Snapshot System**: Create versioned snapshots of any folder at configurable intervals
- 👀 **Automatic Monitoring**: Watch multiple folders with customizable snapshot intervals
- 🔍 **Smart Comparison**: Compare snapshots with detailed diff analysis (added/removed/modified files)
- ↩️ **One-click Restore**: Restore any snapshot to a chosen destination
- 🗂️ **Storage Optimization**: Automatic cleanup of old snapshots beyond configurable limits
- 📊 **Statistics Dashboard**: Comprehensive metrics on snapshots, disk usage, and activity

### 🎨 **Enhanced UI & Themes** ⭐ *NEW*
- 🎨 **Dynamic Theme System**: Multiple built-in themes with live preview and switching
- 📱 **Compact Horizontal Layout**: Redesigned GUI for better space utilization
- ⚙️ **Environment Settings**: Secure API key management with .env file integration
- 💾 **Settings Persistence**: Save/load functionality for all configuration options
- 📊 **Enhanced Progress Visualization**: Detailed progress meters with comprehensive tracking
- 🔧 **Status Bar System**: Clean status updates instead of popup messages

### 🔍 **Advanced Search & Discovery** ⭐ *ENHANCED*
- 🔎 **Multi-Criteria Search**: Search by filename, tags, file type, and date ranges
- 🎯 **Smart Filtering**: Date ranges, tag-based filtering, and file type filtering
- 📋 **Export Search Results**: Export results to CSV format with detailed metadata
- 🏷️ **Tag Management**: Visual tag suggestions and clickable tag searches
- 📊 **Search Analytics**: Detailed statistics and result management
- 🔍 **Dual Database Search**: Search both organized files and system file index
- 📱 **Tabbed Search Interface**: Organized search with Basic, Advanced, and Results tabs
- 🎯 **Quick Filters**: Pre-built filters for recent files, untagged files, and more
- 📂 **Context Menu Actions**: Right-click operations for file management
- 👁️ **File Preview Integration**: Preview files directly from search results

### 👁️ **File Preview System** ⭐ *NEW*
- 📄 **Text File Preview**: View content of text files, code files, and documents
- 🖼️ **Image Preview**: Display images with proper scaling and quality
- 📊 **File Metadata Display**: Show detailed file information including size, dates, and properties
- 🎨 **Syntax Highlighting**: Code syntax highlighting for programming files
- 📱 **Responsive Preview Window**: Scalable preview interface with multiple view modes
- 🔍 **Search Integration**: Preview files directly from search results
- 📂 **Path Information**: Complete file path and location details

### 📜 **Session & History Management** ⭐ *ENHANCED*
- 🔄 **Session-Based Organization**: Each cleanup operation creates a trackable session
- 📊 **Session Analytics**: View statistics and progress for each session
- ↩️ **Selective Undo**: Choose specific sessions to undo from history
- 📋 **Comprehensive History**: Detailed logging of every file movement and operation
- 🏷️ **Session Naming**: Custom session names with automatic suggestions
- 📈 **Success Rate Tracking**: Monitor organization success rates and error patterns

---

## 🆕 What's New in v2.0.1

### 🔍 **Enhanced Search Capabilities**
- **Dual Database Search**: Now searches both organized files and system-wide file index
- **Advanced Search Interface**: Tabbed interface with Basic, Advanced, and Results sections
- **File Type Discovery**: Automatic detection of all available file types
- **Quick Filter Actions**: Pre-built filters for common search scenarios
- **Search Result Context Menus**: Right-click actions for file operations

### 👁️ **File Preview System**
- **Universal File Preview**: Preview text, images, and metadata for any file
- **Syntax Highlighting**: Code files display with proper syntax coloring
- **Image Scaling**: Automatic image resizing with quality preservation
- **Metadata Display**: Comprehensive file information including size and dates
- **Search Integration**: Preview files directly from search results

### 🎨 **UI/UX Improvements**
- **Status Bar System**: Replaced popup messages with clean status bar updates
- **Enhanced Progress Tracking**: More detailed progress indicators with ETA
- **Theme Consistency**: Improved theme application across all windows
- **Responsive Design**: Better scaling for different screen sizes

### 🔧 **Technical Enhancements**
- **Database Optimization**: Improved query performance for large datasets
- **Error Handling**: Better error recovery and user feedback
- **Memory Management**: Optimized memory usage for large file operations
- **Cross-Platform Compatibility**: Enhanced support for different operating systems

---

## 📦 Installation

1. **Clone the repo**:
    ```bash
    git clone https://github.com/jeremystevens/tidydesk.git
    cd tidydesk
    ```

2. **Create and activate virtual environment** (optional but recommended):
    ```bash
    python -m venv venv
    venv\Scripts\activate    # On Windows
    # source venv/bin/activate  # On macOS/Linux
    ```

3. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4. **Set up `.env` file**:
    Create a `.env` file in the project root and add your OpenAI key:
    ```env
    OPENAI_API_KEY=your-api-key-here
    ```

---

## 🧪 How to Run

Start the application with:
```bash
python main.py
```

> ✅ You'll be greeted with a modern, tabbed GUI where you can:
> - Toggle live monitoring and AI features
> - Start cleanup operations with real-time progress
> - Access the Time Machine for folder versioning
> - Search and manage your organized files with advanced filters
> - Preview files directly in the application
> - Customize themes and settings with persistent storage

---

## 📁 Project Structure

```
tidydesk/
│
├── src/
│   ├── gui.py              # Modern tabbed GUI using TTKBootstrap
│   ├── organizer.py        # AI tagging, organizing logic, undo handling
│   ├── desktop_watcher.py  # Real-time desktop monitoring with watchdog
│   ├── index_files.py      # Multi-threaded file indexing system
│   ├── time_machine.py     # Filesystem snapshot and versioning
│   ├── time_machine_gui.py # Time Machine interface
│   ├── theme_manager.py    # Dynamic theme management
│   ├── search_module.py    # Advanced search functionality
│   ├── search_window.py    # Search interface with preview integration
│   ├── file_preview.py     # File preview system
│   ├── db.py               # SQLite database handling
│   └── ai_tagger.py        # OpenAI batch tagging logic
│
├── .env                    # API key config (not committed)
├── config.json             # Application settings and preferences
├── requirements.txt        # Required libraries
├── main.py                 # Entry point
├── FEATURES.md             # Comprehensive feature documentation
└── file_index.db           # (auto-created) File metadata database
```

---

## 🔧 Key Dependencies

- **ttkbootstrap**: Modern GUI framework
- **openai**: AI-powered file tagging
- **watchdog**: Real-time filesystem monitoring
- **pillow**: Image processing and preview capabilities
- **python-dotenv**: Environment variable management

---

## ⚡ Performance Features

- **Multi-threading**: Utilizes all CPU cores for faster processing
- **Batch Operations**: Optimized batch processing for large file sets
- **Smart Caching**: Efficient memory usage and database operations
- **Progress Optimization**: Real-time progress tracking without performance impact
- **System Integration**: OS-specific optimizations for Windows, macOS, and Linux
- **Database Indexing**: Optimized queries for instant search results

---

## 🎯 Use Cases

- **Desktop Cleanup**: Automatically organize cluttered desktops with AI assistance
- **File Management**: AI-powered tagging and intelligent categorization
- **Real-time Monitoring**: Keep desktops organized automatically with live monitoring
- **Version Control**: Track folder changes over time with comprehensive snapshots
- **File Discovery**: Advanced search across organized and indexed file collections
- **File Preview**: Quick file inspection without opening external applications
- **Workflow Automation**: Streamline file organization workflows with session management
- **Data Analytics**: Track organization patterns and file management statistics

---

## ⚠️ Notes

- Ensure your Desktop path is accessible (not under restricted OneDrive redirection)
- Live monitoring runs in background threads for optimal performance
- AI tagging uses paid OpenAI API calls—use toggles wisely to control costs
- Time Machine snapshots are stored locally and can be configured for automatic cleanup
- Multi-threading performance scales with available CPU cores
- File preview supports most common file types with graceful fallbacks
- Search operates on both organized files and system-wide file index for comprehensive results

---

## 🚀 Recent Major Updates

### v2.0.1 Features
- **Universal File Preview**: Complete file preview system with syntax highlighting
- **Enhanced Search Engine**: Dual database search with advanced filtering
- **Improved UI/UX**: Status bar system and enhanced progress tracking
- **Better Performance**: Optimized database queries and memory management

### v2.0.0 Features
- **Live Desktop Monitoring**: Real-time file detection and organization
- **Multi-threaded Performance**: Up to 10x faster file indexing
- **Filesystem Time Machine**: Complete folder versioning system
- **Dynamic Themes**: Multiple themes with live switching
- **Enhanced Settings**: Comprehensive configuration management

---

## 📜 License

MIT License © 2025 Jeremy Stevens

---

## 🔮 Future Roadmap

- **Cloud Integration**: Support for cloud storage services
- **Advanced AI Models**: Integration with additional AI services
- **Mobile Companion**: Mobile app for remote file management
- **Plugin System**: Extensible architecture for custom functionality
- **Collaborative Features**: Multi-user file organization workflows

**TidyDesk v2.0.1** - Your intelligent desktop companion for the modern digital workspace! 🚀
