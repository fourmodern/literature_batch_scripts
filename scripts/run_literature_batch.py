"""
Main entrypoint for the batch literature processing pipeline.
"""
import os
import sys
import argparse
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dotenv import load_dotenv
from tqdm import tqdm
from zotero_fetch import fetch_zotero_items, list_all_collections
from text_extractor import extract_text_from_pdf, extract_text_and_images, extract_figures_and_tables

# Always enable image extraction regardless of summarizer
EXTRACT_IMAGES = True

# Load .env file early to get SUMMARIZER setting
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"Loaded environment from: {env_path}")
else:
    load_dotenv()  # Try default locations
    print("Warning: .env file not found in expected location, trying default paths")

# Import the appropriate summarizer based on environment
summarizer_type = os.getenv('SUMMARIZER', 'gpt').lower()
if summarizer_type == 'gemini':
    try:
        from gemini_summarizer import generate_short_long_with_images as generate_short_long
        from gemini_summarizer import generate_sections_with_images as generate_sections
        MULTIMODAL_SUPPORT = True
        print("Using Gemini API with multimodal support")
    except ImportError:
        print("⚠️ Gemini dependencies not available, falling back to GPT")
        from gpt_summarizer import generate_short_long, generate_sections, translate_captions
        MULTIMODAL_SUPPORT = False
else:
    from gpt_summarizer import generate_short_long, generate_sections, translate_captions
    MULTIMODAL_SUPPORT = False
    print("Using OpenAI GPT API (text-only)")
from markdown_writer import render_note, write_markdown
from utils import setup_logger, is_done, mark_done, save_checkpoint, load_checkpoint, clear_checkpoint
from zotero_path_finder import get_default_pdf_dir
from pdf_downloader import ensure_pdf_available, check_storage_permissions

# Global lock for thread-safe operations
progress_lock = Lock()
done_lock = Lock()

def validate_environment():
    """Check that all required environment variables are set."""
    base_required = ['ZOTERO_USER_ID', 'ZOTERO_API_KEY', 'OUTPUT_DIR']
    
    # Add API key requirement based on summarizer type
    summarizer_type = os.getenv('SUMMARIZER', 'gpt').lower()
    if summarizer_type == 'gemini':
        base_required.append('GEMINI_API_KEY')
    else:
        base_required.append('OPENAI_API_KEY')
    
    missing = []
    
    print("\nChecking environment variables:")
    for var in base_required:
        value = os.getenv(var)
        if not value:
            missing.append(var)
            print(f"  ❌ {var}: Not set")
        else:
            # Mask sensitive values
            if 'KEY' in var:
                masked = value[:10] + '...' if len(value) > 10 else value
                print(f"  ✅ {var}: {masked}")
            else:
                print(f"  ✅ {var}: {value}")
    
    if missing:
        print(f"\nError: Missing required environment variables: {', '.join(missing)}")
        print("Please copy .env.example to .env and fill in your credentials.")
        print("Current working directory:", os.getcwd())
        sys.exit(1)

def sanitize_folder_name(name):
    """Sanitize folder name for filesystem."""
    # Replace problematic characters
    name = name.replace('/', '-').replace('\\', '-').replace(':', '-')
    name = name.replace('*', '').replace('?', '').replace('"', '').replace('<', '').replace('>', '').replace('|', '')
    return name.strip()

