#!/bin/bash
# Restore archived papers back to main folder

ARCHIVE_DIR="/Users/fourmodern/Library/Mobile Documents/iCloud~md~obsidian/Documents/fourmodern/80. References/81. zotero/_archived/20251122"
MAIN_DIR="/Users/fourmodern/Library/Mobile Documents/iCloud~md~obsidian/Documents/fourmodern/80. References/81. zotero"

echo "🔄 Restoring papers from archive..."
echo "Archive: $ARCHIVE_DIR"
echo "Target: $MAIN_DIR"
echo ""

# Count files
FILE_COUNT=$(find "$ARCHIVE_DIR" -name "*.md" -type f | wc -l | xargs)
echo "📄 Found $FILE_COUNT files to restore"
echo ""

# Restore all .md files
RESTORED=0
ERRORS=0

find "$ARCHIVE_DIR" -name "*.md" -type f | while read -r file; do
    # Get just the filename
    filename=$(basename "$file")

    # Move back to main directory (Uncategorized folder)
    target="$MAIN_DIR/Uncategorized/$filename"

    # Create Uncategorized if it doesn't exist
    mkdir -p "$MAIN_DIR/Uncategorized"

    # Move file
    if mv "$file" "$target" 2>/dev/null; then
        echo "✓ Restored: $filename"
        ((RESTORED++))
    else
        echo "✗ Failed: $filename"
        ((ERRORS++))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Restoration complete!"
echo "   Restored: $FILE_COUNT files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
