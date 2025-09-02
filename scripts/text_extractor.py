"""
Extract text content from PDF files using the best available method.
"""
import os
import base64
from typing import Optional, List, Dict, Tuple

# Try to import the best PDF extraction libraries
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

import fitz  # PyMuPDF

def extract_text_from_pdf(pdf_path: str, max_pages: int = None) -> str:
    """
    Extract text from PDF using the best available method.
    Prioritizes pdfplumber for better table and layout handling.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    file_size = os.path.getsize(pdf_path)
    if file_size == 0:
        raise ValueError(f"PDF file is empty: {pdf_path}")
    
    print(f"Extracting from PDF: {os.path.basename(pdf_path)} ({file_size:,} bytes)")
    
    # First try pdfplumber - best for academic papers with tables
    if PDFPLUMBER_AVAILABLE:
        try:
            result = _extract_with_pdfplumber(pdf_path, max_pages)
            print(f"✓ Extracted {len(result)} chars with pdfplumber")
            return result
        except Exception as e:
            print(f"✗ pdfplumber failed: {e}")
    
    # Fallback to PyMuPDF with enhanced extraction
    try:
        result = _extract_with_pymupdf_enhanced(pdf_path, max_pages)
        print(f"✓ Extracted {len(result)} chars with PyMuPDF (enhanced)")
        return result
    except Exception as e:
        print(f"✗ Enhanced PyMuPDF failed: {e}")
        try:
            result = _extract_with_pymupdf_simple(pdf_path, max_pages)
            print(f"✓ Extracted {len(result)} chars with PyMuPDF (simple)")
            return result
        except Exception as e2:
            print(f"✗ All extraction methods failed: {e2}")
            raise

def _extract_with_pdfplumber(pdf_path: str, max_pages: int = None) -> str:
    """Extract text using pdfplumber with table support."""
    result_parts = []
    empty_pages = 0
    
    with pdfplumber.open(pdf_path) as pdf:
        pages_to_process = min(len(pdf.pages), max_pages) if max_pages else len(pdf.pages)
        print(f"  Processing {pages_to_process} pages with pdfplumber...")
        
        for i in range(pages_to_process):
            page = pdf.pages[i]
            
            # Extract text with error handling
            try:
                text = page.extract_text()
                if text and len(text.strip()) > 10:
                    result_parts.append(f"\n--- Page {i+1} ---\n")
                    result_parts.append(text)
                else:
                    empty_pages += 1
                    if empty_pages <= 3:  # Only warn for first few empty pages
                        print(f"  ⚠️ Page {i+1} appears empty")
            except Exception as e:
                print(f"  ✗ Error extracting page {i+1}: {e}")
            
            # Extract tables
            try:
                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    if table and len(table) > 1:
                        result_parts.append(f"\n[Table {j+1} on page {i+1}]")
                        # Use markdown format for better structure
                        markdown_table = _format_table_as_markdown(table)
                        if markdown_table:
                            result_parts.append(markdown_table)
                        else:
                            result_parts.append(_format_table_as_text(table))
            except:
                pass  # Tables are optional
    
    if not result_parts or all(not part.strip() for part in result_parts):
        raise ValueError(f"No text extracted from {pages_to_process} pages")
    
    return '\n'.join(result_parts)

def _extract_with_pymupdf_enhanced(pdf_path: str, max_pages: int = None) -> str:
    """Extract text using PyMuPDF with layout detection."""
    doc = fitz.open(pdf_path)
    pages = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    
    result_parts = [f"Document: {os.path.basename(pdf_path)}"]
    result_parts.append(f"Pages: {doc.page_count}\n")
    
    for i in range(pages):
        page = doc.load_page(i)
        result_parts.append(f"\n--- Page {i+1} ---\n")
        
        # Get text with layout preservation
        blocks = page.get_text("dict")
        page_text = []
        
        # Sort blocks by position
        sorted_blocks = sorted(blocks["blocks"], key=lambda b: (b["bbox"][1], b["bbox"][0]))
        
        for block in sorted_blocks:
            if block["type"] == 0:  # Text block
                block_text = ""
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    if line_text.strip():
                        block_text += line_text + " "
                if block_text.strip():
                    page_text.append(block_text.strip())
        
        result_parts.append('\n'.join(page_text))
    
    doc.close()
    return '\n'.join(result_parts)

def _extract_with_pymupdf_simple(pdf_path: str, max_pages: int = None) -> str:
    """Simple text extraction using PyMuPDF."""
    doc = fitz.open(pdf_path)
    pages = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    
    text_parts = []
    empty_pages = 0
    
    for i in range(pages):
        page = doc.load_page(i)
        
        # Try multiple extraction methods
        # Method 1: Standard text extraction
        text = page.get_text()
        
        # Method 2: If standard fails, try with different flags
        if not text.strip() or len(text.strip()) < 50:
            text = page.get_text("text", flags=11)  # More aggressive extraction
        
        # Method 3: Try extracting as blocks
        if not text.strip() or len(text.strip()) < 50:
            text_blocks = page.get_text("blocks")
            text = '\n'.join([block[4] for block in text_blocks if block[6] == 0])
        
        if text.strip():
            text_parts.append(f"--- Page {i+1} ---\n{text}")
        else:
            empty_pages += 1
            if empty_pages > 5:  # Too many empty pages, might be scanned PDF
                print(f"Warning: Many empty pages detected, PDF might be scanned/image-based")
    
    doc.close()
    
    result = '\n'.join(text_parts)
    if not result.strip():
        raise ValueError("No text could be extracted - PDF might be scanned or image-based")
    
    return result

def _format_table_as_text(table: list) -> str:
    """Format table data as readable text."""
    if not table:
        return ""
    
    lines = []
    for row in table:
        # Clean None values and join with tabs
        cleaned_row = [str(cell).strip() if cell else "" for cell in row]
        if any(cleaned_row):  # Skip empty rows
            lines.append("\t".join(cleaned_row))
    
    return "\n".join(lines)

def _format_table_as_markdown(table: list) -> str:
    """Format table data as markdown table."""
    if not table or len(table) < 1:
        return ""
    
    lines = []
    
    # Process header row
    header_row = [str(cell).strip() if cell else "" for cell in table[0]]
    if not any(header_row):
        return ""
    
    lines.append("| " + " | ".join(header_row) + " |")
    lines.append("| " + " | ".join("---" for _ in header_row) + " |")
    
    # Process data rows
    for row in table[1:]:
        cleaned_row = [str(cell).strip() if cell else "" for cell in row]
        if any(cleaned_row):  # Skip empty rows
            # Pad row to match header length
            while len(cleaned_row) < len(header_row):
                cleaned_row.append("")
            lines.append("| " + " | ".join(cleaned_row[:len(header_row)]) + " |")
    
    return "\n".join(lines)

def extract_images_from_pdf(pdf_path: str, output_dir: str = None) -> List[Dict]:
    """
    Extract images from PDF and save them as PNG files.
    Returns list of image metadata with paths.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(pdf_path), "extracted_images")
    
    os.makedirs(output_dir, exist_ok=True)
    
    images = []
    doc = fitz.open(pdf_path)
    
    print(f"Extracting images from {len(doc)} pages...")
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            try:
                # Get image data
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                
                # Skip very small images (likely artifacts)
                if pix.width < 50 or pix.height < 50:
                    pix = None
                    continue
                
                # Convert CMYK to RGB if needed
                if pix.n - pix.alpha < 4:  # GRAY or RGB
                    img_data = pix.tobytes("png")
                else:  # CMYK
                    pix1 = fitz.Pixmap(fitz.csRGB, pix)
                    img_data = pix1.tobytes("png")
                    pix1 = None
                
                # Save image
                img_filename = f"page{page_num+1}_img{img_index+1}.png"
                img_path = os.path.join(output_dir, img_filename)
                
                with open(img_path, "wb") as f:
                    f.write(img_data)
                
                # Store metadata
                images.append({
                    'path': img_path,
                    'filename': img_filename,
                    'page': page_num + 1,
                    'index': img_index + 1,
                    'width': pix.width,
                    'height': pix.height,
                    'size_bytes': len(img_data)
                })
                
                print(f"  ✓ Extracted image: {img_filename} ({pix.width}x{pix.height})")
                pix = None
                
            except Exception as e:
                print(f"  ✗ Failed to extract image {img_index} from page {page_num+1}: {e}")
                continue
    
    doc.close()
    print(f"Extracted {len(images)} images to {output_dir}")
    return images

