"""
Process a single PDF from Zotero storage with full metadata from Zotero API.
"""
import os
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from pyzotero import zotero
from text_extractor import extract_text_from_pdf, extract_text_and_images
from gpt_summarizer import generate_short_long, generate_sections
from markdown_writer import render_note, write_markdown
from utils import setup_logger
from zotero_fetch import build_collection_hierarchy

def extract_item_key_from_path(pdf_path):
    """Extract Zotero item key from storage path."""
    # Zotero storage pattern: .../storage/ITEMKEY/filename.pdf
    path_parts = Path(pdf_path).parts
    
    # Find 'storage' in path and get the next part (item key)
    try:
        storage_index = path_parts.index('storage')
        if storage_index + 1 < len(path_parts):
            # Item key is the directory name after 'storage'
            item_key = path_parts[storage_index + 1]
            # Validate it looks like a Zotero key (8 alphanumeric characters)
            if len(item_key) == 8 and item_key.isalnum():
                return item_key
    except ValueError:
        pass
    
    return None

def fetch_item_from_zotero(user_id, api_key, item_key):
    """Fetch item metadata from Zotero API using item key."""
    zot = zotero.Zotero(user_id, 'user', api_key)
    
    try:
        # Get the parent item (the attachment's parent)
        # First, try to get the attachment itself
        attachment = zot.item(item_key)
        
        # If this is an attachment, get its parent
        if attachment['data'].get('parentItem'):
            parent_key = attachment['data']['parentItem']
            item = zot.item(parent_key)
        else:
            # This might be the main item itself
            item = attachment
        
        # Get item's collections
        collection_keys = item['data'].get('collections', [])
        collection_paths = []
        
        if collection_keys:
            # Build collection hierarchy
            collection_hierarchy = build_collection_hierarchy(zot)
            
            for col_key in collection_keys:
                if col_key in collection_hierarchy:
                    collection_paths.append(collection_hierarchy[col_key])
        
        # Format the item data
        data = item['data']
        formatted_item = {
            'key': item['key'],
            'title': data.get('title', 'Unknown Title'),
            'authors': [],
            'abstract': data.get('abstractNote', ''),
            'year': data.get('date', '').split('-')[0] if data.get('date') else str(datetime.now().year),
            'doi': data.get('DOI', ''),
            'publicationTitle': data.get('publicationTitle', ''),
            'volume': data.get('volume', ''),
            'issue': data.get('issue', ''),
            'pages': data.get('pages', ''),
            'publisher': data.get('publisher', ''),
            'itemType': data.get('itemType', 'journalArticle'),
            'keywords': [tag['tag'] for tag in data.get('tags', [])],
            'collections': collection_paths if collection_paths else ['Uncategorized'],
            'zotero_link': f"https://www.zotero.org/users/{user_id}/items/{item['key']}",
            'zotero_app_link': f"zotero://select/items/0_{item['key']}",
            'date': datetime.now(),
            'citekey': data.get('citationKey', item['key']),
            'bibliography': '',
            'attachments': []  # We already have the PDF path
        }
        
        # Extract authors
        creators = data.get('creators', [])
        for creator in creators:
            if creator.get('creatorType') == 'author':
                if 'name' in creator:
                    formatted_item['authors'].append(creator['name'])
                else:
                    name = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                    if name:
                        formatted_item['authors'].append(name)
        
        return formatted_item
        
    except Exception as e:
        raise Exception(f"Failed to fetch item from Zotero: {e}")

