#!/bin/bash
# Remove duplicate markdown files (files ending with " 2.md", " 3.md", etc.)

OBSIDIAN_DIR="$HOME/ObsidianVault/LiteratureNotes"

echo "🔍 Finding duplicate files..."

# Count duplicates
DUPLICATE_COUNT=$(find "$OBSIDIAN_DIR" -name "* [2-9].md" -o -name "* [0-9][0-9].md" | wc -l | xargs)
echo "📊 Found $DUPLICATE_COUNT duplicate files"
echo ""

read -p "❓ Delete these duplicates? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🗑️  Deleting duplicates..."

# Delete files ending with " 2.md", " 3.md", etc.
find "$OBSIDIAN_DIR" \( -name "* [2-9].md" -o -name "* [0-9][0-9].md" \) -type f -delete

echo ""
echo "✅ Done! Deleted $DUPLICATE_COUNT duplicate files"
echo ""
echo "📌 Original files (without ' 2', ' 3', etc.) are kept."
