"""
Utility functions for logging, history tracking, etc.
"""
import os
import json
import logging
from datetime import datetime
from threading import Lock

_done_cache = None
_done_cache_lock = Lock()

# Get project root directory for absolute paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def setup_logger(name: str, log_file: str, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    logger.propagate = False
    return logger

def _load_done_cache(done_file: str):
    global _done_cache
    with _done_cache_lock:
        if _done_cache is None:
            if os.path.exists(done_file):
                with open(done_file) as f:
                    _done_cache = set(line.strip() for line in f if line.strip())
            else:
                _done_cache = set()

def mark_done(key: str, done_file: str = None):
    if done_file is None:
        done_file = os.path.join(PROJECT_ROOT, 'logs', 'done.txt')
    os.makedirs(os.path.dirname(done_file), exist_ok=True)
    _load_done_cache(done_file)
    with _done_cache_lock:
        if key in _done_cache:
            return
        _done_cache.add(key)
        with open(done_file, 'a') as f:
            f.write(key + '\n')

def is_done(key: str, done_file: str = None) -> bool:
    if done_file is None:
        done_file = os.path.join(PROJECT_ROOT, 'logs', 'done.txt')
    _load_done_cache(done_file)
    with _done_cache_lock:
        return key in _done_cache

def save_checkpoint(data: dict, checkpoint_file: str = None):
    """Save processing checkpoint for resume functionality."""
    if checkpoint_file is None:
        checkpoint_file = os.path.join(PROJECT_ROOT, 'logs', 'checkpoint.json')
    os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
    data['timestamp'] = datetime.now().isoformat()
    with open(checkpoint_file, 'w') as f:
        json.dump(data, f, indent=2)

def load_checkpoint(checkpoint_file: str = None) -> dict:
    """Load processing checkpoint."""
    if checkpoint_file is None:
        checkpoint_file = os.path.join(PROJECT_ROOT, 'logs', 'checkpoint.json')
    if not os.path.exists(checkpoint_file):
        return None
    try:
        with open(checkpoint_file) as f:
            return json.load(f)
    except:
        return None

def clear_checkpoint(checkpoint_file: str = None):
    """Clear checkpoint after successful completion."""
    if checkpoint_file is None:
        checkpoint_file = os.path.join(PROJECT_ROOT, 'logs', 'checkpoint.json')
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