def process_item(item, args, log, output_dir, pdf_base_dir, zot=None):
    """Process a single literature item."""
    key = item['key']
    title = item['title']
    
    # Get PDF path
    pdf_path = None
    if item['attachments']:
        attachment = item['attachments'][0]
        
        # Always try to ensure PDF is available (download if necessary)
        if zot and not args.no_pdf_download:
            pdf_path = ensure_pdf_available(zot, item, attachment, pdf_base_dir, download_enabled=True)
        else:
            # Fallback to local-only checking if no zot instance
            relative_path = attachment.get('path', '')
            if relative_path:
                # Handle Zotero storage structure: storage/ITEMKEY/filename.pdf
                if relative_path.startswith('storage/'):
                    pdf_path = os.path.join(pdf_base_dir, relative_path)
                else:
                    # For linked files or other paths
                    pdf_path = os.path.join(pdf_base_dir, 'storage', relative_path)
                
                # Check if file exists
                if not os.path.exists(pdf_path):
                    # Try alternative path without 'storage' prefix
                    alt_path = os.path.join(pdf_base_dir, attachment.get('fileKey', ''), attachment.get('filename', 'document.pdf'))
                    if os.path.exists(alt_path):
                        pdf_path = alt_path
                        log.info(f"Found PDF at alternative path: {alt_path}")
                    else:
                        log.warning(f"PDF not found locally and cannot download without Zotero connection")
                        pdf_path = None
    
    # Extract text and images from PDF or use abstract
    text = ''
    images = []
    captions = []
    featured_image = None
    pdf_success = False
    
    if pdf_path and os.path.exists(pdf_path):
        try:
            # Always extract images regardless of summarizer type
            if EXTRACT_IMAGES:
                # Create output directory for images under central img folder
                img_output_dir = os.path.join(output_dir, "img", sanitize_folder_name(title))
                text, images, captions, featured_image = extract_text_and_images(pdf_path, img_output_dir)
                log.info(f"✓ Extracted {len(images)} images and {len(captions)} captions")
                if featured_image:
                    log.info(f"✓ Featured image: {featured_image['filename']} ({featured_image['selection_reason']})")
                # Extract figures and tables
                figure_captions, table_captions = extract_figures_and_tables(pdf_path)
                log.info(f"✓ Found {len(figure_captions)} figures and {len(table_captions)} tables")
                
                # Translate captions if not skipping GPT
                if not args.skip_gpt:
                    try:
                        figure_captions = translate_captions(figure_captions, 'figure')
                        table_captions = translate_captions(table_captions, 'table')
                        log.info(f"✓ Translated figure and table captions to Korean")
                    except Exception as e:
                        log.warning(f"Failed to translate captions: {e}")
            else:
                text = extract_text_from_pdf(pdf_path)
                images = []
                captions = []
                featured_image = None
                figure_captions = []
                table_captions = []
            # Validate extracted text - lower threshold for academic papers
            if text and len(text.strip()) > 100:  # Lowered from 500 to 100 chars
                word_count = len(text.split())
                char_count = len(text.strip())
                
                # Additional validation: check if it's real text or garbage
                # Check for reasonable word length and ASCII ratio
                words = text.split()
                if words:
                    avg_word_length = sum(len(w) for w in words[:100]) / min(len(words), 100)
                    ascii_chars = sum(1 for c in text[:1000] if ord(c) < 128)
                    ascii_ratio = ascii_chars / min(len(text), 1000)
                    
                    # Academic papers validation - more lenient for scientific texts
                    # Allow longer words for chemical/gene names, require some ASCII but not too much
                    if 2 <= avg_word_length <= 30 and 0.5 <= ascii_ratio <= 1.0:
                        # Additional check: if text looks like actual sentences
                        has_spaces = ' ' in text[:500]
                        has_periods = '.' in text[:500]
                        if has_spaces and (has_periods or word_count > 100):
                            log.info(f"✓ Extracted {word_count} words ({char_count} chars) from PDF: {os.path.basename(pdf_path)}")
                            pdf_success = True
                        else:
                            log.warning(f"✗ PDF text seems corrupted (no sentence structure)")
                            text = ''
                    else:
                        log.warning(f"✗ PDF text validation failed (avg word len: {avg_word_length:.1f}, ASCII ratio: {ascii_ratio:.2f})")
                        text = ''
                else:
                    log.warning(f"✗ PDF text too short ({char_count} chars)")
                    text = ''
            else:
                log.warning(f"✗ PDF extraction produced only {len(text.strip())} chars")
                text = ''
        except Exception as e:
            log.error(f"✗ PDF extraction error: {e}")
    
    # Fallback to abstract if no PDF text
    if not text.strip() or not pdf_success:
        abstract = item.get('abstract', '')
        if abstract:
            text = f"[NOTE: PDF extraction failed, using abstract only]\n\n{abstract}"
            log.info(f"Using abstract for {key} (PDF extraction failed)")
        else:
            text = "[No text available - neither PDF nor abstract could be extracted]"
            log.warning(f"No text available for {key}")
        # Empty lists when no PDF available
        if not pdf_success:
            figure_captions = []
            table_captions = []
    
    # Check if we have keywords from Zotero
    zotero_tags = item.get('tags', [])
    
    # Generate summaries
    if args.skip_gpt:
        short_summary = "[GPT summarization skipped]"
        long_summary = "[GPT summarization skipped]"
        contributions = ""
        limitations = ""
        ideas = ""
        # Use Zotero tags if available
        keywords = zotero_tags if zotero_tags else []
        log.info(f"Skipping GPT summarization for {key}")
    elif text:
        # Generate summaries with appropriate method
        if MULTIMODAL_SUPPORT and images:
            short_summary, long_summary = generate_short_long(text, images, captions, title)
            log.info(f"Generated multimodal summary with {len(images)} images for {key}")
        else:
            log.info(f"Generating GPT summaries for {key} (this may take a few minutes with GPT-5)...")
            short_summary, long_summary = generate_short_long(text, title)
            log.info(f"✓ Generated summaries for {key}")
        
        # Only generate keywords with AI if we don't have Zotero tags
        if zotero_tags:
            if MULTIMODAL_SUPPORT and images:
                contributions, limitations, ideas = generate_sections(text, images, captions, title)[:3]
            else:
                contributions, limitations, ideas = generate_sections(text, title)[:3]  # Get only first 3 returns
            keywords = zotero_tags
            log.info(f"Using {len(keywords)} keywords from Zotero for {key}")
        else:
            if MULTIMODAL_SUPPORT and images:
                contributions, limitations, ideas, keywords_raw = generate_sections(text, images, captions, title)
            else:
                contributions, limitations, ideas, keywords_raw = generate_sections(text, title)
            # Parse keywords from the raw response
            # Debug log for problematic paper
            if "Human interpretable" in title:
                log.info(f"DEBUG: Raw keywords for problematic paper: {repr(keywords_raw)}")
            # Check if keywords_raw is a string that needs parsing
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
            log.info(f"Generated {len(keywords)} keywords with AI for {key}")
    else:
        short_summary = "No text available for summarization."
        long_summary = "No text available for summarization."
        contributions = ""
        limitations = ""
        ideas = ""
        keywords = zotero_tags if zotero_tags else []
    
    # Prepare context for template
    # Add Zotero links
    zotero_user_id = os.getenv('ZOTERO_USER_ID')
    zotero_web_link = f"https://www.zotero.org/users/{zotero_user_id}/items/{key}"
    # Use the correct Zotero desktop link format with item key
    zotero_app_link = f"zotero://select/items/0_{key}"
    
    # Add extraction status to summary if PDF failed
    if not pdf_success and "[NOTE: PDF extraction failed" in text:
        short_summary = f"⚠️ PDF 추출 실패 - 초록만 사용\n\n{short_summary}"
    
    context = {
        **item,
        'pdf_path': pdf_path or '',
        'zotero_link': zotero_web_link,
        'zotero_app_link': zotero_app_link,
        'short_summary': short_summary,
        'long_summary': long_summary,
        'contribution': contributions,
        'limitations': limitations,
        'ideas': ideas,
        'keywords': keywords,
        'bibliography': f"{', '.join(item['authors'][:3])}{'...' if len(item['authors']) > 3 else ''}. ({item['year']}). {title}. {item['publicationTitle']}.",
        'pdf_extraction_success': pdf_success,
        'extracted_images': images,
        'image_captions': captions,
        'featured_image': featured_image,
        'figure_captions': figure_captions if 'figure_captions' in locals() else [],
        'table_captions': table_captions if 'table_captions' in locals() else []
    }
    
    # Convert absolute paths to relative paths for Obsidian
    # MD file will be in: output_dir/collection_path/filename.md
    # Images are in: output_dir/paper_title/images/
    collection_path = item.get('collection_path', 'Uncategorized')
    
    # Calculate relative path from MD file location to image location
    # We need to go up from collection folders and then into the paper folder
    collection_depth = len(collection_path.split('/'))
    relative_prefix = '../' * collection_depth  # Go up to vault root
    
    # Update image paths to be relative to new img folder structure
    if featured_image:
        paper_folder = sanitize_folder_name(title)
        featured_image['relative_path'] = f"{relative_prefix}img/{paper_folder}/{featured_image['filename']}"
        log.info(f"Featured image will be included: {featured_image['filename']}")
    else:
        log.info("No featured image to include")
    
    if images:
        paper_folder = sanitize_folder_name(title)
        for img in images:
            img['relative_path'] = f"{relative_prefix}img/{paper_folder}/{img['filename']}"
    
    # Render markdown
    try:
        md_content = render_note('literature_note.md', context)
    except Exception as e:
        log.error(f"Failed to render template for {key}: {e}")
        return False
    
    # Create folder structure based on collection
    collection_path = item.get('collection_path', 'Uncategorized')
    collection_parts = collection_path.split(os.sep)
    sanitized_parts = [sanitize_folder_name(part) for part in collection_parts]
    folder_path = os.path.join(output_dir, *sanitized_parts)
    
    # Write file
    safe_filename = "".join(c for c in title if c.isalnum() or c in ' -_')[:100]
    file_path = os.path.join(folder_path, f"{safe_filename}_{key}.md")
    
    # Handle PDF path based on --copy-pdfs option
    if args.copy_pdfs and pdf_path and os.path.exists(pdf_path) and not args.dry_run:
        # Copy PDF to Obsidian vault
        pdf_folder = os.path.join(folder_path, "PDFs")
        os.makedirs(pdf_folder, exist_ok=True)
        
        # Copy PDF with sanitized filename
        pdf_filename = f"{safe_filename}_{key}.pdf"
        pdf_vault_path = os.path.join(pdf_folder, pdf_filename)
        
        try:
            shutil.copy2(pdf_path, pdf_vault_path)
            log.info(f"Copied PDF to {pdf_vault_path}")
            
            # Update context with relative path for Obsidian
            rel_pdf_path = os.path.relpath(pdf_vault_path, folder_path)
            context['pdf_path'] = rel_pdf_path
            
            # Re-render with updated PDF path
            md_content = render_note('literature_note.md', context)
        except Exception as e:
            log.warning(f"Failed to copy PDF: {e}")
            # Keep original pdf_path if copy fails
    elif args.copy_pdfs and args.dry_run and pdf_path:
        log.info(f"[DRY RUN] Would copy PDF to {folder_path}/PDFs/{safe_filename}_{key}.pdf")
    else:
        # Default: Keep original Zotero path (file:// link)
        if pdf_path:
            context['pdf_path'] = f"file://{pdf_path}"
            # Re-render with file:// path
            md_content = render_note('literature_note.md', context)
    
    if not args.dry_run:
        try:
            write_markdown(md_content, file_path)
            with done_lock:
                mark_done(key)
            log.info(f"Successfully processed {key}: {title}")
        except Exception as e:
            log.error(f"Failed to write {file_path}: {e}")
            return False
    else:
        log.info(f"[DRY RUN] Would write to {file_path}")
    
    return True

