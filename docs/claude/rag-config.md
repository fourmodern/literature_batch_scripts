## RAG System Configuration

**Vector Database Options**
- **ChromaDB**: Local storage, no API costs, good for < 10k papers
- **Pinecone**: Cloud-based, scales to millions of papers, requires API key

**Embedding Models**
- **BGE-M3**: Fast multilingual embeddings, recommended for Korean+English papers
- **sentence-transformers**: Fast, multilingual, runs locally
- **OpenAI embeddings**: Higher quality, API costs apply
- **CLIP**: For multimodal (text + image) search

**Chunking Strategies**
- Section-based: Preserves paper structure (Abstract, Methods, etc.)
- Paragraph-based: Natural semantic units
- Semantic chunking: Uses `semantic_chunker.py` for intelligent boundaries
- Enhanced chunking: Uses `enhanced_text_chunker.py` with overlap
- Simple chunking: Uses `simple_chunker.py` for straightforward splits
- Configurable chunk sizes: 300-1000 tokens

**Search Performance**
- ChromaDB: ~100ms for 10k papers
- Pinecone: ~50ms regardless of scale
- Multimodal search: ~200ms with CLIP embeddings
- Hybrid search: Combines text and image similarity for best results

**Migration and Management**
- Use `migrate_to_pinecone.py` to migrate from ChromaDB to Pinecone
- Use `migrate_improved_to_pinecone.py` for safer migration with validation
- Use `check_pinecone_status.py` to verify Pinecone index health
- Use `compare_collections.py` to compare different vector databases