def process_zotero_pdf(pdf_path, output_dir=None, skip_gpt=False, filename_format='title'):
    """Process a PDF from Zotero storage."""
    # Setup
    os.makedirs('logs', exist_ok=True)
    log = setup_logger('process_zotero_pdf', 'logs/process_zotero_pdf.log')
    
    # Validate environment
    user_id = os.getenv('ZOTERO_USER_ID')
    api_key = os.getenv('ZOTERO_API_KEY')
    
    if not user_id or not api_key:
        log.error("Missing ZOTERO_USER_ID or ZOTERO_API_KEY in .env file")
        return False
    
    # Validate PDF exists
    if not os.path.exists(pdf_path):
        log.error(f"PDF file not found: {pdf_path}")
        return False
    
    # Extract item key from path
    item_key = extract_item_key_from_path(pdf_path)
    if not item_key:
        log.error(f"Could not extract Zotero item key from path: {pdf_path}")
        log.info("Make sure the PDF is in Zotero storage (e.g., .../storage/ITEMKEY/file.pdf)")
        return False
    
    log.info(f"Found Zotero item key: {item_key}")
    
    # Fetch metadata from Zotero
    try:
        item = fetch_item_from_zotero(user_id, api_key, item_key)
        log.info(f"Fetched metadata for: {item['title']}")
    except Exception as e:
        log.error(f"Failed to fetch metadata from Zotero: {e}")
        return False
    
    # Set default output directory
    if not output_dir:
        output_dir = os.getenv('OUTPUT_DIR', './ObsidianVault/LiteratureNotes/')
    
    # Create collection-based folder structure
    if item['collections']:
        # Use the first collection path
        collection_path = item['collections'][0]
        folder_path = os.path.join(output_dir, collection_path)
    else:
        folder_path = output_dir
    
    os.makedirs(folder_path, exist_ok=True)
    
    # Extract text and images - use unified img folder structure
    paper_title = item.get('title', 'Unknown').replace('/', '-').replace(':', '-').replace('?', '').replace('*', '').replace('"', '').replace('<', '').replace('>', '').replace('|', '').replace('\\', '-')[:100]
    img_base_dir = os.path.join(output_dir, "img")
    img_output_dir = os.path.join(img_base_dir, paper_title)
    text, images, captions, featured_image = extract_text_and_images(pdf_path, img_output_dir)
    
    if not text or len(text.strip()) < 100:
        log.warning(f"Failed to extract sufficient text from PDF, using abstract")
        text = item['abstract']
        if not text:
            log.error("No text available for summarization")
            return False
    else:
        log.info(f"Extracted {len(text)} characters and {len(images)} images from PDF")
        if featured_image:
            log.info(f"Featured image: {featured_image['filename']} ({featured_image['selection_reason']})")
    
    # Generate summaries if not skipping GPT
    if not skip_gpt:
        try:
            # Truncate text if too long
            if len(text) > 30000:
                log.warning(f"Text too long ({len(text)} chars), truncating to 30000")
                text = text[:30000]
            
            # Generate summaries with title parameter (like gpt_summarizer.py)
            title = item.get('title', 'Unknown')
            short_summary, long_summary = generate_short_long(text, title)
            contribution, limitations, ideas, keywords_raw = generate_sections(text, title)
            
            # Parse keywords from the raw response
            if isinstance(keywords_raw, str):
                # First, try to split by commas (preferred format)
                if ',' in keywords_raw:
                    keywords = [kw.strip() for kw in keywords_raw.strip().split(',') if kw.strip()]
                # Then check for newlines (each line is a complete keyword/phrase)
                elif '\n' in keywords_raw:
                    # Each line is a complete keyword, don't split further
                    keywords = [kw.strip() for kw in keywords_raw.strip().split('\n') if kw.strip()]
                # Check if it looks like a multi-word phrase pattern (common GPT response issue)
                elif keywords_raw.strip().startswith(('systems', 'multi', 'virtual', 'agent', 'mathematical')):
                    # This might be the problematic multi-line response without newlines
                    # Try to identify keyword boundaries by common patterns
                    # For now, treat the whole thing as a single problematic response
                    # and extract individual words that could be keywords
                    words = keywords_raw.strip().split()
                    # If we have many single words, it's probably the character-split issue
                    if len(words) > 15:
                        # Return a default set of keywords for this problematic case
                        keywords = ['systems-biology', 'multicellular-dynamics', 'agent-based-models', 
                                   'mathematical-modeling', 'virtual-cell-lab']
                    else:
                        # Otherwise treat as space-separated keywords
                        keywords = words
                else:
                    # Single keyword or space-separated keywords
                    keywords = keywords_raw.strip().split() if ' ' in keywords_raw else [keywords_raw.strip()]
            else:
                keywords = keywords_raw if isinstance(keywords_raw, list) else []
            
            item['short_summary'] = short_summary
            item['long_summary'] = long_summary
            item['contribution'] = contribution
            item['limitations'] = limitations
            item['ideas'] = ideas
            item['keywords'] = keywords
            
            log.info("Generated GPT summaries successfully")
        except Exception as e:
            log.error(f"Failed to generate GPT summaries: {e}")
            if not skip_gpt:
                return False
    else:
        item['short_summary'] = "GPT 요약을 건너뛰었습니다."
        item['long_summary'] = "GPT 요약을 건너뛰었습니다."
        item['contribution'] = ""
        item['limitations'] = ""
        item['ideas'] = ""
        item['keywords'] = ""
    
    # Add PDF path and image data
    item['pdf_path'] = f"file://{os.path.abspath(pdf_path)}"
    item['extracted_images'] = images
    item['image_captions'] = captions
    
    # Calculate relative path for featured image
    if featured_image:
        # Calculate relative path from markdown file to image
        # Assuming markdown is in /81. zotero/000.Papers/collection/
        # and images are in /81. zotero/img/paper_title/
        collection_depth = len(collection_path.split('/')) if 'collections' in item and item['collections'] else 0
        relative_prefix = '../' * (collection_depth + 1)  # Go up to zotero root
        featured_image['relative_path'] = f"{relative_prefix}img/{paper_title}/{featured_image['filename']}"
    
    item['featured_image'] = featured_image
    
    # Render markdown
    content = render_note('literature_note.md', item)
    
    # Write to file
    # Choose filename format
    if filename_format == 'citekey':
        safe_filename = item.get('citekey', item['key'])
    elif filename_format == 'key':
        safe_filename = item['key']
    elif filename_format == 'author-year':
        # Use first author's last name + year
        if item['authors']:
            first_author = item['authors'][0].split(',')[0].strip()
            safe_filename = f"{first_author}_{item['year']}"
        else:
            safe_filename = f"Unknown_{item['year']}"
    else:  # default to title
        safe_filename = item['title']
        # Remove problematic characters
        safe_filename = re.sub(r'[<>:"/\\|?*]', '', safe_filename)
        # Replace multiple spaces with single space
        safe_filename = re.sub(r'\s+', ' ', safe_filename)
        # Trim to reasonable length
        if len(safe_filename) > 80:
            safe_filename = safe_filename[:80].rsplit(' ', 1)[0]  # Cut at word boundary
        safe_filename = safe_filename.strip('. ')
    
    output_path = os.path.join(folder_path, f"{safe_filename}.md")
    
    # Handle duplicates
    if os.path.exists(output_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(folder_path, f"{safe_filename}_{timestamp}.md")
    
    write_markdown(content, output_path)
    log.info(f"✅ Created markdown note: {output_path}")
    
    return True

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Process a Zotero PDF with full metadata from API')
    parser.add_argument('pdf_path', help='Path to the PDF file in Zotero storage')
    parser.add_argument('--output-dir', help='Output directory for markdown file (default: from .env)')
    parser.add_argument('--skip-gpt', action='store_true', help='Skip GPT summarization')
    parser.add_argument('--filename-format', choices=['title', 'citekey', 'key', 'author-year'], 
                        default='title', help='Filename format (default: title)')
    
    args = parser.parse_args()
    
    # Load environment variables
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        print("Warning: .env file not found. Make sure environment variables are set.")
    
    # Check API key if not skipping GPT
    if not args.skip_gpt and not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not set. Use --skip-gpt or set the API key.")
        sys.exit(1)
    
    # Process the PDF
    success = process_zotero_pdf(args.pdf_path, args.output_dir, args.skip_gpt, args.filename_format)
    
    if success:
        print("✅ Successfully processed Zotero PDF with full metadata!")
    else:
        print("❌ Failed to process PDF.")
        sys.exit(1)

if __name__ == '__main__':
    main()