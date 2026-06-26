"""
Enhanced Text Chunker with Character-based Splitting
문자 기반 청킹: 1000자 단위, 200자 중첩
"""

import re
from typing import List, Dict, Optional


class EnhancedTextChunker:
    """
    Character-based text chunker with section awareness.
    Chunks text by characters (not words) with specified overlap.
    """

    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        """
        Initialize the chunker.

        Args:
            chunk_size: Number of characters per chunk
            overlap: Number of overlapping characters between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

        # Section markers for academic papers
        self.section_markers = [
            'abstract', 'introduction', 'background', 'related work',
            'methodology', 'methods', 'materials and methods',
            'results', 'experiments', 'evaluation', 'experimental results',
            'discussion', 'conclusion', 'conclusions', 'future work',
            'references', 'bibliography', 'appendix', 'supplementary'
        ]

    def chunk_text(self, text: str, metadata: Dict = None) -> List[Dict]:
        """
        Chunk text by characters with section awareness.

        Args:
            text: Full text to chunk
            metadata: Paper metadata to include in chunks

        Returns:
            List of chunk dictionaries
        """
        if not text:
            return []

        # Skip section identification for speed - just chunk the entire text
        # First, identify sections
        # sections = self._identify_sections(text)  # SLOW - disabled
        sections = [{'name': 'full_text', 'text': text, 'start_pos': 0, 'end_pos': len(text)}]

        # Chunk each section separately to maintain context
        all_chunks = []
        chunk_index = 0

        for section in sections:
            section_chunks = self._chunk_section(
                section['text'],
                section['name'],
                chunk_index,
                metadata
            )
            all_chunks.extend(section_chunks)
            chunk_index += len(section_chunks)

        return all_chunks

    def _identify_sections(self, text: str) -> List[Dict]:
        """
        Identify sections in the text.

        Args:
            text: Full text

        Returns:
            List of sections with their text and names
        """
        sections = []
        lines = text.split('\n')
        current_section = 'unknown'
        section_text = []
        section_start_pos = 0
        current_pos = 0

        for line in lines:
            line_lower = line.lower().strip()
            current_pos += len(line) + 1  # +1 for newline

            # Check if this line is a section header
            section_found = False
            for marker in self.section_markers:
                # Check for section markers at the beginning of lines
                if (marker in line_lower and
                    len(line_lower) < 50 and  # Section headers are usually short
                    (line_lower.startswith(marker) or
                     line_lower.startswith(f"{marker}") or
                     re.match(rf'^\d+\.?\s*{marker}', line_lower))):

                    # Save previous section
                    if section_text:
                        sections.append({
                            'name': current_section,
                            'text': '\n'.join(section_text),
                            'start_pos': section_start_pos,
                            'end_pos': current_pos - len(line) - 1
                        })

                    # Start new section
                    current_section = marker
                    section_text = [line]
                    section_start_pos = current_pos - len(line) - 1
                    section_found = True
                    break

            if not section_found:
                section_text.append(line)

        # Save the last section
        if section_text:
            sections.append({
                'name': current_section,
                'text': '\n'.join(section_text),
                'start_pos': section_start_pos,
                'end_pos': current_pos
            })

        # If no sections were found, treat entire text as one section
        if not sections:
            sections = [{
                'name': 'full_text',
                'text': text,
                'start_pos': 0,
                'end_pos': len(text)
            }]

        return sections

    def _chunk_section(self,
                      text: str,
                      section_name: str,
                      start_index: int,
                      metadata: Dict = None) -> List[Dict]:
        """
        Chunk a section of text by characters.

        Args:
            text: Section text to chunk
            section_name: Name of the section
            start_index: Starting chunk index
            metadata: Paper metadata

        Returns:
            List of chunks for this section
        """
        chunks = []

        if not text:
            return chunks

        text_length = len(text)
        chunk_start = 0

        while chunk_start < text_length:
            # Calculate chunk end
            chunk_end = min(chunk_start + self.chunk_size, text_length)

            # Extract chunk text
            chunk_text = text[chunk_start:chunk_end]

            # Try to avoid breaking in the middle of a word at chunk boundaries
            if chunk_end < text_length and chunk_start > 0:
                # Look for last space or punctuation to break at
                last_break = max(
                    chunk_text.rfind(' '),
                    chunk_text.rfind('\n'),
                    chunk_text.rfind('.'),
                    chunk_text.rfind(','),
                    chunk_text.rfind(';')
                )

                # If we found a good break point in the last 20% of chunk
                if last_break > self.chunk_size * 0.8:
                    chunk_text = chunk_text[:last_break + 1]
                    chunk_end = chunk_start + last_break + 1

            # Create chunk dictionary
            chunk_dict = {
                'text': chunk_text.strip(),
                'chunk_type': 'text',
                'chunk_index': start_index + len(chunks),
                'section': section_name,
                'char_start': chunk_start,
                'char_end': chunk_end,
                'char_count': len(chunk_text.strip()),
                'word_count': len(chunk_text.split())
            }

            # Add metadata if provided
            if metadata:
                chunk_dict['metadata'] = metadata

            chunks.append(chunk_dict)

            # Move to next chunk with overlap
            chunk_start = chunk_end - self.overlap

            # Ensure we make progress
            if chunk_start <= chunk_start - self.chunk_size + self.overlap:
                chunk_start = chunk_end

        return chunks

    def chunk_by_sentences(self,
                          text: str,
                          sentences_per_chunk: int = 5,
                          overlap_sentences: int = 1,
                          metadata: Dict = None) -> List[Dict]:
        """
        Alternative chunking by sentences.

        Args:
            text: Text to chunk
            sentences_per_chunk: Number of sentences per chunk
            overlap_sentences: Number of overlapping sentences
            metadata: Paper metadata

        Returns:
            List of chunks
        """
        # Split into sentences
        sentences = self._split_sentences(text)

        chunks = []
        chunk_index = 0

        for i in range(0, len(sentences), sentences_per_chunk - overlap_sentences):
            chunk_sentences = sentences[i:i + sentences_per_chunk]
            chunk_text = ' '.join(chunk_sentences)

            chunk_dict = {
                'text': chunk_text,
                'chunk_type': 'text',
                'chunk_index': chunk_index,
                'sentence_start': i,
                'sentence_end': i + len(chunk_sentences),
                'char_count': len(chunk_text),
                'word_count': len(chunk_text.split())
            }

            if metadata:
                chunk_dict['metadata'] = metadata

            chunks.append(chunk_dict)
            chunk_index += 1

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.

        Args:
            text: Text to split

        Returns:
            List of sentences
        """
        # Simple sentence splitting (can be improved with NLTK or spaCy)
        sentence_endings = re.compile(r'[.!?]\s+')
        sentences = sentence_endings.split(text)

        # Clean and filter sentences
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences

    def create_sliding_window_chunks(self,
                                   text: str,
                                   window_size: int = 1000,
                                   step_size: int = 800,
                                   metadata: Dict = None) -> List[Dict]:
        """
        Create chunks using a sliding window approach.

        Args:
            text: Text to chunk
            window_size: Size of the window in characters
            step_size: Step size for sliding (window_size - step_size = overlap)
            metadata: Paper metadata

        Returns:
            List of chunks
        """
        chunks = []
        text_length = len(text)

        for i in range(0, text_length, step_size):
            chunk_text = text[i:i + window_size]

            if len(chunk_text.strip()) < 50:  # Skip very small chunks
                continue

            chunk_dict = {
                'text': chunk_text.strip(),
                'chunk_type': 'text_sliding',
                'chunk_index': len(chunks),
                'char_start': i,
                'char_end': min(i + window_size, text_length),
                'char_count': len(chunk_text.strip()),
                'word_count': len(chunk_text.split())
            }

            if metadata:
                chunk_dict['metadata'] = metadata

            chunks.append(chunk_dict)

        return chunks


