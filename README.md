# 🧠 TidyDesk: Smart Desktop Organizer

**TidyDesk** is an intelligent desktop cleanup tool that uses AI to automatically tag and organize your cluttered files and folders. With an intuitive GUI and powerful backend features, it keeps your desktop neat without losing control.

---

## 🚀 Features

- 🔍 **AI File Tagging** (Optional): Uses OpenAI to understand and categorize files intelligently.
- 🗂️ **Automatic Organization**: Sorts files into folders based on AI tags or default rules.
- 🔄 **Undo Cleanup**: Restore all files to their original locations from a session with one click.
- 🧠 **Local File Indexing**: Maintains a SQLite database of moved files for tracking and reliability.
- 🎛️ **Toggle AI Usage**: Disable AI tagging to save API usage and rely on standard rules.
- 📜 **Activity Log**: See real-time status updates for each file processed.

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

> ✅ You’ll be greeted with a user-friendly GUI where you can toggle AI, start cleanup, or undo the last operation.

---

## 📁 Project Structure

```
tidydesk/
│
├── src/
│   ├── gui.py              # GUI interface using TTKBootstrap
│   ├── organizer.py        # AI tagging, organizing logic, undo handling
│   ├── db.py               # SQLite handling
│   └── ai_tagger.py        # OpenAI batch tagging logic
│
├── .env                    # API key config (not committed)
├── requirements.txt        # Required libraries
├── main.py                 # Entry point
└── file_index.db           # (auto-created) File metadata database
```

---

## ⚠️ Notes

- Ensure your Desktop is not under OneDrive redirection unless modified in the code.
- Undo action only works for the most recent cleanup session.
- AI tagging uses paid OpenAI API calls—use the toggle wisely!

---

## 📜 License

MIT License © 2025 Jeremy Stevensa