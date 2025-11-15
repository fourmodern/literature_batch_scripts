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
    Enhanced image extraction from PDF with multiple methods.
    Returns list of image metadata with paths.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(pdf_path), "extracted_images")
    
    os.makedirs(output_dir, exist_ok=True)
    
    images = []
    doc = fitz.open(pdf_path)
    
    print(f"Extracting images from {len(doc)} pages using enhanced methods...")
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        
        # Method 1: Standard image extraction
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            try:
                # Get image data
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                
                # Skip small images (likely logos, icons, artifacts)
                # Only keep meaningful figures/graphs (at least 200x200)
                if pix.width < 200 or pix.height < 200:
                    pix = None
                    continue

                # Skip images from first page (usually logos/headers)
                if page_num == 0 and pix.height < 400:
                    pix = None
                    continue

                # Skip very narrow or tall images (likely decorative lines)
                aspect_ratio = pix.width / pix.height
                if aspect_ratio < 0.2 or aspect_ratio > 5:
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
                
                # Store metadata with enhanced information
                images.append({
                    'path': img_path,
                    'filename': img_filename,
                    'page': page_num + 1,
                    'index': img_index + 1,
                    'width': pix.width,
                    'height': pix.height,
                    'size_bytes': len(img_data),
                    'extraction_method': 'standard'
                })
                
                print(f"  ✓ Extracted image: {img_filename} ({pix.width}x{pix.height})")
                pix = None
                
            except Exception as e:
                print(f"  ⚠️ Standard extraction failed for image {img_index} on page {page_num+1}: {e}")
                continue
        
        # Method 2: Try to extract images as rendered regions if standard method found nothing
        if not any(img['page'] == page_num + 1 for img in images):
            try:
                # Get page as pixmap (rendered image)
                mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
                pix = page.get_pixmap(matrix=mat)
                
                # Only save if page seems to contain non-text content
                # Check if page has minimal text (might be mostly images)
                text = page.get_text().strip()
                if len(text) < 500:  # Page with little text, likely image-heavy
                    img_filename = f"page{page_num+1}_rendered.png"
                    img_path = os.path.join(output_dir, img_filename)
                    
                    pix.save(img_path)
                    
                    images.append({
                        'path': img_path,
                        'filename': img_filename,
                        'page': page_num + 1,
                        'index': 0,
                        'width': pix.width,
                        'height': pix.height,
                        'size_bytes': os.path.getsize(img_path),
                        'extraction_method': 'rendered_page'
                    })
                    
                    print(f"  ✓ Extracted rendered page: {img_filename} (fallback method)")
                
                pix = None
            except Exception as e:
                print(f"  ⚠️ Rendered extraction failed for page {page_num+1}: {e}")
    
    doc.close()
    
    # Remove duplicates based on similar size and page
    unique_images = []
    seen = set()
    for img in images:
        key = (img['page'], img['width'], img['height'])
        if key not in seen:
            seen.add(key)
            unique_images.append(img)
    
    print(f"Extracted {len(unique_images)} unique images to {output_dir}")
    return unique_images

def extract_image_captions(pdf_path: str) -> List[Dict]:
    """
    Enhanced caption extraction with better pattern matching and multi-language support.
    """
    import re
    
    captions = []
    doc = fitz.open(pdf_path)
    
    # Enhanced caption patterns
    caption_patterns = [
        # English patterns
        (r'^(Figure|Fig\.?)\s+(\d+[A-Za-z]?|[A-Z]\d*)[:\.\s]', 100),
        (r'^(Table)\s+(\d+[A-Za-z]?|[A-Z]\d*)[:\.\s]', 90),
        (r'^(Scheme|Schema)\s+(\d+[A-Za-z]?|[A-Z]\d*)[:\.\s]', 95),
        (r'^(Chart|Graph)\s+(\d+[A-Za-z]?|[A-Z]\d*)[:\.\s]', 85),
        (r'^(Supplementary\s+Figure|Supp\.?\s*Fig\.?)\s+', 70),
        (r'^(Graphical\s+Abstract)', 150),
        # Korean patterns
        (r'^(그림|도표)\s*(\d+)[:\.\s]', 100),
        (r'^(표)\s*(\d+)[:\.\s]', 90),
        (r'^(도식|스킴)\s*(\d+)[:\.\s]', 95),
        # Japanese patterns
        (r'^(図|圖)\s*(\d+)[:\.\s]', 100),
        (r'^(表)\s*(\d+)[:\.\s]', 90),
        # Chinese patterns
        (r'^(图|圖)\s*(\d+)[:\.\s]', 100),
        (r'^(表)\s*(\d+)[:\.\s]', 90),
    ]
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        blocks = page.get_text("dict")
        
        for block in blocks["blocks"]:
            if block["type"] == 0:  # Text block
                # Build complete block text
                full_text = ""
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    full_text += line_text + " "
                
                full_text = full_text.strip()
                if not full_text:
                    continue
                
                # Check against patterns
                priority = 0
                caption_type = None
                figure_number = None
                
                for pattern, score in caption_patterns:
                    match = re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE)
                    if match:
                        priority = max(priority, score)
                        if len(match.groups()) >= 2:
                            figure_number = match.group(2)
                        caption_type = match.group(1) if match.groups() else 'Caption'
                        break
                
                # Also check for keywords if no pattern matched
                if priority == 0:
                    text_lower = full_text.lower()
                    keyword_scores = {
                        'figure': 50, 'fig': 50, 'table': 40, 'scheme': 45,
                        'chart': 30, 'graph': 30, 'diagram': 35,
                        '그림': 50, '표': 40, '도표': 35, '도식': 45,
                        '図': 50, '表': 40, '图': 50
                    }
                    
                    for keyword, score in keyword_scores.items():
                        if keyword in text_lower and len(full_text) < 500:  # Captions are usually short
                            priority = max(priority, score)
                            caption_type = keyword.capitalize()
                
                if priority > 0:
                    # Extract clean caption text (remove the Figure X: part)
                    clean_text = full_text
                    if figure_number:
                        # Try to extract just the description part
                        parts = re.split(r'[:\.\s]\s*', full_text, maxsplit=2)
                        if len(parts) > 2:
                            clean_text = parts[2]
                    
                    captions.append({
                        'page': page_num + 1,
                        'text': full_text,
                        'clean_text': clean_text,
                        'bbox': block["bbox"],
                        'priority': priority,
                        'type': caption_type,
                        'number': figure_number
                    })
    
    doc.close()
    
    # Remove duplicates and sort by priority
    seen = set()
    unique_captions = []
    for cap in captions:
        # Use first 100 chars for deduplication
        key = (cap['page'], cap['text'][:100])
        if key not in seen:
            seen.add(key)
            unique_captions.append(cap)
    
    unique_captions.sort(key=lambda x: (-x['priority'], x['page']))
    return unique_captions

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

