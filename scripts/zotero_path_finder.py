"""
Find Zotero data directory across different platforms.
"""
import os
import platform
import json
from pathlib import Path

def find_zotero_data_directory():
    """
    Find the Zotero data directory on different platforms.
    
    Returns:
        str: Path to Zotero data directory or None if not found
    """
    system = platform.system()
    home = Path.home()
    
    # Common Zotero data directory locations
    possible_locations = []
    
    if system == "Darwin":  # macOS
        possible_locations.extend([
            home / "Zotero",
            home / "Documents" / "Zotero",
            home / "Library" / "Application Support" / "Zotero" / "Profiles",
        ])
    elif system == "Windows":
        possible_locations.extend([
            home / "Zotero",
            home / "Documents" / "Zotero",
            Path(os.environ.get("APPDATA", "")) / "Zotero" / "Zotero" / "Profiles" if os.environ.get("APPDATA") else None,
        ])
    else:  # Linux
        possible_locations.extend([
            home / "Zotero",
            home / "Documents" / "Zotero",
            home / ".zotero" / "zotero",
            home / ".local" / "share" / "zotero",
        ])
    
    # Remove None values
    possible_locations = [loc for loc in possible_locations if loc]
    
    # Check each location for the storage folder
    for location in possible_locations:
        if location.exists():
            storage_path = location / "storage"
            if storage_path.exists() and storage_path.is_dir():
                return str(location)
    
    # Try to find from Zotero preferences
    zotero_prefs = find_zotero_prefs()
    if zotero_prefs:
        return zotero_prefs
    
    return None

def find_zotero_prefs():
    """
    Try to find Zotero data directory from Zotero preferences.
    """
    system = platform.system()
    home = Path.home()
    
    prefs_locations = []
    
    if system == "Darwin":  # macOS
        prefs_locations.append(home / "Library" / "Preferences" / "org.zotero.zotero.plist")
    elif system == "Windows":
        appdata = Path(os.environ.get("APPDATA", ""))
        if appdata:
            prefs_locations.append(appdata / "Zotero" / "Zotero" / "prefs.js")
    else:  # Linux
        prefs_locations.extend([
            home / ".zotero" / "zotero" / "prefs.js",
            home / ".config" / "zotero" / "prefs.js",
        ])
    
    for prefs_file in prefs_locations:
        if prefs_file.exists():
            try:
                # Try to parse prefs.js for dataDir
                with open(prefs_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Look for user_pref("extensions.zotero.dataDir", "...");
                    import re
                    match = re.search(r'user_pref\("extensions\.zotero\.dataDir",\s*"([^"]+)"\)', content)
                    if match:
                        data_dir = match.group(1).replace('\\\\', '/')
                        if Path(data_dir).exists():
                            return data_dir
            except:
                continue
    
    return None

def get_default_pdf_dir():
    """
    Get the default PDF directory with automatic detection.
    """
    # First check if PDF_DIR is set in environment
    pdf_dir = os.getenv('PDF_DIR')
    if pdf_dir and os.path.exists(pdf_dir):
        return pdf_dir
    
    # Try to find Zotero data directory
    zotero_dir = find_zotero_data_directory()
    if zotero_dir:
        return zotero_dir
    
    # Fall back to common location
    default_path = os.path.expanduser('~/Zotero')
    if os.path.exists(default_path):
        return default_path
    
    # Last resort - current directory
    return os.getcwd()

if __name__ == "__main__":
    found_dir = find_zotero_data_directory()
    if found_dir:
        print(f"Found Zotero data directory: {found_dir}")
        print(f"Storage directory: {os.path.join(found_dir, 'storage')}")
    else:
        print("Could not find Zotero data directory")
        print(f"Using default: {get_default_pdf_dir()}")