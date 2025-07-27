
import json
from pathlib import Path
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class ThemeManager:
    """Manages theme configuration and application"""
    
    def __init__(self):
        self.config_path = Path("theme_config.json")
        self.available_themes = {
            "superhero": "🦸 Superhero (Dark)",
            "darkly": "🌙 Darkly (Dark)", 
            "solar": "☀️ Solar (Dark)",
            "cyborg": "🤖 Cyborg (Dark)",
            "vapor": "💨 Vapor (Dark)",
            "cosmo": "🌌 Cosmo (Light)",
            "flatly": "📱 Flatly (Light)",
            "journal": "📰 Journal (Light)",
            "litera": "📖 Litera (Light)",
            "lumen": "💡 Lumen (Light)",
            "minty": "🌿 Minty (Light)",
            "pulse": "💓 Pulse (Light)",
            "sandstone": "🏔️ Sandstone (Light)",
            "united": "🤝 United (Light)",
            "yeti": "❄️ Yeti (Light)"
        }
        self.current_theme = self.load_current_theme()
    
    def load_current_theme(self):
        """Load the current theme from config"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                return config.get('current_theme', 'superhero')
        except Exception:
            pass
        return 'superhero'  # Default theme
    
    def save_current_theme(self, theme_name):
        """Save the current theme to config"""
        try:
            config = {'current_theme': theme_name}
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            self.current_theme = theme_name
        except Exception as e:
            print(f"Error saving theme config: {e}")
    
    def get_available_themes(self):
        """Get list of available themes"""
        return list(self.available_themes.keys())
    
    def get_theme_display_name(self, theme_name):
        """Get display name for a theme"""
        return self.available_themes.get(theme_name, theme_name.title())
    
    def apply_theme(self, theme_name, app_window=None):
        """Apply a theme to the application"""
        try:
            if app_window and hasattr(app_window, 'style'):
                # Apply theme to existing window
                app_window.style.theme_use(theme_name)
                self.save_current_theme(theme_name)
                return True
            else:
                # Just save for next startup
                self.save_current_theme(theme_name)
                return True
        except Exception as e:
            print(f"Error applying theme {theme_name}: {e}")
            return False
    
    def get_theme_preview_colors(self, theme_name):
        """Get preview colors for a theme (simplified)"""
        # This is a simplified preview - in a full implementation,
        # you'd extract actual colors from the theme
        dark_themes = ['superhero', 'darkly', 'solar', 'cyborg', 'vapor']
        if theme_name in dark_themes:
            return {
                'bg': '#2c3e50',
                'fg': '#ecf0f1',
                'accent': '#3498db'
            }
        else:
            return {
                'bg': '#ffffff',
                'fg': '#2c3e50',
                'accent': '#007bff'
            }

# Global theme manager instance
theme_manager = ThemeManager()