def match_images_with_captions(images: List[Dict], captions: List[Dict]) -> List[Dict]:
    """
    Match images with their captions using proximity and content analysis.
    Returns images with matched caption information.
    """
    if not images:
        return []
    
    matched_images = []
    
    for img in images:
        img_copy = img.copy()
        img_copy['caption'] = None
        img_copy['caption_confidence'] = 0
        
        # Find best matching caption
        best_match = None
        best_score = 0
        
        for caption in captions:
            # Calculate matching score based on proximity
            score = 0
            
            # Same page = high score
            if caption['page'] == img['page']:
                score += 100
            # Adjacent page = medium score
            elif abs(caption['page'] - img['page']) == 1:
                score += 50
            else:
                continue  # Skip if too far
            
            # Position-based scoring (if bbox available)
            if 'bbox' in caption and 'bbox' in img:
                # Calculate vertical distance
                img_y = img.get('bbox', [0, 0, 0, 0])[1]
                cap_y = caption['bbox'][1]
                distance = abs(img_y - cap_y)
                
                # Closer = higher score
                if distance < 100:
                    score += 50
                elif distance < 200:
                    score += 30
                elif distance < 300:
                    score += 10
            
            # Caption type bonus
            if caption.get('type', '').lower() in ['figure', 'fig', '그림', '図', '图']:
                score += 20
            
            # Priority bonus
            score += caption.get('priority', 0) / 10
            
            if score > best_score:
                best_score = score
                best_match = caption
        
        if best_match:
            img_copy['caption'] = best_match['text']
            img_copy['caption_clean'] = best_match.get('clean_text', best_match['text'])
            img_copy['caption_confidence'] = min(best_score / 200, 1.0)  # Normalize to 0-1
            img_copy['caption_type'] = best_match.get('type', 'Unknown')
            img_copy['caption_number'] = best_match.get('number', '')
        
        matched_images.append(img_copy)
    
    return matched_images

def identify_key_figures(images: List[Dict], captions: List[Dict]) -> List[Dict]:
    """
    Enhanced figure importance scoring with caption matching.
    Returns images with priority scores and matched captions.
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
    Enhanced extraction with better image-caption matching.
    Returns (text_content, image_list, caption_list, featured_image)
    """
    print(f"Starting enhanced extraction from: {os.path.basename(pdf_path)}")
    
    # Extract text
    text_content = extract_text_from_pdf(pdf_path, max_pages)
    
    # Extract images with enhanced methods
    try:
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(pdf_path), "extracted_images")
        images = extract_images_from_pdf(pdf_path, output_dir)
        print(f"  📷 Extracted {len(images)} images")
    except Exception as e:
        print(f"  ⚠️ Image extraction failed: {e}")
        images = []
    
    # Extract captions with enhanced patterns
    try:
        captions = extract_image_captions(pdf_path)
        print(f"  📝 Found {len(captions)} captions")
    except Exception as e:
        print(f"  ⚠️ Caption extraction failed: {e}")
        captions = []
    
    # Match images with captions
    if images and captions:
        try:
            images = match_images_with_captions(images, captions)
            matched_count = sum(1 for img in images if img.get('caption'))
            print(f"  🔗 Matched {matched_count}/{len(images)} images with captions")
        except Exception as e:
            print(f"  ⚠️ Caption matching failed: {e}")
    
    # Select featured image
    featured_image = None
    if images:
        try:
            # First try to find images with high-confidence caption matches
            high_confidence_images = [img for img in images if img.get('caption_confidence', 0) > 0.7]
            if high_confidence_images:
                featured_image = select_featured_image(high_confidence_images, captions)
            else:
                featured_image = select_featured_image(images, captions)
            
            if featured_image:
                reason = featured_image.get('selection_reason', 'Best available')
                if featured_image.get('caption'):
                    print(f"  ⭐ Featured: {featured_image['filename']} - {reason}")
                    print(f"     Caption: {featured_image['caption'][:100]}...")
                else:
                    print(f"  ⭐ Featured: {featured_image['filename']} - {reason} (no caption)")
        except Exception as e:
            print(f"  ⚠️ Featured image selection failed: {e}")
    
    print(f"✅ Extraction complete: {len(text_content):,} chars, {len(images)} images, {len(captions)} captions")
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