def extract_image_captions(pdf_path: str) -> List[Dict]:
    """
    Extract text that looks like image captions (Figure X, 그림 X, etc.)
    """
    captions = []
    doc = fitz.open(pdf_path)
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        blocks = page.get_text("dict")
        
        for block in blocks["blocks"]:
            if block["type"] == 0:  # Text block
                text = ""
                for line in block["lines"]:
                    for span in line["spans"]:
                        text += span["text"] + " "
                
                text = text.strip()
                # Look for figure/table captions with priority scoring
                caption_keywords = {
                    'graphical abstract': 100,  # Highest priority
                    'fig. 1': 90, 'figure 1': 90, 'fig 1': 90,
                    'fig. 2': 80, 'figure 2': 80, 'fig 2': 80,
                    'fig. 3': 70, 'figure 3': 70, 'fig 3': 70,
                    'figure ': 50, 'fig ': 50, 'fig.': 50,
                    '그림 1': 90, '그림 2': 80, '그림 3': 70, '그림 ': 50,
                    'table 1': 85, 'table ': 40, '표 1': 85, '표 ': 40,
                    'chart ': 30, 'graph ': 30
                }
                
                text_lower = text.lower()
                priority = 0
                for keyword, score in caption_keywords.items():
                    if keyword in text_lower:
                        priority = max(priority, score)
                
                if priority > 0:
                    captions.append({
                        'page': page_num + 1,
                        'text': text,
                        'bbox': block["bbox"],
                        'priority': priority
                    })
    
    doc.close()
    # Sort by priority (highest first)
    captions.sort(key=lambda x: x['priority'], reverse=True)
    return captions

