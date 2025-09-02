"""
Test PDF extraction to debug issues.
"""
import os
import sys
from dotenv import load_dotenv
from zotero_fetch import fetch_zotero_items
from text_extractor import extract_text_from_pdf
from zotero_path_finder import get_default_pdf_dir

def test_pdf_extraction(collection_name=None, limit=5):
    """Test PDF extraction on a few papers."""
    # Load environment
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(env_path)
    
    # Fetch items
    items = fetch_zotero_items(
        os.getenv('ZOTERO_USER_ID'),
        os.getenv('ZOTERO_API_KEY'),
        limit=limit,
        collection_filter=collection_name
    )
    
    if not items:
        print("No items found")
        return
    
    pdf_base_dir = get_default_pdf_dir()
    success_count = 0
    fail_count = 0
    
    print(f"\nTesting PDF extraction on {len(items)} papers...")
    print("=" * 80)
    
    for item in items:
        title = item['title'][:60]
        print(f"\n📄 {title}...")
        
        # Find PDF
        pdf_path = None
        if item['attachments']:
            attachment = item['attachments'][0]
            relative_path = attachment.get('path', '')
            
            if relative_path:
                if relative_path.startswith('storage/'):
                    pdf_path = os.path.join(pdf_base_dir, relative_path)
                else:
                    pdf_path = os.path.join(pdf_base_dir, 'storage', relative_path)
        
        if not pdf_path:
            print("   ❌ No PDF attachment found")
            fail_count += 1
            continue
            
        if not os.path.exists(pdf_path):
            print(f"   ❌ PDF not found: {pdf_path}")
            fail_count += 1
            continue
        
        # Try extraction with detailed analysis
        try:
            # First check file size
            file_size = os.path.getsize(pdf_path)
            print(f"   📋 File size: {file_size:,} bytes")
            
            # Try extraction
            text = extract_text_from_pdf(pdf_path, max_pages=5)  # First 5 pages
            words = len(text.split())
            chars = len(text)
            
            # Analyze quality
            lines = text.split('\n')
            non_empty_lines = [l for l in lines if l.strip()]
            avg_line_length = sum(len(l) for l in non_empty_lines) / len(non_empty_lines) if non_empty_lines else 0
            
            print(f"   ✅ Extraction complete:")
            print(f"      - Words: {words:,}")
            print(f"      - Characters: {chars:,}")
            print(f"      - Lines: {len(lines)} ({len(non_empty_lines)} non-empty)")
            print(f"      - Avg line length: {avg_line_length:.1f}")
            
            # Show first few lines
            preview_lines = [l.strip() for l in lines[:10] if l.strip()]
            if preview_lines:
                print(f"   First few lines:")
                for line in preview_lines[:3]:
                    print(f"      > {line[:80]}...")
            
            # Quality assessment
            if chars < 100:
                print("   ⚠️  PROBLEM: Almost no text extracted")
            elif words < 50:
                print("   ⚠️  PROBLEM: Very few words")
            elif avg_line_length > 200:
                print("   ⚠️  PROBLEM: Lines too long, might be corrupted")
            elif "PDF" in text[:100] and "%" in text[:100]:
                print("   ⚠️  PROBLEM: Looks like raw PDF code")
            else:
                print("   ✨ Good extraction quality")
                
            success_count += 1
            
        except Exception as e:
            print(f"   ❌ Extraction failed: {type(e).__name__}: {e}")
            
            # Try to understand why
            try:
                import fitz
                doc = fitz.open(pdf_path)
                print(f"   📄 PDF info: {doc.page_count} pages, metadata: {doc.metadata}")
                
                # Check first page
                page = doc.load_page(0)
                text = page.get_text()
                if not text.strip():
                    # Check if it has images (might be scanned)
                    image_list = page.get_images()
                    if image_list:
                        print(f"   🖼️  Page has {len(image_list)} images - might be scanned PDF")
                    else:
                        print(f"   ❓ Page appears truly empty")
                doc.close()
            except:
                pass
                
            fail_count += 1
    
    print("\n" + "=" * 80)
    print(f"Summary: {success_count} success, {fail_count} failed")
    
    if fail_count > success_count:
        print("\n⚠️  High failure rate detected!")
        print("Common causes:")
        print("- Scanned PDFs (image-based, not text)")
        print("- Corrupted PDF files")
        print("- Password-protected PDFs")
        print("- Missing PDF files (not synced)")

if __name__ == "__main__":
    collection = sys.argv[1] if len(sys.argv) > 1 else None
    test_pdf_extraction(collection, limit=10)