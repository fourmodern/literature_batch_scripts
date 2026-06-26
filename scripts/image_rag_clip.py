"""
Image RAG with CLIP Model
CLIP을 사용한 이미지 전용 RAG 시스템
True multimodal embeddings for cross-modal search
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from tqdm import tqdm
from PIL import Image
import hashlib

# Add script directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import custom modules
from text_extractor import extract_text_and_images

# Environment variables
from dotenv import load_dotenv
load_dotenv()

# Try to import CLIP model
try:
    from sentence_transformers import SentenceTransformer
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    print("⚠️ Sentence Transformers not available. Install with: pip install sentence-transformers")

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


class ImageRAGCLIP:
    """
    Image-only RAG system using CLIP model.
    Supports true pixel-level embeddings and cross-modal search.
    """

    def __init__(self,
                 db_type: str = "chroma",
                 db_path: str = "./image_rag_clip",
                 model_name: str = "clip-ViT-B-32",
                 max_images_per_paper: int = 20):
        """
        Initialize Image RAG with CLIP.

        Args:
            db_type: "chroma" or "pinecone"
            db_path: Path for ChromaDB storage
            model_name: CLIP model variant to use
            max_images_per_paper: Maximum images to process per paper
        """
        self.db_type = db_type
        self.db_path = db_path
        self.max_images_per_paper = max_images_per_paper

        # Initialize CLIP model
        if CLIP_AVAILABLE:
            print(f"🚀 Loading CLIP model: {model_name}...")
            self.model = SentenceTransformer(model_name)
            # Get embedding dimension - CLIP ViT-B-32 is 512
            try:
                self.embedding_dim = self.model.get_sentence_embedding_dimension()
            except:
                # Fallback for CLIP models
                if "clip-ViT-B-32" in model_name:
                    self.embedding_dim = 512
                elif "clip-ViT-L-14" in model_name:
                    self.embedding_dim = 768
                else:
                    self.embedding_dim = 512  # Default CLIP dimension

            if self.embedding_dim is None:
                self.embedding_dim = 512  # Default for CLIP ViT-B-32

            print(f"✅ CLIP loaded successfully")
            print(f"   - Model: {model_name}")
            print(f"   - Embedding dimension: {self.embedding_dim}")
            print(f"   - Supports: Image→Text and Text→Image search")
        else:
            raise ValueError("CLIP model not available. Please install sentence-transformers.")

        # Initialize vector database
        self._init_vector_db()

        # Track processed papers
        self.processed_papers = set()
        self._load_processed_papers()

        # Image processing settings
        self.supported_formats = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}

    def _init_vector_db(self):
        """Initialize the vector database (ChromaDB or Pinecone)."""
        if self.db_type == "chroma" and CHROMA_AVAILABLE:
            # Initialize ChromaDB
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(anonymized_telemetry=False)
            )

            # Create or get collection
            collection_name = "image_papers_clip"
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
            index_name = "image-clip"

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
        Process images from a paper and add to vector database.

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
            'images': 0,
            'embeddings': 0,
            'errors': []
        }

        try:
            print(f"\n🖼️ Processing images from: {paper_id}")

            # Create output directory for images
            image_dir = os.path.join(self.db_path, "extracted_images", paper_id)
            os.makedirs(image_dir, exist_ok=True)

            # Extract images from PDF
            print("  📖 Extracting images from PDF...")
            text, images, captions, featured_image = extract_text_and_images(
                pdf_path,
                output_dir=image_dir,
                max_pages=None
            )

            if not images:
                print("  ⚠️ No images found in PDF")
                self._save_processed_paper(paper_id)
                return stats

            print(f"  ✓ Extracted {len(images)} images")

            # Limit number of images
            if len(images) > self.max_images_per_paper:
                # Prioritize featured image and early pages
                images = self._prioritize_images(images, featured_image, self.max_images_per_paper)
                print(f"  ✓ Limited to {len(images)} most important images")

            # Match images with captions
            image_caption_map = self._match_images_captions(images, captions)
            print(f"  ✓ Matched {len(image_caption_map)} images with captions")

            # Process each image
            image_data = []
            for i, img_info in enumerate(images):
                img_path = os.path.join(image_dir, img_info['filename'])

                if not os.path.exists(img_path):
                    print(f"  ⚠️ Image file not found: {img_path}")
                    continue

                # Get caption if available
                caption = image_caption_map.get(img_info['filename'], {})

                # Create image metadata
                img_metadata = {
                    'paper_id': paper_id,
                    'image_id': f"{paper_id}#I{i:03d}",
                    'filename': img_info['filename'],
                    'path': img_path,
                    'page': img_info.get('page', 0),
                    'width': img_info.get('width', 0),
                    'height': img_info.get('height', 0),
                    'is_featured': img_info.get('filename') == featured_image.get('filename') if featured_image else False,
                    'caption_text': caption.get('text', ''),
                    'caption_id': f"{paper_id}#C{i:03d}" if caption else None
                }

                # Add paper metadata if provided
                if metadata:
                    img_metadata['paper_title'] = metadata.get('title', '')
                    img_metadata['paper_year'] = metadata.get('year', 0)
                    img_metadata['paper_authors'] = metadata.get('authors', '')

                image_data.append(img_metadata)

            stats['images'] = len(image_data)

            # Generate embeddings for images
            print(f"  🔢 Generating CLIP embeddings for {len(image_data)} images...")
            embeddings = self._generate_image_embeddings(image_data)
            stats['embeddings'] = len(embeddings)
            print(f"  ✓ Generated {len(embeddings)} embeddings")

            # Store in vector database
            self._store_images(image_data, embeddings)

            # Mark as processed
            self._save_processed_paper(paper_id)
            print(f"  ✅ Successfully processed: {stats['images']} images")

        except Exception as e:
            print(f"  ❌ Error processing {paper_id}: {str(e)}")
            stats['errors'].append(str(e))
            stats['status'] = 'error'

        return stats

    def _prioritize_images(self,
                          images: List[Dict],
                          featured_image: Optional[Dict],
                          max_count: int) -> List[Dict]:
        """
        Prioritize images based on importance.

        Args:
            images: List of all images
            featured_image: Featured image if identified
            max_count: Maximum number of images to keep

        Returns:
            Prioritized list of images
        """
        prioritized = []

        # Add featured image first
        if featured_image:
            for img in images:
                if img.get('filename') == featured_image.get('filename'):
                    prioritized.append(img)
                    break

        # Add large images (likely to be important figures)
        large_images = sorted(
            images,
            key=lambda x: x.get('width', 0) * x.get('height', 0),
            reverse=True
        )

        for img in large_images:
            if img not in prioritized:
                prioritized.append(img)
                if len(prioritized) >= max_count:
                    break

        # If still room, add images from early pages
        if len(prioritized) < max_count:
            early_images = sorted(images, key=lambda x: x.get('page', 999))
            for img in early_images:
                if img not in prioritized:
                    prioritized.append(img)
                    if len(prioritized) >= max_count:
                        break

        return prioritized[:max_count]

    def _match_images_captions(self,
                              images: List[Dict],
                              captions: List[Dict]) -> Dict:
        """
        Match images with their captions based on page and proximity.

        Args:
            images: List of image information
            captions: List of caption information

        Returns:
            Dictionary mapping image filename to caption
        """
        image_caption_map = {}

        for img in images:
            img_page = img.get('page', 0)
            img_filename = img.get('filename', '')

            # Find captions on the same page
            page_captions = [c for c in captions if c.get('page', -1) == img_page]

            if page_captions:
                # Simple heuristic: assign first caption on page to image
                # More sophisticated matching could use position info
                image_caption_map[img_filename] = page_captions[0]

        return image_caption_map

    def _generate_image_embeddings(self, image_data: List[Dict]) -> np.ndarray:
        """
        Generate CLIP embeddings for images.

        Args:
            image_data: List of image metadata with paths

        Returns:
            Numpy array of embeddings
        """
        embeddings = []

        for img_info in image_data:
            img_path = img_info['path']

            try:
                # Load and encode image
                image = Image.open(img_path).convert('RGB')

                # Resize if too large (CLIP typically uses 224x224)
                if image.width > 1024 or image.height > 1024:
                    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

                # Generate embedding
                embedding = self.model.encode(image)
                embeddings.append(embedding)

            except Exception as e:
                print(f"  ⚠️ Failed to encode image {img_path}: {e}")
                # Use zero embedding as fallback
                embeddings.append(np.zeros(self.embedding_dim))

        return np.array(embeddings)

    def _store_images(self, image_data: List[Dict], embeddings: np.ndarray):
        """
        Store image embeddings and metadata in vector database.

        Args:
            image_data: List of image metadata
            embeddings: Numpy array of embeddings
        """
        if self.db_type == "chroma":
            # Prepare data for ChromaDB
            ids = []
            documents = []
            metadatas = []

            for img_info, embedding in zip(image_data, embeddings):
                # Use image ID as unique identifier
                ids.append(img_info['image_id'])

                # Use caption as document text, or create description
                doc_text = img_info['caption_text'] if img_info['caption_text'] else \
                          f"Image from page {img_info['page']} of {img_info['paper_id']}"
                documents.append(doc_text)

                # Clean metadata for storage
                metadata = {
                    'paper_id': img_info['paper_id'],
                    'image_id': img_info['image_id'],
                    'filename': img_info['filename'],
                    'page': img_info['page'],
                    'width': img_info['width'],
                    'height': img_info['height'],
                    'is_featured': img_info['is_featured'],
                    'caption_id': img_info.get('caption_id', ''),
                    'paper_title': img_info.get('paper_title', ''),
                    'paper_year': img_info.get('paper_year', 0)
                }
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
            for img_info, embedding in zip(image_data, embeddings):
                metadata = {
                    'paper_id': img_info['paper_id'],
                    'filename': img_info['filename'],
                    'page': img_info['page'],
                    'is_featured': img_info['is_featured'],
                    'caption': img_info['caption_text'][:500] if img_info['caption_text'] else ''
                }

                vectors.append({
                    "id": img_info['image_id'],
                    "values": embedding.tolist(),
                    "metadata": metadata
                })

            # Upload in batches
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i+batch_size]
                self.pinecone_index.upsert(vectors=batch)

    def search_by_text(self,
                      query: str,
                      k: int = 10,
                      filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        Search images using text query (text→image search).

        Args:
            query: Text query
            k: Number of results
            filter_dict: Optional metadata filters

        Returns:
            List of similar images
        """
        # Generate text embedding using CLIP
        query_embedding = self.model.encode(query)

        return self._search_by_embedding(query_embedding, k, filter_dict)

    def search_by_image(self,
                       image_path: str,
                       k: int = 10,
                       filter_dict: Optional[Dict] = None) -> List[Dict]:
        """
        Search similar images using an image query (image→image search).

        Args:
            image_path: Path to query image
            k: Number of results
            filter_dict: Optional metadata filters

        Returns:
            List of similar images
        """
        # Load and encode query image
        try:
            image = Image.open(image_path).convert('RGB')
            if image.width > 1024 or image.height > 1024:
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

            query_embedding = self.model.encode(image)
        except Exception as e:
            print(f"Error loading query image: {e}")
            return []

        return self._search_by_embedding(query_embedding, k, filter_dict)

    def _search_by_embedding(self,
                            query_embedding: np.ndarray,
                            k: int,
                            filter_dict: Optional[Dict]) -> List[Dict]:
        """
        Search using an embedding vector.

        Args:
            query_embedding: Query embedding
            k: Number of results
            filter_dict: Optional filters

        Returns:
            List of search results
        """
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
                result = {
                    'id': results['ids'][0][i],
                    'caption': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': 1 - results['distances'][0][i]
                }

                # Add image path
                paper_id = result['metadata']['paper_id']
                filename = result['metadata']['filename']
                result['image_path'] = os.path.join(
                    self.db_path, "extracted_images", paper_id, filename
                )

                formatted_results.append(result)

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
                result = {
                    'id': match['id'],
                    'caption': match['metadata'].get('caption', ''),
                    'metadata': match['metadata'],
                    'score': match['score']
                }

                # Add image path
                paper_id = match['metadata']['paper_id']
                filename = match['metadata']['filename']
                result['image_path'] = os.path.join(
                    self.db_path, "extracted_images", paper_id, filename
                )

                formatted_results.append(result)

            return formatted_results

        return []

    def get_paper_images(self, paper_id: str) -> List[Dict]:
        """
        Get all images from a specific paper.

        Args:
            paper_id: Paper identifier

        Returns:
            List of image information
        """
        filter_dict = {'paper_id': paper_id}
        results = self.search_by_text("", k=100, filter_dict=filter_dict)

        # Sort by page number
        results.sort(key=lambda x: x['metadata'].get('page', 0))

        return results


