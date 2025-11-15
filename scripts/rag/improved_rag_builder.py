"""
Improved RAG Builder with Enhanced Chunking and Multimodal Support
개선된 RAG 빌더: 1000자/200자 청킹, Figure/Table 캡션, 이미지 분석 통합
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import numpy as np
from tqdm import tqdm

# 환경 변수 로드
from dotenv import load_dotenv
load_dotenv()

# Import custom modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from text_extractor import extract_text_and_images, extract_figures_and_tables
from enhanced_text_chunker import EnhancedTextChunker
from simple_chunker import simple_chunk_text
from caption_vectorizer import CaptionVectorizer
from image_analyzer import ImageAnalyzer

# Vector DB imports
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
    print("⚠️ Pinecone not available. Install with: pip install pinecone")

# Embedding model imports
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("⚠️ Sentence Transformers not available. Install with: pip install sentence-transformers")


class ImprovedRAGBuilder:
    """
    Enhanced RAG Builder with:
    - Character-based chunking (1000 chars with 200 overlap)
    - Separate vectorization for figure/table captions
    - Image analysis with Gemini Vision
    - Rich metadata support
    """

    def __init__(self,
                 db_type: str = "chroma",
                 embedding_model: str = "sentence-transformers",
                 chunk_size: int = 1000,
                 overlap: int = 200):
        """
        Initialize the improved RAG builder.

        Args:
            db_type: "chroma" or "pinecone"
            embedding_model: "sentence-transformers" or "openai"
            chunk_size: Number of characters per chunk (default: 1000)
            overlap: Number of overlapping characters (default: 200)
        """
        self.db_type = db_type
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.overlap = overlap

        # Initialize components
        self.text_chunker = EnhancedTextChunker(chunk_size, overlap)
        self.caption_vectorizer = CaptionVectorizer()
        self.image_analyzer = ImageAnalyzer(model_name="gemini-2.0-flash")

        # Initialize embedding model
        if embedding_model == "sentence-transformers" and SENTENCE_TRANSFORMERS_AVAILABLE:
            # Use CLIP multilingual model for text + image support
            # This model supports both text and image embeddings with multilingual capabilities
            self.embedder = SentenceTransformer('clip-ViT-B-32-multilingual-v1')
            self.embedding_dim = 512  # CLIP uses 512 dimensions
            print("✅ Loaded CLIP multilingual model (text + image support)")
        else:
            raise ValueError(f"Embedding model {embedding_model} not available")

        # Initialize vector database
        self._init_vector_db()

        # Track processed papers
        self.processed_papers = set()
        self._load_processed_papers()

    def _init_vector_db(self):
        """Initialize the vector database (ChromaDB or Pinecone)."""
        if self.db_type == "chroma" and CHROMA_AVAILABLE:
            # ChromaDB setup
            self.client = chromadb.PersistentClient(
                path="./improved_vector_db",
                settings=Settings(anonymized_telemetry=False)
            )

            # Create or get collection with timestamp for uniqueness
            from datetime import datetime
            collection_name = f"rag_papers_{datetime.now().strftime('%Y%m%d')}"

            # Try to create new collection
            try:
                self.collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                print(f"✅ Created new ChromaDB collection: {collection_name}")
            except:
                # If exists, delete and recreate for fresh start
                try:
                    self.client.delete_collection(collection_name)
                    self.collection = self.client.create_collection(
                        name=collection_name,
                        metadata={"hnsw:space": "cosine"}
                    )
                    print(f"✅ Recreated ChromaDB collection: {collection_name}")
                except:
                    self.collection = self.client.get_collection(collection_name)
                    print(f"✅ Using existing ChromaDB collection: {collection_name}")

        elif self.db_type == "pinecone" and PINECONE_AVAILABLE:
            # Pinecone setup
            api_key = os.getenv("PINECONE_API_KEY")
            if not api_key:
                raise ValueError("PINECONE_API_KEY not found in environment variables")

            pc = Pinecone(api_key=api_key)

            # Create index name with date for uniqueness
            from datetime import datetime
            index_name = f"rag-papers-{datetime.now().strftime('%Y%m%d')}"

            # Delete old index if exists and create new one
            existing_indexes = pc.list_indexes()
            if any(idx.name == index_name for idx in existing_indexes):
                print(f"🗑️ Deleting existing Pinecone index: {index_name}")
                pc.delete_index(index_name)
                # Wait a moment for deletion to complete
                import time
                time.sleep(5)

            # Create new index
            print(f"📊 Creating new Pinecone index: {index_name}")
            pc.create_index(
                name=index_name,
                dimension=self.embedding_dim,
                metric='cosine',
                spec=ServerlessSpec(cloud='aws', region='us-east-1')
            )
            print(f"✅ Created Pinecone index: {index_name}")

            # Wait for index to be ready
            import time
            time.sleep(10)

            self.pinecone_index = pc.Index(index_name)
            print(f"✅ Connected to Pinecone index: {index_name}")
        else:
            raise ValueError(f"Database type {self.db_type} not available")

    def _load_processed_papers(self):
        """Load list of already processed papers."""
        progress_file = Path("./improved_vector_db/processed_papers.json")
        if progress_file.exists():
            with open(progress_file, 'r') as f:
                self.processed_papers = set(json.load(f))
            print(f"📚 Loaded {len(self.processed_papers)} processed papers")

    def _save_processed_papers(self):
        """Save list of processed papers."""
        progress_file = Path("./improved_vector_db/processed_papers.json")
        progress_file.parent.mkdir(exist_ok=True)
        with open(progress_file, 'w') as f:
            json.dump(list(self.processed_papers), f)

    def process_paper(self,
                     pdf_path: str,
                     paper_id: str,
                     metadata: Dict) -> Dict:
        """
        Process a single paper with all enhancements.

        Args:
            pdf_path: Path to the PDF file
            paper_id: Unique identifier for the paper
            metadata: Paper metadata (title, authors, year, etc.)

        Returns:
            Processing statistics
        """
        if paper_id in self.processed_papers:
            print(f"⏭️ Skipping already processed paper: {paper_id}")
            return {"status": "skipped"}

        print(f"\n📄 Processing paper: {metadata.get('title', paper_id)}")

        print(f"  🔍 Starting to process paper: {paper_id}")
        print(f"     PDF path: {pdf_path}")

        stats = {
            "paper_id": paper_id,
            "text_chunks": 0,
            "caption_chunks": 0,
            "image_chunks": 0,
            "total_chunks": 0
        }

        try:
            # 1. Extract text, images, and captions from PDF
            print("  📖 Extracting content from PDF...")
            # Extract with limited pages for speed
            text, images, captions, featured_image = extract_text_and_images(
                pdf_path,
                output_dir=f"./extracted_images/{paper_id}",
                max_pages=20  # Limit to first 20 pages
            )

            # Limit images to 5 for speed
            if len(images) > 5:
                images = images[:5]
                print(f"     Limited to 5 images (from {len(images)} found)")

            # Also extract structured figure/table captions
            print("  📊 Extracting figures and tables...")
            # SLOW - disabled for testing
            # figures, tables = extract_figures_and_tables(pdf_path)
            figures, tables = [], []  # Skip for speed
            print(f"     Skipped figure/table extraction for speed")

            # 2. Create text chunks (1000 chars with 200 overlap)
            print(f"  ✂️ Creating text chunks ({self.chunk_size} chars, {self.overlap} overlap)...")
            # SLOW chunker - replaced with simple version
            # text_chunks = self.text_chunker.chunk_text(text, metadata)
            text_chunks = simple_chunk_text(text, self.chunk_size, self.overlap)
            stats["text_chunks"] = len(text_chunks)

            # 3. Create caption chunks
            print(f"  📝 Processing {len(figures)} figures and {len(tables)} tables...")
            caption_chunks = self.caption_vectorizer.create_caption_chunks(
                figures, tables, captions, metadata
            )
            stats["caption_chunks"] = len(caption_chunks)

            # 4. Analyze images with Gemini (if available)
            image_embeddings = []
            if images and len(images) > 0:
                print(f"  🖼️ Analyzing {len(images)} images with Gemini...")
                image_chunks = self.image_analyzer.analyze_images(
                    images, metadata, featured_image
                )
                stats["image_chunks"] = len(image_chunks)

                # Generate image embeddings using CLIP
                print(f"  🎨 Generating image embeddings with CLIP...")
                image_paths = [img.get('path', '') for img in images if img.get('path')]
                if image_paths:
                    image_embeddings = self._generate_image_embeddings(image_paths[:10])  # Limit to 10 images
                    print(f"     Generated {len(image_embeddings)} image embeddings")
            else:
                image_chunks = []

            # 5. Combine all chunks
            all_chunks = text_chunks + caption_chunks + image_chunks
            stats["total_chunks"] = len(all_chunks)

            # 6. Generate embeddings for all chunks
            print(f"  🔢 Generating embeddings for {len(all_chunks)} chunks...")
            chunk_texts = [chunk['text'] for chunk in all_chunks]
            text_embeddings = self._generate_embeddings(chunk_texts)

            # Combine text and image embeddings
            if len(image_embeddings) > 0:
                # Add image embeddings as additional chunks
                for i, img_emb in enumerate(image_embeddings):
                    if i < len(images):
                        image_chunk = {
                            'text': f"[Image {i+1}]",
                            'chunk_type': 'pure_image',
                            'image_path': images[i].get('path', ''),
                            'page': images[i].get('page', 0)
                        }
                        all_chunks.append(image_chunk)

                # Concatenate embeddings
                embeddings = np.vstack([text_embeddings, image_embeddings])
            else:
                embeddings = text_embeddings

            # 7. Store in vector database
            print(f"  💾 Storing in {self.db_type} database...")
            self._store_in_db(all_chunks, embeddings, paper_id)

            # 8. Mark as processed
            self.processed_papers.add(paper_id)
            self._save_processed_papers()

            print(f"  ✅ Successfully processed: {stats['total_chunks']} chunks")
            print(f"     - Text chunks: {stats['text_chunks']}")
            print(f"     - Caption chunks: {stats['caption_chunks']}")
            print(f"     - Image analysis chunks: {stats['image_chunks']}")

            return stats

        except Exception as e:
            print(f"  ❌ Error processing paper: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "error": str(e)}

    def _generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""
        # Batch encode for efficiency
        embeddings = self.embedder.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        return embeddings

    def _generate_image_embeddings(self, image_paths: List[str]) -> np.ndarray:
        """Generate embeddings for images using CLIP."""
        if not image_paths:
            return np.array([])

        # CLIP multilingual model expects image paths, not PIL objects
        # Filter out non-existent paths
        valid_paths = []
        for path in image_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                print(f"    Warning: Image path does not exist: {path}")

        if valid_paths:
            # CLIP multilingual model can encode image paths directly
            embeddings = self.embedder.encode(
                valid_paths,  # Pass paths, not PIL Image objects
                batch_size=8,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            return embeddings
        return np.array([])

    def _store_in_db(self,
                    chunks: List[Dict],
                    embeddings: np.ndarray,
                    paper_id: str):
        """Store chunks and embeddings in the vector database."""
        if self.db_type == "chroma":
            # Prepare data for ChromaDB
            ids = [f"{paper_id}_chunk_{i}" for i in range(len(chunks))]
            documents = [chunk['text'] for chunk in chunks]
            metadatas = []

            for chunk in chunks:
                # Ensure all metadata values are JSON-serializable
                metadata = {
                    'paper_id': paper_id,
                    'chunk_type': chunk.get('chunk_type', 'text'),
                    'chunk_index': chunk.get('chunk_index', 0),
                    'section': chunk.get('section', 'unknown'),
                    'page': chunk.get('page', 0),
                    'char_count': len(chunk['text']),
                }

                # Add paper metadata
                if 'metadata' in chunk:
                    for key, value in chunk['metadata'].items():
                        if key not in metadata and value is not None:
                            # Convert complex types to strings
                            if isinstance(value, (list, dict)):
                                metadata[key] = json.dumps(value)
                            else:
                                metadata[key] = str(value)

                metadatas.append(metadata)

            # Add to ChromaDB
            self.collection.add(
                embeddings=embeddings.tolist(),
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

        elif self.db_type == "pinecone":
            # Prepare data for Pinecone
            vectors = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                vector_id = f"{paper_id}_chunk_{i}"

                # Prepare metadata (Pinecone has size limits)
                metadata = {
                    'paper_id': paper_id,
                    'chunk_type': chunk.get('chunk_type', 'text'),
                    'chunk_index': chunk.get('chunk_index', 0),
                    'text': chunk['text'][:1000],  # Truncate for size limit
                    'section': chunk.get('section', 'unknown'),
                    'page': chunk.get('page', 0)
                }

                vectors.append({
                    "id": vector_id,
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
              filter_dict: Dict = None) -> List[Dict]:
        """
        Search for relevant chunks.

        Args:
            query: Search query
            k: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of relevant chunks with scores
        """
        # Generate query embedding
        query_embedding = self._generate_embeddings([query])[0]

        if self.db_type == "chroma":
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding.tolist()],
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
                    'score': 1 - results['distances'][0][i]  # Convert distance to similarity
                })

            return formatted_results

        elif self.db_type == "pinecone":
            # Search in Pinecone
            results = self.pinecone_index.query(
                vector=query_embedding.tolist(),
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

    parser = argparse.ArgumentParser(description="Improved RAG Builder")
    parser.add_argument("--pdf", type=str, help="Path to single PDF file")
    parser.add_argument("--batch", type=str, help="Path to batch JSON file")
    parser.add_argument("--db", type=str, default="chroma", choices=["chroma", "pinecone"])
    parser.add_argument("--search", type=str, help="Search query to test")

    args = parser.parse_args()

    # Initialize RAG builder
    rag_builder = ImprovedRAGBuilder(db_type=args.db)

    if args.search:
        # Test search
        print(f"\n🔍 Searching for: {args.search}")
        results = rag_builder.search(args.search, k=5)

        for i, result in enumerate(results, 1):
            print(f"\n📄 Result {i} (Score: {result['score']:.3f}):")
            print(f"   Type: {result['metadata'].get('chunk_type', 'unknown')}")
            print(f"   Text: {result['text'][:200]}...")

    elif args.pdf:
        # Process single PDF
        paper_id = Path(args.pdf).stem
        metadata = {
            "title": paper_id,
            "file_path": args.pdf
        }
        rag_builder.process_paper(args.pdf, paper_id, metadata)

    elif args.batch:
        # Process batch of PDFs
        with open(args.batch, 'r') as f:
            batch_data = json.load(f)

        print(f"📚 Processing {len(batch_data)} papers...")

        for idx, item in enumerate(batch_data, 1):
            print(f"\n[{idx}/{len(batch_data)}] Processing paper {item['paper_id']}...")
            rag_builder.process_paper(
                item['pdf_path'],
                item['paper_id'],
                item.get('metadata', {})
            )
            print(f"[{idx}/{len(batch_data)}] ✓ Completed {item['paper_id']}")

        print(f"\n✅ Completed processing {len(batch_data)} papers")


if __name__ == "__main__":
    main()