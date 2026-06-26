"""
Caption Vectorizer for Figures and Tables
Figure/Table 캡션을 별도의 벡터로 변환
"""

from typing import List, Dict, Optional
import re


class CaptionVectorizer:
    """
    Create separate vectors for figure and table captions.
    Each caption becomes an independent chunk for better retrieval.
    """

    def __init__(self):
        """Initialize the caption vectorizer."""
        self.figure_patterns = [
            r'Figure\s+(\d+[A-Za-z]?)',
            r'Fig\.?\s+(\d+[A-Za-z]?)',
            r'그림\s*(\d+)',
            r'図\s*(\d+)',
            r'图\s*(\d+)'
        ]

        self.table_patterns = [
            r'Table\s+(\d+[A-Za-z]?)',
            r'표\s*(\d+)',
            r'表\s*(\d+)'
        ]

    def create_caption_chunks(self,
                            figures: List[Dict],
                            tables: List[Dict],
                            raw_captions: List[Dict],
                            metadata: Dict = None) -> List[Dict]:
        """
        Create vector chunks for all captions.

        Args:
            figures: List of figure captions from extract_figures_and_tables
            tables: List of table captions from extract_figures_and_tables
            raw_captions: Raw captions from extract_image_captions
            metadata: Paper metadata to include

        Returns:
            List of caption chunks ready for vectorization
        """
        chunks = []

        # Process figure captions
        figure_chunks = self._process_figure_captions(figures, metadata)
        chunks.extend(figure_chunks)

        # Process table captions
        table_chunks = self._process_table_captions(tables, metadata)
        chunks.extend(table_chunks)

        # Process any additional raw captions
        if raw_captions:
            raw_chunks = self._process_raw_captions(raw_captions, metadata)
            chunks.extend(raw_chunks)

        # Add chunk indices
        for i, chunk in enumerate(chunks):
            chunk['caption_index'] = i

        return chunks

    def _process_figure_captions(self,
                                figures: List[Dict],
                                metadata: Dict = None) -> List[Dict]:
        """
        Process figure captions into chunks.

        Args:
            figures: List of figure dictionaries with 'number', 'title', 'page'
            metadata: Paper metadata

        Returns:
            List of figure caption chunks
        """
        chunks = []

        for fig in figures:
            # Create the caption text
            caption_text = self._format_figure_caption(fig)

            # Create chunk dictionary
            chunk = {
                'text': caption_text,
                'chunk_type': 'figure_caption',
                'figure_number': fig.get('number', ''),
                'page': fig.get('page', 0),
                'section': 'figure',
                'original_title': fig.get('title', ''),
                'char_count': len(caption_text),
                'word_count': len(caption_text.split())
            }

            # Add metadata if provided
            if metadata:
                chunk['metadata'] = metadata

            # Add search-friendly versions
            chunk['search_terms'] = self._generate_search_terms(caption_text, 'figure')

            chunks.append(chunk)

        return chunks

    def _process_table_captions(self,
                               tables: List[Dict],
                               metadata: Dict = None) -> List[Dict]:
        """
        Process table captions into chunks.

        Args:
            tables: List of table dictionaries with 'number', 'title', 'page'
            metadata: Paper metadata

        Returns:
            List of table caption chunks
        """
        chunks = []

        for table in tables:
            # Create the caption text
            caption_text = self._format_table_caption(table)

            # Create chunk dictionary
            chunk = {
                'text': caption_text,
                'chunk_type': 'table_caption',
                'table_number': table.get('number', ''),
                'page': table.get('page', 0),
                'section': 'table',
                'original_title': table.get('title', ''),
                'char_count': len(caption_text),
                'word_count': len(caption_text.split())
            }

            # Add metadata if provided
            if metadata:
                chunk['metadata'] = metadata

            # Add search-friendly versions
            chunk['search_terms'] = self._generate_search_terms(caption_text, 'table')

            chunks.append(chunk)

        return chunks

    def _process_raw_captions(self,
                            raw_captions: List[Dict],
                            metadata: Dict = None) -> List[Dict]:
        """
        Process raw captions that weren't categorized as figures or tables.

        Args:
            raw_captions: List of raw caption dictionaries
            metadata: Paper metadata

        Returns:
            List of caption chunks
        """
        chunks = []

        for caption in raw_captions:
            # Determine caption type
            caption_type = self._determine_caption_type(caption.get('text', ''))

            # Create chunk dictionary
            chunk = {
                'text': caption.get('text', ''),
                'chunk_type': f'{caption_type}_caption',
                'page': caption.get('page', 0),
                'section': caption_type,
                'priority': caption.get('priority', 0),
                'char_count': len(caption.get('text', '')),
                'word_count': len(caption.get('text', '').split())
            }

            # Add metadata if provided
            if metadata:
                chunk['metadata'] = metadata

            chunks.append(chunk)

        return chunks

    def _format_figure_caption(self, figure: Dict) -> str:
        """
        Format a figure caption for vectorization.

        Args:
            figure: Figure dictionary

        Returns:
            Formatted caption text
        """
        number = figure.get('number', '')
        title = figure.get('title', '')

        # Create a comprehensive caption
        if title and not title.startswith('Figure'):
            caption = f"Figure {number}: {title}"
        else:
            caption = title if title else f"Figure {number}"

        # Add context for better retrieval
        page = figure.get('page', 0)
        if page:
            caption += f" (Page {page})"

        return caption

    def _format_table_caption(self, table: Dict) -> str:
        """
        Format a table caption for vectorization.

        Args:
            table: Table dictionary

        Returns:
            Formatted caption text
        """
        number = table.get('number', '')
        title = table.get('title', '')

        # Create a comprehensive caption
        if title and not title.startswith('Table'):
            caption = f"Table {number}: {title}"
        else:
            caption = title if title else f"Table {number}"

        # Add context for better retrieval
        page = table.get('page', 0)
        if page:
            caption += f" (Page {page})"

        return caption

    def _determine_caption_type(self, text: str) -> str:
        """
        Determine the type of caption from its text.

        Args:
            text: Caption text

        Returns:
            Caption type ('figure', 'table', 'scheme', etc.)
        """
        text_lower = text.lower()

        # Check for figure patterns
        for pattern in self.figure_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return 'figure'

        # Check for table patterns
        for pattern in self.table_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return 'table'

        # Check for other types
        if 'scheme' in text_lower or 'schema' in text_lower:
            return 'scheme'
        elif 'chart' in text_lower:
            return 'chart'
        elif 'graph' in text_lower:
            return 'graph'
        elif 'diagram' in text_lower:
            return 'diagram'
        elif 'equation' in text_lower or 'eq.' in text_lower:
            return 'equation'
        elif 'algorithm' in text_lower:
            return 'algorithm'
        else:
            return 'other'

    def _generate_search_terms(self, caption_text: str, caption_type: str) -> List[str]:
        """
        Generate search-friendly terms from caption.

        Args:
            caption_text: Caption text
            caption_type: Type of caption

        Returns:
            List of search terms
        """
        terms = []

        # Add type variations
        if caption_type == 'figure':
            terms.extend(['figure', 'fig', 'image', 'diagram', '그림', '図', '图'])
        elif caption_type == 'table':
            terms.extend(['table', 'data', '표', '表'])

        # Extract numbers
        numbers = re.findall(r'\d+', caption_text)
        for num in numbers:
            terms.append(f"{caption_type} {num}")
            terms.append(f"{caption_type[:3]} {num}")

        # Extract key technical terms (simplified)
        # In production, use NLP libraries for better term extraction
        words = caption_text.lower().split()
        technical_terms = [
            w for w in words
            if len(w) > 4 and w not in ['figure', 'table', 'shows', 'presents', 'illustrates']
        ]
        terms.extend(technical_terms[:5])  # Top 5 terms

        return terms

    def enhance_with_context(self,
                           caption_chunks: List[Dict],
                           full_text: str,
                           window_size: int = 500) -> List[Dict]:
        """
        Enhance caption chunks with surrounding context from the main text.

        Args:
            caption_chunks: List of caption chunks
            full_text: Full paper text
            window_size: Characters of context to include

        Returns:
            Enhanced caption chunks
        """
        enhanced_chunks = []

        for chunk in caption_chunks:
            enhanced_chunk = chunk.copy()

            # Try to find references to this figure/table in the text
            if chunk['chunk_type'] == 'figure_caption':
                ref_patterns = [
                    f"Figure {chunk.get('figure_number', '')}",
                    f"Fig. {chunk.get('figure_number', '')}",
                    f"Fig {chunk.get('figure_number', '')}",
                    f"figure {chunk.get('figure_number', '')}"
                ]
            elif chunk['chunk_type'] == 'table_caption':
                ref_patterns = [
                    f"Table {chunk.get('table_number', '')}",
                    f"table {chunk.get('table_number', '')}"
                ]
            else:
                ref_patterns = []

            # Find and add context
            contexts = []
            for pattern in ref_patterns:
                indices = self._find_all_occurrences(full_text, pattern)
                for idx in indices[:3]:  # Limit to 3 references
                    # Extract surrounding context
                    start = max(0, idx - window_size // 2)
                    end = min(len(full_text), idx + len(pattern) + window_size // 2)
                    context = full_text[start:end]

                    # Clean up context
                    context = self._clean_context(context)
                    if context:
                        contexts.append(context)

            # Add context to chunk
            if contexts:
                enhanced_chunk['context'] = ' ... '.join(contexts)
                enhanced_chunk['has_context'] = True
            else:
                enhanced_chunk['has_context'] = False

            enhanced_chunks.append(enhanced_chunk)

        return enhanced_chunks

    def _find_all_occurrences(self, text: str, pattern: str) -> List[int]:
        """
        Find all occurrences of a pattern in text.

        Args:
            text: Text to search
            pattern: Pattern to find

        Returns:
            List of starting indices
        """
        indices = []
        pattern_lower = pattern.lower()
        text_lower = text.lower()

        start = 0
        while start < len(text_lower):
            idx = text_lower.find(pattern_lower, start)
            if idx == -1:
                break
            indices.append(idx)
            start = idx + 1

        return indices

    def _clean_context(self, context: str) -> str:
        """
        Clean up extracted context.

        Args:
            context: Raw context string

        Returns:
            Cleaned context
        """
        # Remove excessive whitespace
        context = ' '.join(context.split())

        # Try to start at sentence beginning
        sentence_start = max(
            context.find('. ') + 2,
            0
        )
        if sentence_start > 50:  # Only if not too far from start
            context = context[sentence_start:]

        # Try to end at sentence end
        sentence_end = context.rfind('.')
        if sentence_end > len(context) - 50:  # Only if not too far from end
            context = context[:sentence_end + 1]

        return context.strip()


def test_caption_vectorizer():
    """Test the caption vectorizer."""

    # Sample data
    figures = [
        {'number': '1', 'title': 'Overview of the proposed architecture', 'page': 3},
        {'number': '2A', 'title': 'Experimental results on dataset A', 'page': 5},
        {'number': '3', 'title': 'Comparison with baseline methods', 'page': 7}
    ]

    tables = [
        {'number': '1', 'title': 'Dataset statistics and characteristics', 'page': 4},
        {'number': '2', 'title': 'Performance comparison across different models', 'page': 6}
    ]

    raw_captions = [
        {'text': 'Supplementary Figure S1: Additional experimental data', 'page': 15, 'priority': 70}
    ]

    metadata = {
        'title': 'Test Paper',
        'authors': ['Author1', 'Author2'],
        'year': '2024'
    }

    # Initialize vectorizer
    vectorizer = CaptionVectorizer()

    # Create caption chunks
    chunks = vectorizer.create_caption_chunks(figures, tables, raw_captions, metadata)

    print(f"Created {len(chunks)} caption chunks:\n")

    for i, chunk in enumerate(chunks):
        print(f"Chunk {i + 1}:")
        print(f"  Type: {chunk['chunk_type']}")
        print(f"  Page: {chunk.get('page', 'N/A')}")
        print(f"  Text: {chunk['text']}")
        if 'search_terms' in chunk:
            print(f"  Search terms: {chunk['search_terms']}")
        print()


if __name__ == "__main__":
    test_caption_vectorizer()