def main():
    # Environment already loaded at module level
    validate_environment()
    
    parser = argparse.ArgumentParser(description='Batch process Zotero literature.')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of items to process')
    parser.add_argument('--dry-run', action='store_true', help='Run without writing files')
    parser.add_argument('--overwrite', action='store_true', help='Process items even if already done')
    parser.add_argument('--resume', action='store_true', help='Resume from last processed item')
    parser.add_argument('--collection', type=str, default=None, help='Process only items from specific collection (by name)')
    parser.add_argument('--list-collections', action='store_true', help='List all available collections and exit')
    parser.add_argument('--skip-gpt', action='store_true', help='Skip GPT summarization (only extract metadata)')
    parser.add_argument('--copy-pdfs', action='store_true', help='Copy PDFs to vault (default: use Zotero links)')
    parser.add_argument('--no-pdf-download', action='store_true', help='Skip automatic PDF downloads (use local files only)')
    parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers for processing (default: 5)')
    args = parser.parse_args()
    
    # Setup directories and logging
    output_dir = os.getenv('OUTPUT_DIR')
    pdf_base_dir = get_default_pdf_dir()
    
    # Show detected PDF directory
    env_pdf_dir = os.getenv('PDF_DIR')
    if env_pdf_dir:
        if os.path.exists(env_pdf_dir):
            print(f"Using PDF directory from environment: {env_pdf_dir}")
            pdf_base_dir = env_pdf_dir
        else:
            print(f"Warning: PDF_DIR '{env_pdf_dir}' does not exist")
            print(f"Using auto-detected directory: {pdf_base_dir}")
    else:
        print(f"Auto-detected Zotero directory: {pdf_base_dir}")
    
    # Verify the storage subdirectory exists
    storage_dir = os.path.join(pdf_base_dir, 'storage')
    if os.path.exists(storage_dir):
        print(f"Zotero storage found: {storage_dir}")
    else:
        print(f"Warning: Zotero storage directory not found at {storage_dir}")
        print("PDF extraction may fail. Please set PDF_DIR environment variable.")
    
    # Check storage permissions for automatic PDF downloads
    has_permission, error_msg = check_storage_permissions(pdf_base_dir)
    if not has_permission:
        print(f"Warning: {error_msg}")
        print("Automatic PDF download may fail due to permission issues.")
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    log = setup_logger('batch', './logs/summary.log')
    log.info(f"Starting batch processing with args: {vars(args)}")
    
    # Handle --list-collections
    if args.list_collections:
        print("\nAvailable Zotero Collections:")
        print("=" * 60)
        collections = list_all_collections(
            os.getenv('ZOTERO_USER_ID'), 
            os.getenv('ZOTERO_API_KEY')
        )
        if not collections:
            print("No collections found.")
        else:
            for path, count in collections:
                indent = "  " * path.count(os.sep)
                name = os.path.basename(path) or path
                print(f"{indent}{name} ({count} papers)")
        print(f"\nTotal: {len(collections)} collections")
        return
    
    # Fetch items from Zotero
    if args.collection:
        print(f"Fetching items from collection '{args.collection}'...")
    else:
        print("Fetching all items from Zotero...")
    
    # Always get Zotero instance for automatic PDF downloads
    items, zot = fetch_zotero_items(
        os.getenv('ZOTERO_USER_ID'), 
        os.getenv('ZOTERO_API_KEY'), 
        limit=args.limit,
        collection_filter=args.collection,
        return_zot_instance=True
    )
    
    if not items:
        print("No items found to process.")
        return
    
    print(f"Found {len(items)} items to process.")
    
    # Handle resume functionality
    start_index = 0
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            print(f"\nResuming from checkpoint (saved {checkpoint['timestamp']})")
            print(f"Previous progress: {checkpoint['processed']} papers processed")
            
            # Verify we're processing the same collection
            if checkpoint.get('collection') != args.collection:
                print(f"Warning: Checkpoint was for collection '{checkpoint.get('collection')}', but current collection is '{args.collection}'")
                response = input("Continue anyway? (y/n): ")
                if response.lower() != 'y':
                    return
            
            # Find where to start
            checkpoint_keys = checkpoint.get('processed_keys', [])
            if checkpoint_keys:
                for i, item in enumerate(items):
                    if item['key'] not in checkpoint_keys:
                        start_index = i
                        break
                print(f"Skipping first {start_index} items (already processed)")
        else:
            print("No checkpoint found, starting from beginning")
    
    # Filter already processed items
    if not args.overwrite and not args.resume:
        items = [item for item in items if not is_done(item['key'])]
        print(f"{len(items)} items remaining after filtering already processed.")
    elif args.resume and start_index > 0:
        items = items[start_index:]
        print(f"{len(items)} items remaining to process.")
    
    if not items:
        print("\n✅ All items have been processed.")
        print("\nOptions:")
        print("  • Use --overwrite to reprocess all papers")
        print("  • Use --limit N to process only N papers") 
        print("  • Add new papers to Zotero and run again")
        clear_checkpoint()  # Clear checkpoint if all done
        return
    
    # Process items with progress bar
    success_count = 0
    error_count = 0
    processed_keys = []
    
    # Load existing processed keys if resuming
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            processed_keys = checkpoint.get('processed_keys', [])
            success_count = checkpoint.get('success_count', 0)
            error_count = checkpoint.get('error_count', 0)
    
    print(f"\n🚀 Processing with {args.workers} parallel workers...")
    
    try:
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            # Submit all tasks
            future_to_item = {}
            for item in items:
                future = executor.submit(process_item, item, args, log, output_dir, pdf_base_dir, zot)
                future_to_item[future] = item
            
            # Process completed tasks with progress bar
            with tqdm(total=len(items), desc="Processing papers", unit="paper") as pbar:
                for future in as_completed(future_to_item):
                    item = future_to_item[future]
                    
                    try:
                        result = future.result()
                        
                        with progress_lock:
                            if result:
                                success_count += 1
                                processed_keys.append(item['key'])
                            else:
                                error_count += 1
                            
                            pbar.update(1)
                            pbar.set_postfix({
                                'success': success_count,
                                'errors': error_count,
                                'current': item['title'][:30] + '...'
                            })
                            
                            # Save checkpoint every 10 papers or on error
                            if (success_count + error_count) % 10 == 0 or error_count > 0:
                                save_checkpoint({
                                    'collection': args.collection,
                                    'processed': success_count + error_count,
                                    'success_count': success_count,
                                    'error_count': error_count,
                                    'processed_keys': processed_keys,
                                    'total_items': len(items) + (start_index if args.resume else 0)
                                })
                                
                    except KeyboardInterrupt:
                        print("\n\nInterrupted by user. Cancelling remaining tasks...")
                        executor.shutdown(wait=False)
                        
                        with progress_lock:
                            save_checkpoint({
                                'collection': args.collection,
                                'processed': success_count + error_count,
                                'success_count': success_count,
                                'error_count': error_count,
                                'processed_keys': processed_keys,
                                'total_items': len(items) + (start_index if args.resume else 0)
                            })
                        print(f"Checkpoint saved. Use --resume to continue from this point.")
                        print(f"Progress: {success_count + error_count} papers processed")
                        return
                        
                    except Exception as e:
                        log.error(f"Unexpected error processing {item['key']}: {e}")
                        with progress_lock:
                            error_count += 1
                    
        # Clear checkpoint on successful completion
        clear_checkpoint()
        
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        save_checkpoint({
            'collection': args.collection,
            'processed': success_count + error_count,
            'success_count': success_count,
            'error_count': error_count,
            'processed_keys': processed_keys,
            'total_items': len(items) + (start_index if args.resume else 0)
        })
        print(f"Checkpoint saved. Use --resume to continue.")
        raise
    
    # Summary
    print(f"\nProcessing complete!")
    print(f"Successfully processed: {success_count} papers")
    print(f"Errors: {error_count} papers")
    print(f"Output directory: {output_dir}")
    print(f"Log file: ./logs/summary.log")

if __name__ == '__main__':
    main()