def test_chunker():
    """Test the enhanced text chunker."""
    sample_text = """
    Abstract
    This is the abstract of the paper. It contains a brief summary of the research.
    The abstract typically provides an overview of the problem, methodology, and key findings.

    Introduction
    The introduction section provides background information and motivation for the research.
    It explains why this research is important and what gap it aims to fill in the existing literature.
    Previous work has shown that chunking strategies significantly impact retrieval performance.

    Methods
    We propose a character-based chunking approach with 1000 character chunks and 200 character overlap.
    This ensures that context is preserved across chunk boundaries while maintaining reasonable chunk sizes.
    Our method differs from traditional word-based chunking by providing more consistent chunk sizes.

    Results
    Our experiments show that character-based chunking with overlap improves retrieval accuracy by 15%.
    The overlap helps maintain context continuity, especially for technical terms that may be split across chunks.

    Conclusion
    Character-based chunking with overlap provides better performance for RAG systems.
    Future work will explore adaptive chunking strategies based on content type.
    """

    # Initialize chunker
    chunker = EnhancedTextChunker(chunk_size=200, overlap=50)

    # Test character-based chunking
    print("Testing character-based chunking:")
    print("-" * 50)
    chunks = chunker.chunk_text(sample_text)

    for i, chunk in enumerate(chunks):
        print(f"\nChunk {i + 1}:")
        print(f"  Section: {chunk['section']}")
        print(f"  Characters: {chunk['char_count']}")
        print(f"  Text preview: {chunk['text'][:100]}...")

    # Test sentence-based chunking
    print("\n\nTesting sentence-based chunking:")
    print("-" * 50)
    sentence_chunks = chunker.chunk_by_sentences(sample_text, sentences_per_chunk=3)

    for i, chunk in enumerate(sentence_chunks[:3]):
        print(f"\nChunk {i + 1}:")
        print(f"  Characters: {chunk['char_count']}")
        print(f"  Text: {chunk['text'][:150]}...")


if __name__ == "__main__":
    test_chunker()