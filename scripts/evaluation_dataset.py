"""
Evaluation Dataset Generator for RAG System
RAG 시스템 성능 평가를 위한 50개 질문-답변 데이터셋 생성
"""

import os
import json
import random
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from datetime import datetime


class EvaluationDatasetGenerator:
    """
    Generate evaluation dataset with 50 question-answer pairs
    for testing RAG system performance.
    """

    def __init__(self, rag_system=None):
        """
        Initialize the evaluation dataset generator.

        Args:
            rag_system: RAG system instance for finding relevant chunks
        """
        self.rag_system = rag_system

        # Question templates by category
        self.question_templates = {
            'definition': [
                "What is the definition of {term} in this paper?",
                "How do the authors define {concept}?",
                "What does {acronym} stand for in this context?",
                "Explain the meaning of {technical_term} as used in this paper."
            ],
            'methodology': [
                "What methodology was used for {experiment}?",
                "Describe the experimental setup for {process}.",
                "What are the key steps in the {method} approach?",
                "How did the authors implement {technique}?",
                "What dataset was used for {evaluation}?"
            ],
            'results': [
                "What are the main results of {experiment}?",
                "What performance improvement was achieved with {method}?",
                "What is the accuracy/precision/recall of {model}?",
                "How does {approach} compare to the baseline?",
                "What are the quantitative findings regarding {metric}?"
            ],
            'figure_table': [
                "What information is shown in Figure {number}?",
                "What does Table {number} demonstrate?",
                "Describe the data presented in Figure {number}.",
                "What are the key findings from Table {number}?",
                "Explain the visualization in Figure {number}."
            ],
            'comparison': [
                "How does {method1} compare to {method2}?",
                "What are the advantages of {approach} over previous work?",
                "What is the difference between {concept1} and {concept2}?",
                "How does this work improve upon {baseline}?",
                "Compare the performance of {model1} and {model2}."
            ],
            'limitations': [
                "What are the limitations of the proposed approach?",
                "What challenges remain unresolved?",
                "What are the potential drawbacks of {method}?",
                "What future work is suggested by the authors?",
                "What assumptions does the {approach} make?"
            ]
        }

    def generate_dataset(self,
                        papers: List[Dict],
                        questions_per_paper: int = 5,
                        total_questions: int = 50) -> List[Dict]:
        """
        Generate evaluation dataset from papers.

        Args:
            papers: List of paper metadata with content
            questions_per_paper: Number of questions per paper
            total_questions: Total number of questions to generate

        Returns:
            List of evaluation questions with answers and metadata
        """
        evaluation_data = []
        papers_to_use = min(len(papers), total_questions // questions_per_paper)

        print(f"Generating {total_questions} evaluation questions from {papers_to_use} papers...")

        for paper in papers[:papers_to_use]:
            paper_questions = self._generate_paper_questions(
                paper,
                questions_per_paper
            )
            evaluation_data.extend(paper_questions)

            if len(evaluation_data) >= total_questions:
                break

        # Trim to exact number if needed
        evaluation_data = evaluation_data[:total_questions]

        print(f"✅ Generated {len(evaluation_data)} evaluation questions")

        return evaluation_data

    def _generate_paper_questions(self,
                                 paper: Dict,
                                 num_questions: int) -> List[Dict]:
        """
        Generate questions for a single paper.

        Args:
            paper: Paper metadata and content
            num_questions: Number of questions to generate

        Returns:
            List of question-answer pairs
        """
        questions = []
        categories = list(self.question_templates.keys())

        # Ensure we have at least one question from each major category
        for i in range(num_questions):
            if i < len(categories):
                category = categories[i]
            else:
                category = random.choice(categories)

            question_data = self._create_question(paper, category)
            if question_data:
                questions.append(question_data)

        return questions

    def _create_question(self,
                       paper: Dict,
                       category: str) -> Optional[Dict]:
        """
        Create a single question-answer pair.

        Args:
            paper: Paper data
            category: Question category

        Returns:
            Question-answer dictionary
        """
        templates = self.question_templates[category]
        template = random.choice(templates)

        # Extract paper elements for template filling
        elements = self._extract_paper_elements(paper)

        # Fill template with actual content
        question = self._fill_template(template, elements, category)

        if not question:
            return None

        # Generate or extract answer
        answer = self._generate_answer(paper, question, category)

        # Find relevant chunks if RAG system is available
        relevant_chunks = []
        if self.rag_system:
            search_results = self.rag_system.search(question, k=5)
            relevant_chunks = [r['id'] for r in search_results]

        return {
            'question_id': self._generate_id(),
            'paper_id': paper.get('paper_id', 'unknown'),
            'paper_title': paper.get('title', 'Unknown Title'),
            'category': category,
            'question': question,
            'answer': answer,
            'relevant_chunks': relevant_chunks,
            'metadata': {
                'template': template,
                'created_at': datetime.now().isoformat(),
                'difficulty': self._estimate_difficulty(category)
            }
        }

    def _extract_paper_elements(self, paper: Dict) -> Dict:
        """
        Extract key elements from paper for question generation.

        Args:
            paper: Paper data

        Returns:
            Dictionary of extracted elements
        """
        elements = {
            'terms': [],
            'concepts': [],
            'methods': [],
            'experiments': [],
            'figures': [],
            'tables': [],
            'models': [],
            'metrics': []
        }

        # Extract from title and abstract
        title = paper.get('title', '')
        abstract = paper.get('abstract', '')

        # Simple extraction (in production, use NLP for better extraction)
        # Extract technical terms (capitalized words, acronyms)
        import re

        # Find acronyms
        acronyms = re.findall(r'\b[A-Z]{2,}\b', title + ' ' + abstract)
        elements['terms'].extend(acronyms)

        # Find figure/table numbers if available
        if 'figures' in paper:
            elements['figures'] = [fig.get('number', str(i+1))
                                  for i, fig in enumerate(paper['figures'][:5])]
        else:
            elements['figures'] = ['1', '2', '3']  # Default figures

        if 'tables' in paper:
            elements['tables'] = [tab.get('number', str(i+1))
                                for i, tab in enumerate(paper['tables'][:3])]
        else:
            elements['tables'] = ['1', '2']  # Default tables

        # Extract method names (words ending in common suffixes)
        method_patterns = [
            r'\b\w+(?:Net|Model|Algorithm|System|Framework|Architecture)\b',
            r'\b\w+(?:-based|-aware|-guided)\b'
        ]
        for pattern in method_patterns:
            methods = re.findall(pattern, title + ' ' + abstract, re.IGNORECASE)
            elements['methods'].extend(methods)

        # Add some common placeholders if empty
        if not elements['terms']:
            elements['terms'] = ['model', 'approach', 'method', 'system']
        if not elements['methods']:
            elements['methods'] = ['proposed method', 'our approach', 'baseline']

        # Add common metrics
        elements['metrics'] = ['accuracy', 'precision', 'recall', 'F1-score', 'performance']

        return elements

    def _fill_template(self,
                      template: str,
                      elements: Dict,
                      category: str) -> str:
        """
        Fill question template with actual content.

        Args:
            template: Question template
            elements: Extracted paper elements
            category: Question category

        Returns:
            Filled question
        """
        import re

        # Find all placeholders in template
        placeholders = re.findall(r'\{(\w+)\}', template)

        filled = template
        for placeholder in placeholders:
            # Map placeholder to element category
            if placeholder in ['term', 'technical_term', 'acronym']:
                replacement = random.choice(elements['terms']) if elements['terms'] else 'concept'
            elif placeholder in ['concept', 'concept1', 'concept2']:
                replacement = random.choice(elements['terms']) if elements['terms'] else 'approach'
            elif placeholder in ['method', 'method1', 'method2', 'approach', 'technique']:
                replacement = random.choice(elements['methods']) if elements['methods'] else 'proposed method'
            elif placeholder in ['experiment', 'process', 'evaluation']:
                replacement = random.choice(['main experiment', 'evaluation', 'validation'])
            elif placeholder == 'number':
                if category == 'figure_table':
                    if 'Figure' in template and elements['figures']:
                        replacement = random.choice(elements['figures'])
                    elif 'Table' in template and elements['tables']:
                        replacement = random.choice(elements['tables'])
                    else:
                        replacement = '1'
                else:
                    replacement = '1'
            elif placeholder in ['model', 'model1', 'model2']:
                replacement = random.choice(elements['methods']) if elements['methods'] else 'model'
            elif placeholder == 'baseline':
                replacement = 'baseline method'
            elif placeholder == 'metric':
                replacement = random.choice(elements['metrics'])
            elif placeholder == 'dataset':
                replacement = 'evaluation dataset'
            else:
                replacement = placeholder

            filled = filled.replace(f'{{{placeholder}}}', replacement)

        return filled

    def _generate_answer(self,
                       paper: Dict,
                       question: str,
                       category: str) -> str:
        """
        Generate or extract answer for the question.

        Args:
            paper: Paper data
            question: Generated question
            category: Question category

        Returns:
            Answer text
        """
        # This is a simplified answer generation
        # In production, you would:
        # 1. Use the actual paper content to find relevant sections
        # 2. Use an LLM to generate accurate answers based on the content
        # 3. Verify answers with human annotation

        # For now, generate placeholder answers based on category
        if category == 'definition':
            answer = f"According to the paper, this refers to a specific concept or technique used in the research context. [This would contain the actual definition from the paper]"

        elif category == 'methodology':
            answer = f"The authors employed a systematic approach involving data collection, preprocessing, model training, and evaluation. [Actual methodology details would be extracted here]"

        elif category == 'results':
            answer = f"The experimental results show significant improvements over baseline methods, with specific metrics indicating [actual results would be here]"

        elif category == 'figure_table':
            answer = f"This figure/table presents the experimental results and comparisons, showing [actual figure/table description would be here]"

        elif category == 'comparison':
            answer = f"The comparison reveals that the proposed approach outperforms existing methods in terms of [actual comparison details would be here]"

        elif category == 'limitations':
            answer = f"The authors acknowledge certain limitations including computational complexity and dataset constraints. [Actual limitations would be listed here]"

        else:
            answer = f"[Answer would be extracted from the paper content relevant to: {question}]"

        return answer

    def _generate_id(self) -> str:
        """Generate unique question ID."""
        import uuid
        return str(uuid.uuid4())[:8]

    def _estimate_difficulty(self, category: str) -> str:
        """
        Estimate question difficulty based on category.

        Args:
            category: Question category

        Returns:
            Difficulty level
        """
        difficulty_map = {
            'definition': 'easy',
            'methodology': 'medium',
            'results': 'medium',
            'figure_table': 'easy',
            'comparison': 'hard',
            'limitations': 'hard'
        }
        return difficulty_map.get(category, 'medium')

    def save_dataset(self,
                    evaluation_data: List[Dict],
                    output_path: str = "./evaluation_dataset.json"):
        """
        Save evaluation dataset to file.

        Args:
            evaluation_data: List of question-answer pairs
            output_path: Output file path
        """
        output = {
            'metadata': {
                'total_questions': len(evaluation_data),
                'created_at': datetime.now().isoformat(),
                'categories': list(self.question_templates.keys()),
                'version': '1.0'
            },
            'questions': evaluation_data
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"✅ Saved evaluation dataset to {output_path}")

    def load_dataset(self, input_path: str) -> List[Dict]:
        """
        Load evaluation dataset from file.

        Args:
            input_path: Input file path

        Returns:
            List of question-answer pairs
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data['questions']

    def generate_human_annotation_template(self,
                                         evaluation_data: List[Dict],
                                         output_path: str = "./annotation_template.jsonl"):
        """
        Generate template for human annotation of answers.

        Args:
            evaluation_data: Generated evaluation data
            output_path: Output file path
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in evaluation_data:
                annotation = {
                    'question_id': item['question_id'],
                    'paper_title': item['paper_title'],
                    'question': item['question'],
                    'generated_answer': item['answer'],
                    'human_answer': "",  # To be filled by annotator
                    'is_correct': None,  # To be marked by annotator
                    'notes': ""  # Additional notes from annotator
                }
                f.write(json.dumps(annotation, ensure_ascii=False) + '\n')

        print(f"✅ Saved annotation template to {output_path}")


def test_evaluation_generator():
    """Test the evaluation dataset generator."""

    # Sample paper data
    sample_papers = [
        {
            'paper_id': 'paper1',
            'title': 'Deep Learning for Natural Language Processing',
            'abstract': 'We propose a novel BERT-based architecture for NLP tasks...',
            'figures': [
                {'number': '1', 'title': 'Model Architecture'},
                {'number': '2', 'title': 'Performance Comparison'}
            ],
            'tables': [
                {'number': '1', 'title': 'Dataset Statistics'}
            ]
        },
        {
            'paper_id': 'paper2',
            'title': 'Transformer Models for Computer Vision',
            'abstract': 'Vision Transformers (ViT) have shown remarkable performance...',
            'figures': [
                {'number': '1', 'title': 'ViT Architecture'},
                {'number': '3', 'title': 'Attention Maps'}
            ]
        }
    ]

    # Initialize generator
    generator = EvaluationDatasetGenerator()

    # Generate dataset
    dataset = generator.generate_dataset(
        sample_papers,
        questions_per_paper=5,
        total_questions=10
    )

    # Display results
    print("\nGenerated Evaluation Dataset:")
    print("-" * 50)

    for i, item in enumerate(dataset, 1):
        print(f"\nQuestion {i}:")
        print(f"  Paper: {item['paper_title']}")
        print(f"  Category: {item['category']}")
        print(f"  Q: {item['question']}")
        print(f"  A: {item['answer'][:100]}...")

    # Save dataset
    generator.save_dataset(dataset, "./test_evaluation_dataset.json")

    # Generate annotation template
    generator.generate_human_annotation_template(dataset, "./test_annotation.jsonl")


if __name__ == "__main__":
    test_evaluation_generator()