"""
Diagnostic script to check Zotero sync status and file availability.
"""
import os
import sys
from dotenv import load_dotenv
from pyzotero import zotero
from zotero_path_finder import get_default_pdf_dir

def check_zotero_sync():
    """Check Zotero sync status and file availability."""
    # Load environment
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    load_dotenv(env_path)
    
    user_id = os.getenv('ZOTERO_USER_ID')
    api_key = os.getenv('ZOTERO_API_KEY')
    
    if not user_id or not api_key:
        print("❌ Missing ZOTERO_USER_ID or ZOTERO_API_KEY in .env file")
        return
    
    print(f"🔍 Checking Zotero sync status for user {user_id}...\n")
    
    try:
        # Initialize Zotero API
        zot = zotero.Zotero(user_id, 'user', api_key)
        
        # Get storage info
        print("📊 Storage Information:")
        try:
            # Get last sync time
            last_sync = zot.last_modified_version()
            print(f"   Last sync version: {last_sync}")
        except Exception as e:
            print(f"   ⚠️  Could not get sync info: {e}")
        
        # Get a few recent items with attachments
        print("\n📄 Checking recent items with PDFs:")
        items = zot.items(limit=5, itemType='journalArticle')
        
        pdf_base_dir = get_default_pdf_dir()
        items_with_pdfs = 0
        items_with_sync = 0
        
        for item in items:
            title = item['data'].get('title', 'Unknown')[:50]
            print(f"\n   📖 {title}")
            
            # Get attachments
            attachments = zot.children(item['key'])
            pdf_attachments = [a for a in attachments if a['data'].get('contentType') == 'application/pdf']
            
            if not pdf_attachments:
                print(f"      ⚠️  No PDF attachments")
                continue
            
            items_with_pdfs += 1
            
            for att in pdf_attachments:
                att_data = att['data']
                file_key = att_data.get('key', '')
                filename = att_data.get('filename', 'document.pdf')
                
                print(f"      📎 Attachment: {filename}")
                print(f"         Key: {file_key}")
                
                # Check local file
                local_path = os.path.join(pdf_base_dir, 'storage', file_key, filename)
                if os.path.exists(local_path):
                    size = os.path.getsize(local_path)
                    print(f"         ✓ Local: {size:,} bytes")
                else:
                    print(f"         ✗ Not found locally")
                
                # Try to check if it's on server
                try:
                    # Test if we can access file info
                    file_info = zot.file(file_key)
                    if file_info:
                        items_with_sync += 1
                        print(f"         ✓ Available on Zotero server")
                    else:
                        print(f"         ⚠️  Empty response from server")
                except Exception as e:
                    if '404' in str(e):
                        print(f"         ✗ Not synced to Zotero server (404)")
                    else:
                        print(f"         ⚠️  Server check failed: {type(e).__name__}")
        
        # Summary
        print(f"\n📈 Summary:")
        print(f"   Items with PDFs: {items_with_pdfs}")
        print(f"   PDFs on server: {items_with_sync}")
        
        if items_with_sync == 0 and items_with_pdfs > 0:
            print("\n⚠️  No PDFs found on Zotero server!")
            print("\n🔧 Possible solutions:")
            print("   1. Check Zotero Preferences → Sync → Files")
            print("      - Enable 'Sync attachment files in My Library'")
            print("      - Choose 'Sync attachment files in group libraries using Zotero storage'")
            print("   2. In Zotero, right-click library → 'Sync' to force sync")
            print("   3. Check your Zotero storage quota at zotero.org/settings/storage")
            print("   4. If using WebDAV, verify WebDAV settings")
        
    except Exception as e:
        print(f"❌ Error connecting to Zotero API: {e}")
        print("\n🔧 Check:")
        print("   - Your API key has proper permissions")
        print("   - Your internet connection")
        print("   - Zotero API status at status.zotero.org")

if __name__ == "__main__":
    check_zotero_sync()