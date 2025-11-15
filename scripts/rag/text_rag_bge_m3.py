"""
Text RAG with BGE-M3 Model
BGE-M3를 사용한 텍스트 전용 RAG 시스템
Supports Korean, English, and 100+ languages with 8192 token context
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from tqdm import tqdm
import hashlib

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import custom modules
from semantic_chunker import SemanticChunker, HybridChunker
from text_extractor import extract_text_and_images, extract_figures_and_tables

# Environment variables
from dotenv import load_dotenv
load_dotenv()

# Try to import BGE-M3
try:
    from FlagEmbedding import BGEM3FlagModel
    BGE_M3_AVAILABLE = True
except ImportError:
    BGE_M3_AVAILABLE = False
    print("⚠️ BGE-M3 not available. Install with: pip install FlagEmbedding")

# Vector database imports
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("⚠️ ChromaDB not available. Install with: pip install chromadb")

try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    print("⚠️ Pinecone not available. Install with: pip install pinecone-client")


class TextRAGBGEM3:
    """
    Text-only RAG system using BGE-M3 model.
    Optimized for multilingual text retrieval with long context support.
    """

    def __init__(self,
                 db_type: str = "chroma",
                 db_path: str = "./text_rag_bge_m3",
                 chunk_size: int = 1000,
                 overlap: int = 200,
                 use_semantic_chunking: bool = True):
        """
        Initialize Text RAG with BGE-M3.

        Args:
            db_type: "chroma" or "pinecone"
            db_path: Path for ChromaDB storage
            chunk_size: Size of text chunks in characters
            overlap: Overlap between chunks
            use_semantic_chunking: Use semantic chunking vs simple chunking
        """
        self.db_type = db_type
        self.db_path = db_path
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.use_semantic_chunking = use_semantic_chunking

        # Initialize BGE-M3 model
        if BGE_M3_AVAILABLE:
            print("🚀 Loading BGE-M3 model...")
            self.model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
            self.embedding_dim = 1024
            print("✅ BGE-M3 loaded successfully")
            print("   - Supports 100+ languages including Korean and English")
            print("   - Max context: 8192 tokens")
            print("   - Dense + Sparse + ColBERT retrieval modes")
        else:
            raise ValueError("BGE-M3 model not available. Please install FlagEmbedding.")

        # Initialize chunker
        if use_semantic_chunking:
            self.chunker = HybridChunker(
                chunk_size=chunk_size,
                overlap_size=overlap,
                min_chunk_size=100
            )
            print(f"✅ Using semantic chunking with sentence preservation")
        else:
            from simple_chunker import simple_chunk_text
            self.simple_chunk = simple_chunk_text
            print(f"✅ Using simple character-based chunking")

        # Initialize vector database
        self._init_vector_db()

        # Track processed papers
        self.processed_papers = set()
        self._load_processed_papers()

    def _init_vector_db(self):
        """Initialize the vector database (ChromaDB or Pinecone)."""
        if self.db_type == "chroma" and CHROMA_AVAILABLE:
            # Initialize ChromaDB
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(anonymized_telemetry=False)
            )

            # Create or get collection
            collection_name = "text_papers_bge_m3"
            try:
                self.collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                print(f"✅ Created ChromaDB collection: {collection_name}")
            except:
                self.collection = self.client.get_collection(collection_name)
                print(f"✅ Using existing ChromaDB collection: {collection_name}")

        elif self.db_type == "pinecone" and PINECONE_AVAILABLE:
            # Initialize Pinecone
            api_key = os.getenv('PINECONE_API_KEY')
            if not api_key:
                raise ValueError("PINECONE_API_KEY not found in environment")

            pc = Pinecone(api_key=api_key)
            index_name = "text-bge-m3"

            # Create or connect to index
            existing_indexes = pc.list_indexes()
            if not any(idx.name == index_name for idx in existing_indexes):
                pc.create_index(
                    name=index_name,
                    dimension=self.embedding_dim,
                    metric='cosine',
                    spec=ServerlessSpec(cloud='aws', region='us-east-1')
                )
                print(f"✅ Created Pinecone index: {index_name}")
            else:
                print(f"✅ Using existing Pinecone index: {index_name}")

            self.pinecone_index = pc.Index(index_name)
        else:
            raise ValueError(f"Database type {self.db_type} not available")

    def _load_processed_papers(self):
        """Load list of already processed papers."""
        processed_file = os.path.join(self.db_path, "processed_papers.txt")
        if os.path.exists(processed_file):
            with open(processed_file, 'r') as f:
                self.processed_papers = set(line.strip() for line in f)
            print(f"📚 Loaded {len(self.processed_papers)} processed papers")

    def _save_processed_paper(self, paper_id: str):
        """Save paper ID as processed."""
        self.processed_papers.add(paper_id)
        processed_file = os.path.join(self.db_path, "processed_papers.txt")
        os.makedirs(self.db_path, exist_ok=True)
        with open(processed_file, 'a') as f:
            f.write(f"{paper_id}\n")

    def process_paper(self,
                     paper_id: str,
                     pdf_path: str,
                     metadata: Optional[Dict] = None) -> Dict:
        """
        Process a single paper and add to vector database.

        Args:
            paper_id: Unique identifier for the paper
            pdf_path: Path to PDF file
            metadata: Optional paper metadata

        Returns:
            Processing statistics
        """
        if paper_id in self.processed_papers:
            print(f"⏭️ Skipping already processed: {paper_id}")
            return {'status': 'skipped', 'paper_id': paper_id}

        stats = {
            'paper_id': paper_id,
            'chunks': 0,
            'errors': []
        }

        try:
            print(f"\n📄 Processing: {paper_id}")

            # Extract text and metadata
            print("  📖 Extracting text from PDF...")
            text, images, captions, featured_image = extract_text_and_images(
                pdf_path,
                output_dir=None,  # Don't extract images for text-only DB
                max_pages=None
            )

            if not text or len(text) < 100:
                raise ValueError("Insufficient text extracted from PDF")

            print(f"  ✓ Extracted {len(text)} characters")

            # Extract figures and tables for caption text
            figures, tables = extract_figures_and_tables(pdf_path)
            print(f"  ✓ Found {len(figures)} figures and {len(tables)} tables")

            # Create chunks
            if self.use_semantic_chunking:
                chunks = self.chunker.chunk_with_paragraphs(text, metadata)
            else:
                simple_chunks = self.simple_chunk(text, self.chunk_size, self.overlap)
                chunks = [
                    {**chunk, 'metadata': metadata or {}}
                    for chunk in simple_chunks
                ]

            print(f"  ✓ Created {len(chunks)} text chunks")

            # Add caption chunks
            caption_chunks = self._create_caption_chunks(captions, figures, tables, paper_id)
            chunks.extend(caption_chunks)
            print(f"  ✓ Added {len(caption_chunks)} caption chunks")

            # Generate embeddings
            print(f"  🔢 Generating BGE-M3 embeddings...")
            embeddings = self._generate_embeddings(chunks)
            print(f"  ✓ Generated {len(embeddings)} embeddings")

            # Store in vector database
            self._store_chunks(paper_id, chunks, embeddings)
            stats['chunks'] = len(chunks)

            # Mark as processed
            self._save_processed_paper(paper_id)
            print(f"  ✅ Successfully processed: {stats['chunks']} chunks")

        except Exception as e:
            print(f"  ❌ Error processing {paper_id}: {str(e)}")
            stats['errors'].append(str(e))
            stats['status'] = 'error'

        return stats

    def _create_caption_chunks(self,
                              captions: List[Dict],
                              figures: List[Dict],
                              tables: List[Dict],
                              paper_id: str) -> List[Dict]:
        """
        Create chunks from figure and table captions.

        Args:
            captions: Detected captions
            figures: Figure information
            tables: Table information
            paper_id: Paper identifier

        Returns:
            List of caption chunks
        """
        caption_chunks = []

        # Process captions
        for i, caption in enumerate(captions):
            caption_text = caption.get('text', '')
            if caption_text and len(caption_text) > 20:
                caption_chunks.append({
                    'text': caption_text,
                    'chunk_index': f"caption_{i}",
                    'chunk_type': 'caption',
                    'section': 'figure_caption',
                    'metadata': {
                        'paper_id': paper_id,
                        'caption_type': caption.get('type', 'unknown'),
                        'page': caption.get('page', 0)
                    }
                })

        # Process figure descriptions
        for i, figure in enumerate(figures):
            if 'caption' in figure and figure['caption']:
                caption_chunks.append({
                    'text': figure['caption'],
                    'chunk_index': f"figure_{i}",
                    'chunk_type': 'figure_caption',
                    'section': 'figures',
                    'metadata': {
                        'paper_id': paper_id,
                        'figure_id': f"{paper_id}#F{i}",
                        'page': figure.get('page', 0)
                    }
                })

        # Process table descriptions
        for i, table in enumerate(tables):
            if 'caption' in table and table['caption']:
                caption_chunks.append({
                    'text': table['caption'],
                    'chunk_index': f"table_{i}",
                    'chunk_type': 'table_caption',
                    'section': 'tables',
                    'metadata': {
                        'paper_id': paper_id,
                        'table_id': f"{paper_id}#T{i}",
                        'page': table.get('page', 0)
                    }
                })

        return caption_chunks

    def _generate_embeddings(self, chunks: List[Dict]) -> np.ndarray:
        """
        Generate BGE-M3 embeddings for text chunks.

        Args:
            chunks: List of text chunks

        Returns:
            Numpy array of embeddings
        """
        texts = [chunk['text'] for chunk in chunks]

        # Generate dense embeddings
        embeddings = self.model.encode(
            texts,
            batch_size=12,
            max_length=8192,  # BGE-M3 supports up to 8192 tokens
            return_dense=True,
            return_sparse=False,  # Can enable for hybrid search
            return_colbert_vecs=False  # Can enable for ColBERT search
        )['dense_vecs']

        return embeddings

    def _store_chunks(self,
                     paper_id: str,
                     chunks: List[Dict],
                     embeddings: np.ndarray):
        """
        Store chunks and embeddings in vector database.

        Args:
            paper_id: Paper identifier
            chunks: List of text chunks
            embeddings: Numpy array of embeddings
        """
        if self.db_type == "chroma":
            # Prepare data for ChromaDB
            ids = []
            documents = []
            metadatas = []

            for i, chunk in enumerate(chunks):
                chunk_id = f"{paper_id}#T{i:04d}"
                ids.append(chunk_id)
                documents.append(chunk['text'])

                # Prepare metadata
                metadata = {
                    'paper_id': paper_id,
                    'chunk_index': i,
                    'chunk_type': chunk.get('chunk_type', 'text'),
                    'section': chunk.get('section', 'unknown'),
                    'sentence_count': chunk.get('sentence_count', 0)
                }

                # Add custom metadata if provided
                if 'metadata' in chunk and isinstance(chunk['metadata'], dict):
                    metadata.update(chunk['metadata'])

                metadatas.append(metadata)

            # Add to ChromaDB
            self.collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings.tolist(),
                metadatas=metadatas
            )

        elif self.db_type == "pinecone":
            # Prepare data for Pinecone
            vectors = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = f"{paper_id}#T{i:04d}"

                metadata = {
                    'paper_id': paper_id,
                    'chunk_type': chunk.get('chunk_type', 'text'),
                    'section': chunk.get('section', 'unknown'),
                    'text': chunk['text'][:1000]  # Truncate for Pinecone limits
                }

                vectors.append({
                    "id": chunk_id,
                    "values": embedding.tolist(),
                    "metadata": metadata
                })

            # Upload in batches
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i+batch_size]
                self.pinecone_index.upsert(vectors=batch)

    def search(self,
              query: str,
              k: int = 10,
              filter_dict: Optional[Dict] = None,
              use_hybrid: bool = False) -> List[Dict]:
        """
        Search for relevant text chunks.

        Args:
            query: Search query
            k: Number of results
            filter_dict: Optional metadata filters
            use_hybrid: Use hybrid search (dense + sparse)

        Returns:
            List of search results
        """
        # Generate query embedding
        query_embedding = self.model.encode(
            [query],
            batch_size=1,
            max_length=8192,
            return_dense=True,
            return_sparse=use_hybrid,
            return_colbert_vecs=False
        )

        dense_embedding = query_embedding['dense_vecs'][0]

        if self.db_type == "chroma":
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[dense_embedding.tolist()],
                n_results=k,
                where=filter_dict if filter_dict else None
            )

            # Format results
            formatted_results = []
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': 1 - results['distances'][0][i]
                })

            return formatted_results

        elif self.db_type == "pinecone":
            # Search in Pinecone
            results = self.pinecone_index.query(
                vector=dense_embedding.tolist(),
                top_k=k,
                include_metadata=True,
                filter=filter_dict if filter_dict else None
            )

            # Format results
            formatted_results = []
            for match in results['matches']:
                formatted_results.append({
                    'id': match['id'],
                    'text': match['metadata'].get('text', ''),
                    'metadata': match['metadata'],
                    'score': match['score']
                })

            return formatted_results

        return []


def main():
    """Main function for testing and batch processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Text RAG with BGE-M3")
    parser.add_argument("--pdf", type=str, help="Single PDF to process")
    parser.add_argument("--batch", type=str, help="Batch JSON file")
    parser.add_argument("--search", type=str, help="Search query")
    parser.add_argument("--db", type=str, default="chroma", choices=["chroma", "pinecone"])
    parser.add_argument("--k", type=int, default=10, help="Number of search results")

    args = parser.parse_args()

    # Initialize Text RAG
    rag = TextRAGBGEM3(db_type=args.db, use_semantic_chunking=True)

    if args.pdf:
        # Process single PDF
        paper_id = Path(args.pdf).stem
        stats = rag.process_paper(paper_id, args.pdf)
        print(f"\nProcessed: {stats}")

    elif args.batch:
        # Process batch
        with open(args.batch, 'r') as f:
            batch = json.load(f)

        for item in tqdm(batch, desc="Processing papers"):
            paper_id = item.get('paper_id', Path(item['pdf_path']).stem)
            stats = rag.process_paper(paper_id, item['pdf_path'], item.get('metadata'))

    elif args.search:
        # Search
        results = rag.search(args.search, k=args.k)
        print(f"\nFound {len(results)} results for '{args.search}':\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. Score: {result['score']:.3f}")
            print(f"   ID: {result['id']}")
            print(f"   Text: {result['text'][:200]}...")
            print(f"   Metadata: {result['metadata']}")
            print()


if __name__ == "__main__":
    main()