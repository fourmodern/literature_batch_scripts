"""
Process a single PDF paper and create an Obsidian markdown note.
"""
import os
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from text_extractor import extract_text_from_pdf, extract_text_and_images
from gpt_summarizer import generate_short_long, generate_sections
from markdown_writer import render_note, write_markdown
from utils import setup_logger

def extract_metadata_from_pdf(pdf_path, text):
    """Extract metadata from PDF text content."""
    metadata = {
        'title': 'Unknown Title',
        'authors': [],
        'year': datetime.now().year,
        'abstract': '',
        'doi': '',
        'journal': '',
        'keywords': []
    }
    
    # Try to extract title from first few lines
    lines = text.split('\n')[:50]  # First 50 lines
    for i, line in enumerate(lines):
        line = line.strip()
        if len(line) > 20 and len(line) < 200:  # Reasonable title length
            # Check if it looks like a title (not all caps, not a number)
            if not line.isupper() and not line.replace('.', '').isdigit():
                metadata['title'] = line
                break
    
    # Extract DOI
    doi_pattern = r'10\.\d{4,}/[-._;()/:\w]+'
    doi_match = re.search(doi_pattern, text[:5000])  # Search in first 5000 chars
    if doi_match:
        metadata['doi'] = doi_match.group()
    
    # Extract year
    year_pattern = r'\b(19|20)\d{2}\b'
    year_matches = re.findall(year_pattern, text[:5000])
    if year_matches:
        # Get the most recent year that's not in the future
        current_year = datetime.now().year
        valid_years = [int(y) for y in year_matches if int(y) <= current_year]
        if valid_years:
            metadata['year'] = max(valid_years)
    
    # Extract abstract
    abstract_start = text.lower().find('abstract')
    if abstract_start != -1:
        abstract_text = text[abstract_start:abstract_start+2000]
        # Clean up abstract
        abstract_lines = abstract_text.split('\n')[1:20]  # Skip "Abstract" line
        abstract = ' '.join(line.strip() for line in abstract_lines if line.strip())
        # Stop at introduction or keywords
        for stop_word in ['introduction', 'keywords', '1.', 'I.']:
            stop_pos = abstract.lower().find(stop_word.lower())
            if stop_pos > 100:  # Make sure we have some content
                abstract = abstract[:stop_pos]
                break
        metadata['abstract'] = abstract.strip()
    
    return metadata

def sanitize_filename(filename):
    """Sanitize filename for filesystem."""
    # Remove or replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename

def process_single_pdf(pdf_path, output_dir=None, skip_gpt=False):
    """Process a single PDF file."""
    # Setup
    log = setup_logger("single_pdf", "logs/single_pdf.log")
    
    # Validate PDF exists
    if not os.path.exists(pdf_path):
        log.error(f"PDF file not found: {pdf_path}")
        return False
    
    # Set default output directory
    if not output_dir:
        output_dir = os.getenv('OUTPUT_DIR', './ObsidianVault/LiteratureNotes/')
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    log.info(f"Processing PDF: {pdf_path}")
    
    # Extract text and images
    img_output_dir = os.path.join(output_dir, Path(pdf_path).stem, "images")
    text, images, captions, featured_image = extract_text_and_images(pdf_path, img_output_dir)
    
    if not text or len(text.strip()) < 100:
        log.error(f"Failed to extract sufficient text from PDF (only {len(text)} chars)")
        return False
    
    log.info(f"Extracted {len(text)} characters and {len(images)} images from PDF")
    if featured_image:
        log.info(f"Featured image: {featured_image['filename']} ({featured_image['selection_reason']})")
    
    # Extract metadata
    metadata = extract_metadata_from_pdf(pdf_path, text)
    log.info(f"Extracted metadata - Title: {metadata['title'][:50]}...")
    
    # Generate summaries if not skipping GPT
    if not skip_gpt:
        try:
            # Truncate text if too long
            if len(text) > 30000:
                log.warning(f"Text too long ({len(text)} chars), truncating to 30000")
                text = text[:30000]
            
            # Generate summaries
            title = metadata.get('title', 'Unknown')
            short_summary, long_summary = generate_short_long(text, title)
            contribution, limitations, ideas, keywords = generate_sections(text, title)
            
            metadata['short_summary'] = short_summary
            metadata['long_summary'] = long_summary
            metadata['contribution'] = contribution
            metadata['limitations'] = limitations
            metadata['ideas'] = ideas
            metadata['keywords'] = keywords
            
            log.info("Generated GPT summaries successfully")
        except Exception as e:
            log.error(f"Failed to generate GPT summaries: {e}")
            if not skip_gpt:
                return False
    else:
        metadata['short_summary'] = "GPT 요약을 건너뛰었습니다."
        metadata['long_summary'] = "GPT 요약을 건너뛰었습니다."
        metadata['contribution'] = ""
        metadata['limitations'] = ""
        metadata['ideas'] = ""
    
    # Prepare item data for template
    item = {
        'key': Path(pdf_path).stem,
        'title': metadata['title'],
        'authors': metadata['authors'],
        'year': metadata['year'],
        'abstract': metadata['abstract'],
        'doi': metadata['doi'],
        'publicationTitle': metadata['journal'],
        'keywords': metadata['keywords'],
        'date': datetime.now().strftime('%Y-%m-%d'),
        'itemType': 'journalArticle',
        'pdf_path': f"file://{os.path.abspath(pdf_path)}",
        'collections': ['Single PDF Import'],
        'zotero_link': '',
        'zotero_app_link': '',
        'short_summary': metadata.get('short_summary', ''),
        'long_summary': metadata.get('long_summary', ''),
        'contribution': metadata.get('contribution', ''),
        'limitations': metadata.get('limitations', ''),
        'ideas': metadata.get('ideas', ''),
        'extracted_images': images,
        'image_captions': captions,
        'featured_image': featured_image
    }
    
    # Render markdown
    content = render_note('literature_note.md', item)
    
    # Write to file
    safe_filename = sanitize_filename(metadata['title'])
    output_path = os.path.join(output_dir, f"{safe_filename}.md")
    
    # Handle duplicates
    if os.path.exists(output_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(output_dir, f"{safe_filename}_{timestamp}.md")
    
    write_markdown(content, output_path)
    log.info(f"✅ Created markdown note: {output_path}")
    
    return True

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Process a single PDF paper into Obsidian markdown')
    parser.add_argument('pdf_path', help='Path to the PDF file to process')
    parser.add_argument('--output-dir', help='Output directory for markdown file (default: from .env)')
    parser.add_argument('--skip-gpt', action='store_true', help='Skip GPT summarization')
    
    args = parser.parse_args()
    
    # Load environment
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        print("Warning: .env file not found. Make sure OPENAI_API_KEY is set.")
    
    # Check API key if not skipping GPT
    if not args.skip_gpt and not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not set. Use --skip-gpt or set the API key.")
        sys.exit(1)
    
    # Process the PDF
    success = process_single_pdf(args.pdf_path, args.output_dir, args.skip_gpt)
    
    if success:
        print("✅ Successfully processed PDF!")
    else:
        print("❌ Failed to process PDF.")
        sys.exit(1)

if __name__ == '__main__':
    main()