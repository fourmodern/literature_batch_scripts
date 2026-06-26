"""
Image Analyzer using Gemini Vision API
Gemini를 사용한 학술 이미지 분석 및 벡터화
"""

import os
import base64
from typing import List, Dict, Optional
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


class ImageAnalyzer:
    """
    Analyze academic paper images using Gemini Vision API.
    Creates text descriptions that can be vectorized.
    """

    def __init__(self, model_name: str = "gemini-2.0-flash"):
        """
        Initialize the image analyzer.

        Args:
            model_name: Gemini model to use (2.0-flash for better safety handling)
        """
        # Configure Gemini API
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("⚠️ GEMINI_API_KEY not found. Image analysis will be skipped.")
            self.enabled = False
            return

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.enabled = True

        # Safety settings for academic content
        self.safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]

        print(f"✅ Gemini Vision API initialized with {model_name}")

    def analyze_images(self,
                      images: List[Dict],
                      metadata: Dict = None,
                      featured_image: Dict = None,
                      max_images: int = 10) -> List[Dict]:
        """
        Analyze images and create text descriptions for vectorization.

        Args:
            images: List of image dictionaries from extract_images_from_pdf
            metadata: Paper metadata
            featured_image: Featured image if identified
            max_images: Maximum number of images to analyze

        Returns:
            List of image analysis chunks
        """
        if not self.enabled or not images:
            return []

        chunks = []

        # Prioritize featured image
        if featured_image:
            images_to_analyze = [featured_image]
            remaining = [img for img in images if img != featured_image]
            images_to_analyze.extend(remaining[:max_images - 1])
        else:
            images_to_analyze = images[:max_images]

        print(f"  🖼️ Analyzing {len(images_to_analyze)} images...")

        for i, img_info in enumerate(images_to_analyze):
            try:
                # Analyze single image
                analysis = self._analyze_single_image(img_info, i + 1)

                if analysis:
                    # Create chunk for this image analysis
                    chunk = {
                        'text': analysis,
                        'chunk_type': 'image_analysis',
                        'image_index': i,
                        'image_path': img_info.get('path', ''),
                        'image_filename': img_info.get('filename', ''),
                        'page': img_info.get('page', 0),
                        'is_featured': img_info == featured_image,
                        'char_count': len(analysis),
                        'word_count': len(analysis.split())
                    }

                    # Add metadata if provided
                    if metadata:
                        chunk['metadata'] = metadata

                    # Add image dimensions and size
                    chunk['image_width'] = img_info.get('width', 0)
                    chunk['image_height'] = img_info.get('height', 0)
                    chunk['image_size_bytes'] = img_info.get('size_bytes', 0)

                    chunks.append(chunk)

                    print(f"    ✓ Image {i + 1} analyzed ({len(analysis)} chars)")

            except Exception as e:
                print(f"    ✗ Failed to analyze image {i + 1}: {e}")
                continue

        return chunks

    def _analyze_single_image(self,
                            img_info: Dict,
                            image_number: int) -> Optional[str]:
        """
        Analyze a single image using Gemini.

        Args:
            img_info: Image information dictionary
            image_number: Image number for reference

        Returns:
            Text description of the image
        """
        image_path = img_info.get('path', '')
        if not os.path.exists(image_path):
            return None

        try:
            # Read image file
            with open(image_path, 'rb') as f:
                image_data = f.read()

            # Create prompt for academic image analysis
            prompt = self._create_analysis_prompt(img_info, image_number)

            # Prepare content for Gemini
            content = [
                prompt,
                {
                    'mime_type': 'image/png',
                    'data': image_data
                }
            ]

            # Generate analysis
            response = self.model.generate_content(
                content,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.3,
                ),
                safety_settings=self.safety_settings
            )

            # Check if response was blocked
            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = response.candidates[0].finish_reason
                if finish_reason == 2:  # SAFETY
                    print(f"      ⚠️ Gemini blocked image (safety filter)")
                    return None
                elif finish_reason == 3:  # RECITATION
                    print(f"      ⚠️ Gemini blocked image (recitation)")
                    return None
                elif finish_reason == 4:  # OTHER
                    print(f"      ⚠️ Gemini blocked image (other reason)")
                    return None

            # Try to get text response
            if hasattr(response, 'text') and response.text:
                # Format the analysis
                analysis = self._format_analysis(response.text, img_info, image_number)
                return analysis
            else:
                print(f"      ⚠️ No text in Gemini response")
                return None

        except Exception as e:
            # Don't show confusing error message for safety blocks
            if "finish_reason" in str(e) and "is 2" in str(e):
                print(f"      ⚠️ Gemini blocked image (safety filter)")
            else:
                print(f"      Error in Gemini analysis: {e}")
            return None

    def _create_analysis_prompt(self, img_info: Dict, image_number: int) -> str:
        """
        Create a prompt for image analysis.

        Args:
            img_info: Image information
            image_number: Image number

        Returns:
            Analysis prompt
        """
        page = img_info.get('page', 0)

        prompt = f"""You are analyzing Figure {image_number} from page {page} of an academic paper.

Please provide a detailed but concise description of this image, focusing on:
1. Type of visualization (graph, chart, diagram, microscopy image, etc.)
2. Main elements and components visible
3. Key data or information presented
4. Any text, labels, or legends visible
5. Scientific significance or purpose

Format your response as a single paragraph description suitable for text-based search.
Be specific about quantitative information if visible.
Describe colors, patterns, and structures that are scientifically relevant.

Important: Only describe what you can actually see in the image. Do not make assumptions."""

        return prompt

    def _format_analysis(self,
                        raw_analysis: str,
                        img_info: Dict,
                        image_number: int) -> str:
        """
        Format the analysis for vectorization.

        Args:
            raw_analysis: Raw analysis from Gemini
            img_info: Image information
            image_number: Image number

        Returns:
            Formatted analysis text
        """
        # Clean up the analysis
        analysis = raw_analysis.strip()

        # Add context prefix
        page = img_info.get('page', 0)
        prefix = f"[Image {image_number} from page {page}] "

        # Combine with analysis
        formatted = prefix + analysis

        # Add caption if available
        if img_info.get('caption'):
            caption = img_info['caption']
            if isinstance(caption, dict):
                caption_text = caption.get('text', '')
            else:
                caption_text = str(caption)

            if caption_text:
                formatted += f" [Original caption: {caption_text[:200]}]"

        return formatted

    def analyze_with_context(self,
                           img_info: Dict,
                           surrounding_text: str,
                           metadata: Dict = None) -> Optional[str]:
        """
        Analyze an image with surrounding text context.

        Args:
            img_info: Image information
            surrounding_text: Text around the image reference
            metadata: Paper metadata

        Returns:
            Contextual analysis of the image
        """
        if not self.enabled:
            return None

        image_path = img_info.get('path', '')
        if not os.path.exists(image_path):
            return None

        try:
            # Read image file
            with open(image_path, 'rb') as f:
                image_data = f.read()

            # Create contextual prompt
            prompt = f"""Analyze this figure from an academic paper.

Context from the paper: {surrounding_text[:500]}

Please describe:
1. What this image shows
2. How it relates to the surrounding text
3. Key findings or data visible
4. Scientific significance

Be specific and factual. Focus on what is actually visible."""

            # Generate analysis with context
            content = [
                prompt,
                {
                    'mime_type': 'image/png',
                    'data': image_data
                }
            ]

            response = self.model.generate_content(
                content,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=400,
                    temperature=0.3,
                ),
                safety_settings=self.safety_settings
            )

            if response.text:
                return response.text.strip()

        except Exception as e:
            print(f"    Error in contextual analysis: {e}")

        return None

    def batch_analyze_images(self,
                           image_paths: List[str],
                           batch_size: int = 5) -> List[str]:
        """
        Analyze multiple images in batches.

        Args:
            image_paths: List of image file paths
            batch_size: Number of images per batch

        Returns:
            List of analysis texts
        """
        if not self.enabled:
            return []

        analyses = []

        for i in range(0, len(image_paths), batch_size):
            batch = image_paths[i:i + batch_size]

            for path in batch:
                img_info = {
                    'path': path,
                    'filename': os.path.basename(path),
                    'page': 0  # Unknown page
                }

                analysis = self._analyze_single_image(img_info, len(analyses) + 1)
                if analysis:
                    analyses.append(analysis)

        return analyses

    def create_multimodal_chunk(self,
                              img_info: Dict,
                              analysis: str,
                              caption: Optional[str] = None,
                              metadata: Dict = None) -> Dict:
        """
        Create a comprehensive multimodal chunk combining image analysis and caption.

        Args:
            img_info: Image information
            analysis: Gemini analysis text
            caption: Original caption if available
            metadata: Paper metadata

        Returns:
            Multimodal chunk dictionary
        """
        # Combine all text elements
        text_parts = []

        # Add caption if available
        if caption:
            text_parts.append(f"Caption: {caption}")

        # Add analysis
        text_parts.append(f"Visual Analysis: {analysis}")

        # Combine into single text
        combined_text = " | ".join(text_parts)

        # Create chunk
        chunk = {
            'text': combined_text,
            'chunk_type': 'multimodal_image',
            'image_path': img_info.get('path', ''),
            'image_filename': img_info.get('filename', ''),
            'page': img_info.get('page', 0),
            'has_caption': caption is not None,
            'has_analysis': True,
            'char_count': len(combined_text),
            'word_count': len(combined_text.split())
        }

        # Add metadata
        if metadata:
            chunk['metadata'] = metadata

        # Add image properties
        chunk['image_width'] = img_info.get('width', 0)
        chunk['image_height'] = img_info.get('height', 0)

        return chunk


