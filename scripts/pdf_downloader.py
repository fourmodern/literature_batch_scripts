"""
Download PDFs from Zotero server when not available locally.
"""
import os
import time
import requests
from pathlib import Path
from typing import Optional, Tuple

def download_pdf_from_zotero(zot, item_key: str, file_key: str, save_path: str, max_retries: int = 3) -> bool:
    """
    Download PDF from Zotero server.
    
    Args:
        zot: Zotero API instance
        item_key: Parent item key
        file_key: Attachment file key
        save_path: Local path to save the PDF
        max_retries: Maximum number of retry attempts
        
    Returns:
        bool: True if download successful, False otherwise
    """
    # Silently attempt download unless debug mode
    
    for attempt in range(max_retries):
        try:
            # Download the file content using the correct method
            # pyzotero's file() method returns the binary content directly
            try:
                file_content = zot.file(file_key)
            except Exception as e:
                # Check if it's a 404 error
                if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                    if e.response.status_code == 404:
                        return False  # Silently fail on 404
                continue
            
            # Check if file_content is valid
            if file_content is None or len(file_content) == 0:
                continue
                
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Write the file
            with open(save_path, 'wb') as f:
                f.write(file_content)
            
            # Verify the file was written and has content
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                return True
            else:
                if os.path.exists(save_path):
                    os.remove(save_path)
                    
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"PDF not found on Zotero server (404)")
                return False
            elif e.response.status_code == 429:  # Rate limit
                wait_time = min(2 ** attempt * 5, 60)
                print(f"Rate limit hit. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"HTTP error downloading PDF: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error downloading PDF: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
                
        except Exception as e:
            print(f"Unexpected error downloading PDF: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    
    return False

def ensure_pdf_available(zot, item: dict, attachment: dict, pdf_base_dir: str, download_enabled: bool = False) -> Optional[str]:
    """
    Ensure PDF is available locally, downloading if necessary and enabled.
    
    Args:
        zot: Zotero API instance
        item: Item metadata dict
        attachment: Attachment metadata dict
        pdf_base_dir: Base directory for PDFs
        download_enabled: Whether to download missing PDFs
        
    Returns:
        str: Path to PDF if available, None otherwise
    """
    # Construct expected local path
    relative_path = attachment.get('path', '')
    file_key = attachment.get('fileKey', '')
    filename = attachment.get('filename', 'document.pdf')
    item_key = item.get('key', 'unknown')
    title = item.get('title', 'Unknown')[:50]
    
    # Silent operation for performance
    
    # Try different path constructions
    possible_paths = []
    
    if relative_path:
        if relative_path.startswith('storage/'):
            possible_paths.append(os.path.join(pdf_base_dir, relative_path))
        else:
            possible_paths.append(os.path.join(pdf_base_dir, 'storage', relative_path))
    
    if file_key:
        # Standard Zotero storage structure
        storage_path = os.path.join(pdf_base_dir, 'storage', file_key, filename)
        possible_paths.append(storage_path)
    
    # Check if PDF exists locally
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    
    # If not found locally and download is enabled
    if download_enabled and file_key:
        download_path = os.path.join(pdf_base_dir, 'storage', file_key, filename)
        
        if download_pdf_from_zotero(zot, item['key'], file_key, download_path):
            return download_path
    
    return None

def check_storage_permissions(pdf_base_dir: str) -> Tuple[bool, str]:
    """
    Check if we have write permissions to the storage directory.
    
    Returns:
        Tuple[bool, str]: (has_permission, error_message)
    """
    storage_dir = os.path.join(pdf_base_dir, 'storage')
    
    try:
        # Try to create storage directory
        os.makedirs(storage_dir, exist_ok=True)
        
        # Try to create a test file
        test_file = os.path.join(storage_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        
        return True, ""
    except PermissionError:
        return False, f"No write permission to storage directory: {storage_dir}"
    except Exception as e:
        return False, f"Error checking storage permissions: {e}"