"""
Semantic Text Chunker with Sentence Boundary Preservation
의미 기반 텍스트 청킹: 문장 경계 보존, 섹션 인식
"""

import re
from typing import List, Dict, Optional, Tuple
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("Downloading NLTK punkt tokenizer...")
    nltk.download('punkt')


class SemanticChunker:
    """
    Semantic chunking that preserves sentence boundaries and section structure.
    문장 경계와 섹션 구조를 보존하는 의미 기반 청킹.
    """

    def __init__(self,
                 chunk_size: int = 1000,
                 overlap_size: int = 200,
                 min_chunk_size: int = 100):
        """
        Initialize the semantic chunker.

        Args:
            chunk_size: Target size for each chunk in characters
            overlap_size: Overlap between chunks in characters
            min_chunk_size: Minimum chunk size to avoid tiny fragments
        """
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.min_chunk_size = min_chunk_size

        # Common section headers in academic papers
        self.section_patterns = [
            r'^#+\s*(abstract|introduction|background|related\s*work)',
            r'^#+\s*(methods?|methodology|materials?\s*and\s*methods?)',
            r'^#+\s*(results?|experiments?|evaluation|findings)',
            r'^#+\s*(discussion|conclusion|future\s*work|limitations)',
            r'^#+\s*(references|bibliography|appendix|supplementary)',
            r'^\d+\.?\s*(introduction|background|methods?|results?|discussion)',
            r'^(abstract|introduction|methods?|results?|discussion|conclusion)[\s:\.]',
        ]
        self.section_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE)
                                 for p in self.section_patterns]

    def chunk_text(self,
                   text: str,
                   preserve_sections: bool = True,
                   metadata: Optional[Dict] = None) -> List[Dict]:
        """
        Chunk text with sentence boundary preservation.

        Args:
            text: Input text to chunk
            preserve_sections: Whether to identify and preserve section boundaries
            metadata: Optional metadata to include with chunks

        Returns:
            List of chunk dictionaries with text and metadata
        """
        if not text or len(text) < self.min_chunk_size:
            return [{
                'text': text,
                'chunk_index': 0,
                'chunk_type': 'text',
                'section': 'unknown',
                'metadata': metadata or {}
            }]

        # Step 1: Identify sections if requested
        if preserve_sections:
            sections = self._identify_sections(text)
        else:
            sections = [{'name': 'full_text', 'text': text, 'start': 0, 'end': len(text)}]

        # Step 2: Chunk each section separately
        all_chunks = []
        global_chunk_index = 0

        for section in sections:
            section_chunks = self._chunk_section(
                section['text'],
                section['name'],
                global_chunk_index,
                metadata
            )

            # Add section position info
            for chunk in section_chunks:
                chunk['section_start'] = section['start']
                chunk['section_end'] = section['end']

            all_chunks.extend(section_chunks)
            global_chunk_index += len(section_chunks)

        return all_chunks

    def _identify_sections(self, text: str) -> List[Dict]:
        """
        Identify sections in academic text using patterns.

        Args:
            text: Full text to analyze

        Returns:
            List of section dictionaries
        """
        sections = []

        # Find all section headers
        section_matches = []
        for pattern in self.section_patterns:
            for match in pattern.finditer(text):
                section_name = self._extract_section_name(match.group())
                if section_name:
                    section_matches.append({
                        'name': section_name,
                        'start': match.start(),
                        'match': match.group()
                    })

        # Sort by position
        section_matches.sort(key=lambda x: x['start'])

        # Create sections from matches
        if not section_matches:
            # No sections found, treat as single section
            return [{'name': 'full_text', 'text': text, 'start': 0, 'end': len(text)}]

        # Add content before first section if exists
        if section_matches[0]['start'] > 100:  # Significant content before first section
            sections.append({
                'name': 'preamble',
                'text': text[:section_matches[0]['start']],
                'start': 0,
                'end': section_matches[0]['start']
            })

        # Process each section
        for i, match in enumerate(section_matches):
            start = match['start']
            end = section_matches[i + 1]['start'] if i + 1 < len(section_matches) else len(text)

            sections.append({
                'name': match['name'],
                'text': text[start:end],
                'start': start,
                'end': end
            })

        return sections

    def _extract_section_name(self, header_text: str) -> Optional[str]:
        """
        Extract clean section name from header text.

        Args:
            header_text: Raw header text

        Returns:
            Cleaned section name or None
        """
        # Remove markdown headers, numbers, punctuation
        cleaned = re.sub(r'^#+\s*', '', header_text)
        cleaned = re.sub(r'^\d+\.?\s*', '', cleaned)
        cleaned = re.sub(r'[\s:\.]+$', '', cleaned)
        cleaned = cleaned.strip().lower()

        # Map to standard names
        section_map = {
            'introduction': 'introduction',
            'background': 'introduction',
            'related work': 'related_work',
            'methods': 'methods',
            'methodology': 'methods',
            'materials and methods': 'methods',
            'results': 'results',
            'experiments': 'results',
            'evaluation': 'results',
            'discussion': 'discussion',
            'conclusion': 'conclusion',
            'conclusions': 'conclusion',
            'future work': 'future_work',
            'references': 'references',
            'bibliography': 'references',
            'abstract': 'abstract'
        }

        return section_map.get(cleaned, cleaned if cleaned else None)

    def _chunk_section(self,
                      section_text: str,
                      section_name: str,
                      start_index: int,
                      metadata: Optional[Dict]) -> List[Dict]:
        """
        Chunk a single section preserving sentence boundaries.

        Args:
            section_text: Text of the section
            section_name: Name of the section
            start_index: Starting chunk index
            metadata: Optional metadata

        Returns:
            List of chunks from this section
        """
        if not section_text:
            return []

        # Tokenize into sentences
        sentences = self._smart_sent_tokenize(section_text)

        if not sentences:
            return [{
                'text': section_text,
                'chunk_index': start_index,
                'chunk_type': 'text',
                'section': section_name,
                'sentence_count': 0,
                'metadata': metadata or {}
            }]

        # Group sentences into chunks
        chunks = []
        current_chunk = []
        current_size = 0
        chunk_index = start_index

        for i, sentence in enumerate(sentences):
            sentence_size = len(sentence)

            # Check if adding this sentence exceeds chunk size
            if current_size + sentence_size > self.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = ' '.join(current_chunk)
                chunks.append({
                    'text': chunk_text,
                    'chunk_index': chunk_index,
                    'chunk_type': 'text',
                    'section': section_name,
                    'sentence_count': len(current_chunk),
                    'sentence_boundaries': self._get_sentence_boundaries(chunk_text),
                    'metadata': metadata or {}
                })
                chunk_index += 1

                # Create overlap: keep last few sentences
                overlap_sentences = self._get_overlap_sentences(current_chunk, self.overlap_size)
                current_chunk = overlap_sentences
                current_size = sum(len(s) + 1 for s in current_chunk)  # +1 for space

            current_chunk.append(sentence)
            current_size += sentence_size + 1  # +1 for space between sentences

        # Add remaining sentences as final chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append({
                'text': chunk_text,
                'chunk_index': chunk_index,
                'chunk_type': 'text',
                'section': section_name,
                'sentence_count': len(current_chunk),
                'sentence_boundaries': self._get_sentence_boundaries(chunk_text),
                'metadata': metadata or {}
            })

        return chunks

    def _smart_sent_tokenize(self, text: str) -> List[str]:
        """
        Smart sentence tokenization that handles academic text peculiarities.

        Args:
            text: Text to tokenize

        Returns:
            List of sentences
        """
        # Use NLTK's sentence tokenizer
        sentences = sent_tokenize(text)

        # Post-process to handle common issues
        processed = []
        for sent in sentences:
            # Skip very short fragments
            if len(sent.strip()) < 10:
                if processed:
                    # Append to previous sentence
                    processed[-1] += ' ' + sent
                else:
                    processed.append(sent)
            else:
                processed.append(sent.strip())

        # Handle special cases like "Fig. 1" or "et al." being split incorrectly
        final_sentences = []
        i = 0
        while i < len(processed):
            sent = processed[i]

            # Check if this ends with common abbreviation and next starts with lowercase
            if (i + 1 < len(processed) and
                re.search(r'\b(Fig|Tab|Eq|et al|e\.g|i\.e|vs|Dr|Prof|Inc|Ltd|Corp)\.$', sent) and
                processed[i + 1][0].islower()):
                # Merge with next sentence
                sent = sent + ' ' + processed[i + 1]
                i += 1

            final_sentences.append(sent)
            i += 1

        return final_sentences

    def _get_overlap_sentences(self, sentences: List[str], target_overlap: int) -> List[str]:
        """
        Get sentences for overlap, aiming for target character count.

        Args:
            sentences: List of sentences
            target_overlap: Target overlap size in characters

        Returns:
            List of sentences for overlap
        """
        if not sentences:
            return []

        overlap_sentences = []
        overlap_size = 0

        # Start from the end and work backwards
        for sent in reversed(sentences):
            if overlap_size + len(sent) <= target_overlap * 1.5:  # Allow some flexibility
                overlap_sentences.insert(0, sent)
                overlap_size += len(sent) + 1
            else:
                break

        # Ensure at least one sentence for overlap if possible
        if not overlap_sentences and sentences:
            overlap_sentences = [sentences[-1]]

        return overlap_sentences

    def _get_sentence_boundaries(self, text: str) -> List[int]:
        """
        Get character positions of sentence boundaries in text.

        Args:
            text: Chunk text

        Returns:
            List of boundary positions
        """
        boundaries = []
        sentences = sent_tokenize(text)

        pos = 0
        for sent in sentences:
            pos = text.find(sent, pos)
            if pos != -1:
                boundaries.append(pos)
                pos += len(sent)

        return boundaries


