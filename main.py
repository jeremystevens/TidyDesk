from src.gui import build_gui
from src.db import init_db
init_db()
if __name__ == "__main__":
    build_gui()