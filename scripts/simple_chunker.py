"""
Simple and fast text chunker
간단하고 빠른 텍스트 청킹
"""

def simple_chunk_text(text, chunk_size=1000, overlap=200):
    """
    Simple chunking without complex processing.
    Just slice the text with overlap.
    """
    if not text:
        return []

    chunks = []
    text_length = len(text)
    chunk_index = 0
    position = 0

    while position < text_length:
        # Get chunk
        end_position = min(position + chunk_size, text_length)
        chunk_text = text[position:end_position]

        # Create chunk dict
        chunks.append({
            'text': chunk_text,
            'chunk_index': chunk_index,
            'chunk_type': 'text',
            'section': 'full_text',
            'start_pos': position,
            'end_pos': end_position
        })

        # Move to next chunk with overlap
        position = position + chunk_size - overlap
        chunk_index += 1

    return chunks