class HybridChunker(SemanticChunker):
    """
    Hybrid chunker that combines semantic chunking with additional features.
    Includes paragraph detection and special handling for lists and tables.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def chunk_with_paragraphs(self, text: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """
        Chunk text with paragraph awareness in addition to sentence boundaries.

        Args:
            text: Input text
            metadata: Optional metadata

        Returns:
            List of chunks
        """
        # Split into paragraphs first
        paragraphs = self._split_paragraphs(text)

        all_chunks = []
        chunk_index = 0

        for para_idx, para in enumerate(paragraphs):
            # Short paragraphs become single chunks
            if len(para) <= self.chunk_size:
                all_chunks.append({
                    'text': para,
                    'chunk_index': chunk_index,
                    'chunk_type': 'paragraph',
                    'paragraph_index': para_idx,
                    'sentence_count': len(sent_tokenize(para)),
                    'metadata': metadata or {}
                })
                chunk_index += 1
            else:
                # Long paragraphs use sentence-based chunking
                para_chunks = self._chunk_section(para, 'paragraph', chunk_index, metadata)
                for chunk in para_chunks:
                    chunk['paragraph_index'] = para_idx
                all_chunks.extend(para_chunks)
                chunk_index += len(para_chunks)

        return all_chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        """
        Split text into paragraphs.

        Args:
            text: Input text

        Returns:
            List of paragraphs
        """
        # Split on double newlines or multiple spaces
        paragraphs = re.split(r'\n\s*\n|\r\n\s*\r\n', text)

        # Filter out empty paragraphs and clean
        cleaned = []
        for para in paragraphs:
            para = para.strip()
            if para and len(para) > 20:  # Skip very short fragments
                cleaned.append(para)

        return cleaned


if __name__ == "__main__":
    # Test the chunker
    test_text = """
    # Introduction

    Large language models (LLMs) have revolutionized natural language processing.
    These models, trained on vast amounts of text data, demonstrate remarkable
    capabilities in understanding and generating human-like text. The development
    of transformer architectures has been particularly influential.

    # Methods

    We employed a BERT-based architecture for our experiments. The model was trained
    on a corpus of scientific papers. Training was conducted using distributed computing
    resources over a period of two weeks. We used a learning rate of 1e-4 with the
    Adam optimizer.

    Our evaluation metrics included accuracy, F1 score, and perplexity. We compared
    our results against several baseline models. The experiments were repeated three
    times to ensure statistical significance.

    # Results

    The proposed model achieved an accuracy of 92.3% on the test set. This represents
    a significant improvement over the baseline models. Table 1 shows the detailed
    performance metrics. Fig. 2 illustrates the learning curves during training.

    # Conclusion

    Our work demonstrates the effectiveness of semantic chunking for RAG systems.
    Future work will explore multilingual applications.
    """

    chunker = SemanticChunker(chunk_size=300, overlap_size=50)
    chunks = chunker.chunk_text(test_text, preserve_sections=True)

    print(f"Generated {len(chunks)} chunks:\n")
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1} (Section: {chunk['section']}, Sentences: {chunk['sentence_count']}):")
        print(f"  {chunk['text'][:100]}...")
        print()