def main():
    """Main function for testing and batch processing."""
    import argparse

    parser = argparse.ArgumentParser(description="Image RAG with CLIP")
    parser.add_argument("--pdf", type=str, help="Single PDF to process")
    parser.add_argument("--batch", type=str, help="Batch JSON file")
    parser.add_argument("--search-text", type=str, help="Search by text query")
    parser.add_argument("--search-image", type=str, help="Search by image path")
    parser.add_argument("--db", type=str, default="chroma", choices=["chroma", "pinecone"])
    parser.add_argument("--k", type=int, default=10, help="Number of search results")

    args = parser.parse_args()

    # Initialize Image RAG
    rag = ImageRAGCLIP(db_type=args.db)

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

    elif args.search_text:
        # Search by text
        results = rag.search_by_text(args.search_text, k=args.k)
        print(f"\nFound {len(results)} images for '{args.search_text}':\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. Score: {result['score']:.3f}")
            print(f"   ID: {result['id']}")
            print(f"   Caption: {result['caption'][:200]}...")
            print(f"   Path: {result['image_path']}")
            print(f"   Metadata: {result['metadata']}")
            print()

    elif args.search_image:
        # Search by image
        results = rag.search_by_image(args.search_image, k=args.k)
        print(f"\nFound {len(results)} similar images:\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. Score: {result['score']:.3f}")
            print(f"   ID: {result['id']}")
            print(f"   Path: {result['image_path']}")
            print(f"   Metadata: {result['metadata']}")
            print()


if __name__ == "__main__":
    main()