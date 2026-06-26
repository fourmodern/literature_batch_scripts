"""
Relation Manager for Cross-Database Connectivity
SQLite 기반 텍스트-이미지 관계 관리
"""

import os
import re
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import hashlib


class RelationManager:
    """
    Manages relationships between text chunks and images across databases.
    Uses SQLite for efficient relational queries and cross-references.
    """

    def __init__(self, db_path: str = "./databases/paper_relations.db"):
        """
        Initialize the relation manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Connect to database
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        self.cursor = self.conn.cursor()

        # Create tables if not exist
        self._create_tables()

        print(f"✅ Initialized RelationManager at {db_path}")

    def _create_tables(self):
        """Create database tables for relationships."""

        # Papers table - master information
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                paper_id TEXT PRIMARY KEY,
                title TEXT,
                authors TEXT,
                year INTEGER,
                doi TEXT,
                abstract TEXT,
                featured_image_id TEXT,
                text_chunk_count INTEGER DEFAULT 0,
                image_count INTEGER DEFAULT 0,
                caption_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Text chunks table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS text_chunks (
                chunk_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                chunk_index INTEGER,
                chunk_type TEXT,  -- 'text', 'caption', 'abstract'
                section TEXT,
                content TEXT,
                sentence_count INTEGER,
                char_count INTEGER,
                page_start INTEGER,
                page_end INTEGER,
                FOREIGN KEY (paper_id) REFERENCES papers (paper_id)
            )
        """)

        # Images table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                image_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                filename TEXT,
                page INTEGER,
                width INTEGER,
                height INTEGER,
                is_featured BOOLEAN DEFAULT 0,
                caption_id TEXT,
                image_type TEXT,  -- 'graph', 'chart', 'diagram', 'photo', 'table'
                FOREIGN KEY (paper_id) REFERENCES papers (paper_id)
            )
        """)

        # Captions table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS captions (
                caption_id TEXT PRIMARY KEY,
                paper_id TEXT NOT NULL,
                image_id TEXT,
                caption_text TEXT,
                caption_type TEXT,  -- 'figure', 'table', 'equation'
                page INTEGER,
                FOREIGN KEY (paper_id) REFERENCES papers (paper_id),
                FOREIGN KEY (image_id) REFERENCES images (image_id)
            )
        """)

        # Image-Text relations
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_text_relations (
                relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id TEXT NOT NULL,
                text_chunk_id TEXT NOT NULL,
                relation_type TEXT,  -- 'mentioned', 'caption', 'nearby', 'same_page'
                confidence REAL DEFAULT 1.0,
                context TEXT,
                FOREIGN KEY (image_id) REFERENCES images (image_id),
                FOREIGN KEY (text_chunk_id) REFERENCES text_chunks (chunk_id),
                UNIQUE(image_id, text_chunk_id, relation_type)
            )
        """)

        # Cross-references (Figure/Table references in text)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS cross_references (
                ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_chunk_id TEXT NOT NULL,
                target_id TEXT,  -- Can be image_id, table_id, etc.
                reference_type TEXT,  -- 'figure_ref', 'table_ref', 'equation_ref'
                reference_text TEXT,  -- The actual reference text, e.g., "Figure 3"
                position_start INTEGER,
                position_end INTEGER,
                FOREIGN KEY (source_chunk_id) REFERENCES text_chunks (chunk_id)
            )
        """)

        # Keywords/Entities for enhanced search
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                keyword_id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT NOT NULL,
                chunk_id TEXT,
                keyword TEXT,
                keyword_type TEXT,  -- 'entity', 'concept', 'method', 'chemical'
                frequency INTEGER DEFAULT 1,
                FOREIGN KEY (paper_id) REFERENCES papers (paper_id)
            )
        """)

        # Create indices for performance
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_text_chunks_paper ON text_chunks(paper_id)",
            "CREATE INDEX IF NOT EXISTS idx_images_paper ON images(paper_id)",
            "CREATE INDEX IF NOT EXISTS idx_captions_paper ON captions(paper_id)",
            "CREATE INDEX IF NOT EXISTS idx_relations_image ON image_text_relations(image_id)",
            "CREATE INDEX IF NOT EXISTS idx_relations_text ON image_text_relations(text_chunk_id)",
            "CREATE INDEX IF NOT EXISTS idx_references_source ON cross_references(source_chunk_id)",
            "CREATE INDEX IF NOT EXISTS idx_keywords_paper ON keywords(paper_id)",
            "CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword)"
        ]

        for idx in indices:
            self.cursor.execute(idx)

        self.conn.commit()

    def add_paper(self,
                  paper_id: str,
                  title: str = "",
                  authors: str = "",
                  year: int = 0,
                  doi: str = "",
                  abstract: str = "") -> bool:
        """
        Add or update paper information.

        Args:
            paper_id: Unique paper identifier
            title: Paper title
            authors: Authors (comma-separated)
            year: Publication year
            doi: DOI
            abstract: Abstract text

        Returns:
            Success status
        """
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO papers
                (paper_id, title, authors, year, doi, abstract, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (paper_id, title, authors, year, doi, abstract))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding paper {paper_id}: {e}")
            return False

    def add_text_chunk(self,
                      chunk_id: str,
                      paper_id: str,
                      chunk_data: Dict) -> bool:
        """
        Add text chunk information.

        Args:
            chunk_id: Unique chunk identifier (e.g., "PAPER_ID#T001")
            paper_id: Paper identifier
            chunk_data: Dictionary with chunk information

        Returns:
            Success status
        """
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO text_chunks
                (chunk_id, paper_id, chunk_index, chunk_type, section, content,
                 sentence_count, char_count, page_start, page_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id,
                paper_id,
                chunk_data.get('chunk_index', 0),
                chunk_data.get('chunk_type', 'text'),
                chunk_data.get('section', 'unknown'),
                chunk_data.get('text', '')[:1000],  # Store first 1000 chars
                chunk_data.get('sentence_count', 0),
                len(chunk_data.get('text', '')),
                chunk_data.get('page_start', 0),
                chunk_data.get('page_end', 0)
            ))

            # Update paper chunk count
            self.cursor.execute("""
                UPDATE papers
                SET text_chunk_count = (
                    SELECT COUNT(*) FROM text_chunks WHERE paper_id = ?
                )
                WHERE paper_id = ?
            """, (paper_id, paper_id))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding text chunk {chunk_id}: {e}")
            return False

    def add_image(self,
                  image_id: str,
                  paper_id: str,
                  image_data: Dict) -> bool:
        """
        Add image information.

        Args:
            image_id: Unique image identifier (e.g., "PAPER_ID#I001")
            paper_id: Paper identifier
            image_data: Dictionary with image information

        Returns:
            Success status
        """
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO images
                (image_id, paper_id, filename, page, width, height,
                 is_featured, caption_id, image_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                image_id,
                paper_id,
                image_data.get('filename', ''),
                image_data.get('page', 0),
                image_data.get('width', 0),
                image_data.get('height', 0),
                1 if image_data.get('is_featured', False) else 0,
                image_data.get('caption_id'),
                image_data.get('image_type', 'unknown')
            ))

            # Update featured image in papers table if needed
            if image_data.get('is_featured', False):
                self.cursor.execute("""
                    UPDATE papers SET featured_image_id = ? WHERE paper_id = ?
                """, (image_id, paper_id))

            # Update paper image count
            self.cursor.execute("""
                UPDATE papers
                SET image_count = (
                    SELECT COUNT(*) FROM images WHERE paper_id = ?
                )
                WHERE paper_id = ?
            """, (paper_id, paper_id))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding image {image_id}: {e}")
            return False

    def add_caption(self,
                   caption_id: str,
                   paper_id: str,
                   caption_data: Dict) -> bool:
        """
        Add caption information.

        Args:
            caption_id: Unique caption identifier
            paper_id: Paper identifier
            caption_data: Dictionary with caption information

        Returns:
            Success status
        """
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO captions
                (caption_id, paper_id, image_id, caption_text, caption_type, page)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                caption_id,
                paper_id,
                caption_data.get('image_id'),
                caption_data.get('text', ''),
                caption_data.get('type', 'figure'),
                caption_data.get('page', 0)
            ))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding caption {caption_id}: {e}")
            return False

    def add_image_text_relation(self,
                               image_id: str,
                               text_chunk_id: str,
                               relation_type: str = "nearby",
                               confidence: float = 1.0,
                               context: str = "") -> bool:
        """
        Add relationship between image and text chunk.

        Args:
            image_id: Image identifier
            text_chunk_id: Text chunk identifier
            relation_type: Type of relation
            confidence: Confidence score
            context: Additional context

        Returns:
            Success status
        """
        try:
            self.cursor.execute("""
                INSERT OR REPLACE INTO image_text_relations
                (image_id, text_chunk_id, relation_type, confidence, context)
                VALUES (?, ?, ?, ?, ?)
            """, (image_id, text_chunk_id, relation_type, confidence, context))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding relation: {e}")
            return False

    def extract_and_add_cross_references(self,
                                        chunk_id: str,
                                        text: str) -> int:
        """
        Extract and store figure/table references from text.

        Args:
            chunk_id: Source chunk identifier
            text: Text to analyze

        Returns:
            Number of references found
        """
        references = []

        # Patterns for different reference types
        patterns = {
            'figure_ref': [
                r'(?:Figure|Fig\.?|그림)\s*(\d+[A-Za-z]?)',
                r'도표\s*(\d+)',
                r'\((?:Figure|Fig\.?)\s*(\d+[A-Za-z]?)\)'
            ],
            'table_ref': [
                r'(?:Table|Tab\.?|표)\s*(\d+[A-Za-z]?)',
                r'\((?:Table|Tab\.?)\s*(\d+[A-Za-z]?)\)'
            ],
            'equation_ref': [
                r'(?:Equation|Eq\.?|식)\s*\(?(\d+)\)?',
                r'\((\d+)\)'  # Often equations are just numbered
            ]
        }

        for ref_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    references.append({
                        'source_chunk_id': chunk_id,
                        'target_id': f"{ref_type}_{match.group(1)}",
                        'reference_type': ref_type,
                        'reference_text': match.group(0),
                        'position_start': match.start(),
                        'position_end': match.end()
                    })

        # Store references in database
        for ref in references:
            try:
                self.cursor.execute("""
                    INSERT INTO cross_references
                    (source_chunk_id, target_id, reference_type, reference_text,
                     position_start, position_end)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    ref['source_chunk_id'],
                    ref['target_id'],
                    ref['reference_type'],
                    ref['reference_text'],
                    ref['position_start'],
                    ref['position_end']
                ))
            except:
                pass  # Skip duplicates

        self.conn.commit()
        return len(references)

    def get_paper_info(self, paper_id: str) -> Optional[Dict]:
        """
        Get complete paper information.

        Args:
            paper_id: Paper identifier

        Returns:
            Paper information dictionary
        """
        self.cursor.execute("""
            SELECT * FROM papers WHERE paper_id = ?
        """, (paper_id,))

        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_related_images(self, chunk_id: str) -> List[Dict]:
        """
        Get images related to a text chunk.

        Args:
            chunk_id: Text chunk identifier

        Returns:
            List of related images
        """
        self.cursor.execute("""
            SELECT i.*, r.relation_type, r.confidence
            FROM images i
            JOIN image_text_relations r ON i.image_id = r.image_id
            WHERE r.text_chunk_id = ?
            ORDER BY r.confidence DESC
        """, (chunk_id,))

        return [dict(row) for row in self.cursor.fetchall()]

    def get_image_context(self, image_id: str) -> List[Dict]:
        """
        Get text chunks related to an image.

        Args:
            image_id: Image identifier

        Returns:
            List of related text chunks
        """
        self.cursor.execute("""
            SELECT t.*, r.relation_type, r.confidence
            FROM text_chunks t
            JOIN image_text_relations r ON t.chunk_id = r.text_chunk_id
            WHERE r.image_id = ?
            ORDER BY r.confidence DESC
        """, (image_id,))

        return [dict(row) for row in self.cursor.fetchall()]

    def get_paper_images(self, paper_id: str) -> List[Dict]:
        """
        Get all images from a paper.

        Args:
            paper_id: Paper identifier

        Returns:
            List of images
        """
        self.cursor.execute("""
            SELECT * FROM images
            WHERE paper_id = ?
            ORDER BY page, image_id
        """, (paper_id,))

        return [dict(row) for row in self.cursor.fetchall()]

    def get_featured_image(self, paper_id: str) -> Optional[Dict]:
        """
        Get featured image of a paper.

        Args:
            paper_id: Paper identifier

        Returns:
            Featured image information
        """
        self.cursor.execute("""
            SELECT * FROM images
            WHERE paper_id = ? AND is_featured = 1
            LIMIT 1
        """, (paper_id,))

        row = self.cursor.fetchone()
        if row:
            return dict(row)
        return None

    def find_papers_by_keyword(self, keyword: str) -> List[Dict]:
        """
        Find papers containing a keyword.

        Args:
            keyword: Search keyword

        Returns:
            List of papers
        """
        self.cursor.execute("""
            SELECT DISTINCT p.*
            FROM papers p
            JOIN keywords k ON p.paper_id = k.paper_id
            WHERE k.keyword LIKE ?
            ORDER BY p.year DESC
        """, (f"%{keyword}%",))

        return [dict(row) for row in self.cursor.fetchall()]

    def get_statistics(self) -> Dict:
        """
        Get database statistics.

        Returns:
            Statistics dictionary
        """
        stats = {}

        # Count tables
        tables = ['papers', 'text_chunks', 'images', 'captions',
                 'image_text_relations', 'cross_references', 'keywords']

        for table in tables:
            self.cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[f"{table}_count"] = self.cursor.fetchone()[0]

        return stats

    def build_relationships_for_paper(self, paper_id: str):
        """
        Automatically build relationships for a paper.

        Args:
            paper_id: Paper identifier
        """
        # Get all text chunks and images for the paper
        self.cursor.execute("""
            SELECT chunk_id, content, page_start, page_end
            FROM text_chunks
            WHERE paper_id = ?
        """, (paper_id,))
        chunks = self.cursor.fetchall()

        self.cursor.execute("""
            SELECT image_id, page FROM images WHERE paper_id = ?
        """, (paper_id,))
        images = self.cursor.fetchall()

        # Build relationships based on page proximity
        for chunk in chunks:
            chunk_pages = range(chunk['page_start'], chunk['page_end'] + 1)

            for image in images:
                img_page = image['page']

                # Same page relation
                if img_page in chunk_pages:
                    self.add_image_text_relation(
                        image['image_id'],
                        chunk['chunk_id'],
                        'same_page',
                        confidence=0.9
                    )

                # Nearby relation (within 1 page)
                elif abs(img_page - chunk['page_start']) <= 1:
                    self.add_image_text_relation(
                        image['image_id'],
                        chunk['chunk_id'],
                        'nearby',
                        confidence=0.7
                    )

            # Extract cross-references
            self.extract_and_add_cross_references(chunk['chunk_id'], chunk['content'])

    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    """Test the relation manager."""
    rm = RelationManager()

    # Test adding paper
    rm.add_paper(
        "TEST001",
        title="Test Paper",
        authors="John Doe, Jane Smith",
        year=2024,
        abstract="This is a test abstract."
    )

    # Test adding chunks
    rm.add_text_chunk(
        "TEST001#T001",
        "TEST001",
        {'text': 'This is chunk 1 referring to Figure 1.', 'page_start': 1}
    )

    # Test adding image
    rm.add_image(
        "TEST001#I001",
        "TEST001",
        {'filename': 'figure1.png', 'page': 1, 'is_featured': True}
    )

    # Build relationships
    rm.build_relationships_for_paper("TEST001")

    # Get statistics
    stats = rm.get_statistics()
    print(f"Database statistics: {stats}")

    rm.close()


if __name__ == "__main__":
    main()