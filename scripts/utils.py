"""
Utility functions for logging, history tracking, etc.
"""
import os
import json
import logging
from datetime import datetime

def setup_logger(name: str, log_file: str, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    fh = logging.FileHandler(log_file)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger

def mark_done(key: str, done_file: str = './logs/done.txt'):
    os.makedirs(os.path.dirname(done_file), exist_ok=True)
    with open(done_file, 'a') as f:
        f.write(key + '\n')

def is_done(key: str, done_file: str = './logs/done.txt') -> bool:
    if not os.path.exists(done_file):
        return False
    with open(done_file) as f:
        return key in f.read().splitlines()

def save_checkpoint(data: dict, checkpoint_file: str = './logs/checkpoint.json'):
    """Save processing checkpoint for resume functionality."""
    os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
    data['timestamp'] = datetime.now().isoformat()
    with open(checkpoint_file, 'w') as f:
        json.dump(data, f, indent=2)

def load_checkpoint(checkpoint_file: str = './logs/checkpoint.json') -> dict:
    """Load processing checkpoint."""
    if not os.path.exists(checkpoint_file):
        return None
    try:
        with open(checkpoint_file) as f:
            return json.load(f)
    except:
        return None

def clear_checkpoint(checkpoint_file: str = './logs/checkpoint.json'):
    """Clear checkpoint after successful completion."""
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