def test_image_analyzer():
    """Test the image analyzer with a sample image."""
    import requests
    from PIL import Image
    from io import BytesIO

    # Create test image (or use existing)
    test_image_path = "./test_image.png"

    if not os.path.exists(test_image_path):
        # Create a simple test image
        print("Creating test image...")
        img = Image.new('RGB', (400, 300), color='white')
        img.save(test_image_path)

    # Initialize analyzer
    analyzer = ImageAnalyzer()

    if not analyzer.enabled:
        print("Gemini API not configured. Skipping test.")
        return

    # Test single image analysis
    img_info = {
        'path': test_image_path,
        'filename': 'test_image.png',
        'page': 1,
        'width': 400,
        'height': 300
    }

    print("Testing single image analysis:")
    print("-" * 50)

    analysis = analyzer._analyze_single_image(img_info, 1)
    if analysis:
        print(f"Analysis: {analysis}")
    else:
        print("No analysis generated")

    # Test chunk creation
    print("\nTesting multimodal chunk creation:")
    print("-" * 50)

    chunk = analyzer.create_multimodal_chunk(
        img_info,
        analysis or "Test analysis",
        caption="Test figure showing example data",
        metadata={'paper_id': 'test123'}
    )

    for key, value in chunk.items():
        if key != 'text':
            print(f"{key}: {value}")
    print(f"text: {chunk['text'][:200]}...")

    # Clean up
    if os.path.exists(test_image_path):
        os.remove(test_image_path)


if __name__ == "__main__":
    test_image_analyzer()