def extract_figures_and_tables(pdf_path: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract and parse figure and table captions separately with titles.
    Returns (figure_captions, table_captions)
    """
    import re
    
    figures = []
    tables = []
    doc = fitz.open(pdf_path)
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text()
        lines = text.split('\n')
        
        # Process lines to find captions
        for i, line in enumerate(lines):
            # Check for Figure captions
            fig_match = re.match(r'^(Figure|Fig\.?)\s+(\d+|[A-Z]\d*)[:\.]?\s*(.*)', line, re.IGNORECASE)
            if fig_match:
                number = fig_match.group(2)
                # Get title - may span multiple lines
                title_parts = [fig_match.group(3)]
                
                # Check next few lines for continuation
                for j in range(1, min(4, len(lines) - i)):
                    next_line = lines[i + j].strip()
                    # Stop if we hit another figure/table or empty line
                    if not next_line or re.match(r'^(Figure|Fig|Table)\s+\d', next_line, re.IGNORECASE):
                        break
                    # Stop at common section markers
                    if next_line[0].isupper() and len(next_line.split()) < 3:
                        break
                    title_parts.append(next_line)
                
                title = ' '.join(title_parts).strip()
                # Clean up title - remove trailing periods, etc.
                title = re.sub(r'\.$', '', title)
                
                figures.append({
                    'number': number,
                    'title': title if title else f"Figure {number}",
                    'page': page_num + 1
                })
            
            # Check for Table captions
            table_match = re.match(r'^Table\s+(\d+|[A-Z]\d*)[:\.]?\s*(.*)', line, re.IGNORECASE)
            if table_match:
                number = table_match.group(1)
                # Get title - may span multiple lines
                title_parts = [table_match.group(2)]
                
                # Check next few lines for continuation
                for j in range(1, min(4, len(lines) - i)):
                    next_line = lines[i + j].strip()
                    # Stop if we hit another figure/table or empty line
                    if not next_line or re.match(r'^(Figure|Fig|Table)\s+\d', next_line, re.IGNORECASE):
                        break
                    # Stop at common section markers
                    if next_line[0].isupper() and len(next_line.split()) < 3:
                        break
                    title_parts.append(next_line)
                
                title = ' '.join(title_parts).strip()
                # Clean up title
                title = re.sub(r'\.$', '', title)
                
                tables.append({
                    'number': number,
                    'title': title if title else f"Table {number}",
                    'page': page_num + 1
                })
    
    doc.close()
    
    # Remove duplicates and sort by number
    seen_figs = set()
    unique_figures = []
    for fig in figures:
        key = (fig['number'], fig['title'][:50])  # Use first 50 chars to identify
        if key not in seen_figs:
            seen_figs.add(key)
            unique_figures.append(fig)
    
    seen_tables = set()
    unique_tables = []
    for table in tables:
        key = (table['number'], table['title'][:50])
        if key not in seen_tables:
            seen_tables.add(key)
            unique_tables.append(table)
    
    # Sort by number (handle both numeric and alphanumeric)
    def sort_key(item):
        num = item['number']
        if num.isdigit():
            return (0, int(num))
        else:
            # Handle cases like 'S1', 'A1', etc.
            return (1, num)
    
    unique_figures.sort(key=sort_key)
    unique_tables.sort(key=sort_key)
    
    return unique_figures, unique_tables

def identify_key_figures(images: List[Dict], captions: List[Dict]) -> List[Dict]:
    """
    Identify the most important figures based on various criteria.
    Returns images with priority scores.
    """
    if not images:
        return []
    
    # Create a copy of images with priority scores
    prioritized_images = []
    for img in images:
        img_copy = img.copy()
        priority = 0
        
        # Base priority by page (earlier pages are more important)
        page_priority = max(0, 100 - (img['page'] - 1) * 5)  # Decreases by 5 per page
        priority += page_priority
        
        # Size-based priority (larger images are more important)
        img_area = img['width'] * img['height']
        if img_area > 500000:  # Large images
            priority += 50
        elif img_area > 200000:  # Medium images
            priority += 30
        elif img_area > 100000:  # Small-medium images
            priority += 15
        
        # Match with captions for additional priority
        for caption in captions:
            if abs(caption['page'] - img['page']) <= 1:  # Same page or adjacent
                priority += caption['priority'] // 2  # Half of caption priority
                
                # Check if caption text suggests importance
                caption_text = caption['text'].lower()
                if 'graphical abstract' in caption_text:
                    priority += 300  # Highest priority for graphical abstract
                elif any(keyword in caption_text for keyword in ['schema', 'scheme', 'schematic diagram']):
                    priority += 250  # Very high priority for schema/schematic
                elif any(keyword in caption_text for keyword in ['fig. 1', 'figure 1', 'fig 1', '그림 1']):
                    priority += 100  # High boost for Figure 1
                elif any(keyword in caption_text for keyword in ['overview', 'workflow', 'schematic', 'summary', 'framework', 'architecture']):
                    priority += 80  # Boost for overview figures
                elif any(keyword in caption_text for keyword in ['model', 'pipeline', 'mechanism', 'pathway']):
                    priority += 60  # Boost for explanatory figures
        
        # Position-based priority (images near top of page are more important)
        # This would require bbox information from image extraction
        
        img_copy['priority'] = priority
        prioritized_images.append(img_copy)
    
    # Sort by priority (highest first)
    prioritized_images.sort(key=lambda x: x['priority'], reverse=True)
    return prioritized_images

def select_featured_image(images: List[Dict], captions: List[Dict]) -> Optional[Dict]:
    """
    Select the single most important image to feature prominently.
    """
    prioritized_images = identify_key_figures(images, captions)
    
    if not prioritized_images:
        return None
    
    # Return the highest priority image
    featured = prioritized_images[0]
    
    # Add reason for selection
    reasons = []
    if featured['priority'] >= 300:
        reasons.append("Graphical Abstract")
    elif featured['priority'] >= 250:
        reasons.append("Schema/Schematic")
    elif featured['priority'] >= 150:
        reasons.append("Figure 1")
    elif featured['priority'] >= 100:
        reasons.append("Early key figure")
    elif featured['priority'] >= 80:
        reasons.append("Overview figure")
    elif featured['priority'] >= 60:
        reasons.append("Explanatory figure")
    else:
        reasons.append("Best available")
    
    if featured['width'] * featured['height'] > 500000:
        reasons.append("Large size")
    
    featured['selection_reason'] = ", ".join(reasons)
    return featured

def encode_image_to_base64(image_path: str) -> str:
    """Encode image file to base64 for API usage."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_text_and_images(pdf_path: str, output_dir: str = None, max_pages: int = None) -> Tuple[str, List[Dict], List[Dict], Optional[Dict]]:
    """
    Extract text, images, and captions from PDF.
    Returns (text_content, image_list, caption_list, featured_image)
    """
    print(f"Starting comprehensive extraction from: {os.path.basename(pdf_path)}")
    
    # Extract text
    text_content = extract_text_from_pdf(pdf_path, max_pages)
    
    # Extract images
    try:
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(pdf_path), "extracted_images")
        images = extract_images_from_pdf(pdf_path, output_dir)
    except Exception as e:
        print(f"Image extraction failed: {e}")
        images = []
    
    # Extract captions
    try:
        captions = extract_image_captions(pdf_path)
    except Exception as e:
        print(f"Caption extraction failed: {e}")
        captions = []
    
    # Select featured image
    featured_image = None
    if images:
        try:
            featured_image = select_featured_image(images, captions)
            if featured_image:
                print(f"Selected featured image: {featured_image['filename']} ({featured_image['selection_reason']})")
        except Exception as e:
            print(f"Featured image selection failed: {e}")
    
    print(f"Extraction complete: {len(text_content)} chars text, {len(images)} images, {len(captions)} captions")
    return text_content, images, captions, featured_image

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        pdf = sys.argv[1]
        print(f"Extracting text from: {pdf}")
        print("Using:", "pdfplumber" if PDFPLUMBER_AVAILABLE else "PyMuPDF")
        print("-" * 50)
        result = extract_text_from_pdf(pdf, max_pages=5)
        print(result)