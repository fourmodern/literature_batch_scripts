"""
RAG System Performance Evaluator
RAG 시스템의 검색 정확도 및 답변 품질 평가
"""

import os
import sys
import json
import time
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from datetime import datetime
import numpy as np
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import RAG system
try:
    from improved_rag_builder import ImprovedRAGBuilder
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️ ImprovedRAGBuilder not available")

# Import evaluation dataset generator
from evaluation_dataset import EvaluationDatasetGenerator

# Import OpenAI for answer quality evaluation
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not available for answer quality evaluation")

from dotenv import load_dotenv
load_dotenv()


class RAGEvaluator:
    """
    Evaluate RAG system performance using various metrics.
    """

    def __init__(self, rag_system: Optional[ImprovedRAGBuilder] = None):
        """
        Initialize the evaluator.

        Args:
            rag_system: RAG system instance to evaluate
        """
        self.rag_system = rag_system
        
        # Initialize OpenAI client for answer evaluation
        if OPENAI_AVAILABLE:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.openai_client = OpenAI(api_key=api_key)
            else:
                self.openai_client = None
                print("⚠️ OPENAI_API_KEY not found. Answer quality evaluation disabled.")
        else:
            self.openai_client = None

    def evaluate_retrieval(self,
                         evaluation_dataset: List[Dict],
                         k_values: List[int] = [1, 3, 5, 10]) -> Dict:
        """
        Evaluate retrieval performance.

        Args:
            evaluation_dataset: List of Q&A pairs with relevant chunks
            k_values: List of k values for Recall@k computation

        Returns:
            Dictionary of evaluation metrics
        """
        if not self.rag_system:
            raise ValueError("RAG system not initialized")

        print(f"\n📊 Evaluating retrieval on {len(evaluation_dataset)} questions...")
        
        # Initialize metrics
        recall_at_k = {k: [] for k in k_values}
        mrr_scores = []  # Mean Reciprocal Rank
        precision_at_k = {k: [] for k in k_values}
        
        # Track performance by category
        category_metrics = {}
        
        for item in tqdm(evaluation_dataset):
            question = item['question']
            relevant_chunks = set(item.get('relevant_chunks', []))
            category = item.get('category', 'unknown')
            
            # Skip if no relevant chunks marked
            if not relevant_chunks:
                continue
            
            # Search with different k values
            max_k = max(k_values)
            search_results = self.rag_system.search(question, k=max_k)
            
            # Extract retrieved chunk IDs
            retrieved_ids = [result['id'] for result in search_results]
            
            # Calculate metrics for each k
            for k in k_values:
                retrieved_k = set(retrieved_ids[:k])
                
                # Recall@k: What fraction of relevant chunks were retrieved
                if relevant_chunks:
                    recall = len(retrieved_k & relevant_chunks) / len(relevant_chunks)
                    recall_at_k[k].append(recall)
                
                # Precision@k: What fraction of retrieved chunks were relevant
                if retrieved_k:
                    precision = len(retrieved_k & relevant_chunks) / len(retrieved_k)
                    precision_at_k[k].append(precision)
            
            # Mean Reciprocal Rank (MRR)
            for rank, chunk_id in enumerate(retrieved_ids, 1):
                if chunk_id in relevant_chunks:
                    mrr_scores.append(1.0 / rank)
                    break
            else:
                mrr_scores.append(0.0)
            
            # Track category performance
            if category not in category_metrics:
                category_metrics[category] = {'recall': [], 'mrr': []}
            
            category_metrics[category]['recall'].append(
                recall_at_k[5][-1] if 5 in recall_at_k else 0
            )
            category_metrics[category]['mrr'].append(mrr_scores[-1])
        
        # Calculate average metrics
        results = {
            'total_questions': len(evaluation_dataset),
            'evaluated_questions': len(mrr_scores),
            'metrics': {
                'mrr': np.mean(mrr_scores) if mrr_scores else 0,
                'recall_at_k': {k: np.mean(scores) if scores else 0 
                              for k, scores in recall_at_k.items()},
                'precision_at_k': {k: np.mean(scores) if scores else 0
                                 for k, scores in precision_at_k.items()}
            },
            'category_performance': {}
        }
        
        # Calculate category averages
        for category, metrics in category_metrics.items():
            results['category_performance'][category] = {
                'recall@5': np.mean(metrics['recall']) if metrics['recall'] else 0,
                'mrr': np.mean(metrics['mrr']) if metrics['mrr'] else 0,
                'count': len(metrics['recall'])
            }
        
        return results

    def evaluate_answer_quality(self,
                             evaluation_dataset: List[Dict],
                             sample_size: int = 10) -> Dict:
        """
        Evaluate answer generation quality using GPT-4.

        Args:
            evaluation_dataset: List of Q&A pairs
            sample_size: Number of questions to evaluate

        Returns:
            Dictionary of quality metrics
        """
        if not self.rag_system:
            raise ValueError("RAG system not initialized")
        
        if not self.openai_client:
            return {"error": "OpenAI client not available for answer evaluation"}
        
        print(f"\n🎯 Evaluating answer quality on {sample_size} questions...")
        
        # Sample questions
        import random
        sample = random.sample(evaluation_dataset, min(sample_size, len(evaluation_dataset)))
        
        quality_scores = []
        relevance_scores = []
        completeness_scores = []
        
        for item in tqdm(sample):
            question = item['question']
            expected_answer = item.get('answer', '')
            
            # Get RAG system's answer
            search_results = self.rag_system.search(question, k=5)
            context = "\n\n".join([r['text'] for r in search_results[:3]])
            
            # Generate answer using context
            rag_answer = self._generate_answer(question, context)
            
            if rag_answer:
                # Evaluate answer quality
                scores = self._evaluate_single_answer(
                    question,
                    rag_answer,
                    expected_answer,
                    context
                )
                
                if scores:
                    quality_scores.append(scores['quality'])
                    relevance_scores.append(scores['relevance'])
                    completeness_scores.append(scores['completeness'])
        
        return {
            'evaluated_samples': len(quality_scores),
            'average_quality': np.mean(quality_scores) if quality_scores else 0,
            'average_relevance': np.mean(relevance_scores) if relevance_scores else 0,
            'average_completeness': np.mean(completeness_scores) if completeness_scores else 0,
            'quality_distribution': {
                'excellent': sum(1 for s in quality_scores if s >= 4.5),
                'good': sum(1 for s in quality_scores if 3.5 <= s < 4.5),
                'fair': sum(1 for s in quality_scores if 2.5 <= s < 3.5),
                'poor': sum(1 for s in quality_scores if s < 2.5)
            }
        }

    def _generate_answer(self, question: str, context: str) -> Optional[str]:
        """
        Generate answer using retrieved context.

        Args:
            question: User question
            context: Retrieved context chunks

        Returns:
            Generated answer
        """
        if not self.openai_client:
            return None
        
        try:
            prompt = f"""Based on the following context from academic papers, answer the question.
            
Context:
{context}

Question: {question}

Provide a clear, concise answer based only on the given context. If the context doesn't contain enough information, state that clearly.

Answer:"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful academic assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            print(f"Error generating answer: {e}")
            return None

    def _evaluate_single_answer(self,
                              question: str,
                              rag_answer: str,
                              expected_answer: str,
                              context: str) -> Optional[Dict]:
        """
        Evaluate a single answer using GPT-4.

        Args:
            question: Original question
            rag_answer: RAG system's answer
            expected_answer: Expected/reference answer
            context: Retrieved context

        Returns:
            Dictionary of scores
        """
        if not self.openai_client:
            return None
        
        try:
            evaluation_prompt = f"""Evaluate the quality of this RAG system answer.

Question: {question}

RAG System Answer: {rag_answer}

Reference Answer: {expected_answer}

Retrieved Context: {context[:1000]}...

Evaluate the RAG answer on three dimensions:
1. Quality (1-5): Overall answer quality
2. Relevance (1-5): How well it answers the specific question
3. Completeness (1-5): How thoroughly it covers the topic

Provide scores in JSON format:
{{"quality": X, "relevance": Y, "completeness": Z}}

Scores:"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert evaluator of AI-generated answers."},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            
            # Parse JSON response
            import re
            content = response.choices[0].message.content
            json_match = re.search(r'\{.*\}', content)
            if json_match:
                scores = json.loads(json_match.group())
                return scores
            
        except Exception as e:
            print(f"Error evaluating answer: {e}")
        
        return None

    def run_full_evaluation(self,
                          evaluation_dataset: List[Dict],
                          output_path: str = "./evaluation_results.json") -> Dict:
        """
        Run complete evaluation suite.

        Args:
            evaluation_dataset: Evaluation Q&A pairs
            output_path: Path to save results

        Returns:
            Complete evaluation results
        """
        print("="*50)
        print("🚀 Starting RAG System Evaluation")
        print("="*50)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'dataset_size': len(evaluation_dataset)
        }
        
        # 1. Retrieval evaluation
        print("\n📚 Phase 1: Retrieval Performance")
        retrieval_results = self.evaluate_retrieval(evaluation_dataset)
        results['retrieval'] = retrieval_results
        
        # 2. Answer quality evaluation
        print("\n💡 Phase 2: Answer Quality")
        answer_results = self.evaluate_answer_quality(evaluation_dataset)
        results['answer_quality'] = answer_results
        
        # 3. Performance by question type
        results['performance_by_category'] = retrieval_results.get('category_performance', {})
        
        # Save results
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # Print summary
        self._print_evaluation_summary(results)
        
        return results

    def _print_evaluation_summary(self, results: Dict):
        """
        Print evaluation summary.

        Args:
            results: Evaluation results
        """
        print("\n" + "="*50)
        print("📊 EVALUATION SUMMARY")
        print("="*50)
        
        # Retrieval metrics
        if 'retrieval' in results:
            retrieval = results['retrieval']
            print("\n🔍 Retrieval Performance:")
            print(f"  • MRR: {retrieval['metrics']['mrr']:.3f}")
            for k, score in retrieval['metrics']['recall_at_k'].items():
                print(f"  • Recall@{k}: {score:.3f}")
        
        # Answer quality
        if 'answer_quality' in results:
            quality = results['answer_quality']
            if 'average_quality' in quality:
                print("\n✨ Answer Quality:")
                print(f"  • Overall Quality: {quality['average_quality']:.2f}/5")
                print(f"  • Relevance: {quality['average_relevance']:.2f}/5")
                print(f"  • Completeness: {quality['average_completeness']:.2f}/5")
        
        # Category performance
        if 'performance_by_category' in results:
            print("\n📈 Performance by Category:")
            for category, metrics in results['performance_by_category'].items():
                print(f"  • {category}: Recall@5={metrics['recall@5']:.3f}, MRR={metrics['mrr']:.3f}")
        
        print("\n✅ Evaluation complete! Results saved to evaluation_results.json")

    def compare_configurations(self,
                             evaluation_dataset: List[Dict],
                             configurations: List[Dict]) -> Dict:
        """
        Compare different RAG configurations.

        Args:
            evaluation_dataset: Evaluation dataset
            configurations: List of configuration dictionaries

        Returns:
            Comparison results
        """
        comparison_results = {}
        
        for config in configurations:
            config_name = config['name']
            print(f"\n🔧 Testing configuration: {config_name}")
            
            # Initialize RAG with specific configuration
            rag = ImprovedRAGBuilder(
                chunk_size=config.get('chunk_size', 1000),
                overlap=config.get('overlap', 200),
                db_type=config.get('db_type', 'chroma')
            )
            
            # Set RAG system
            self.rag_system = rag
            
            # Run evaluation
            results = self.evaluate_retrieval(evaluation_dataset)
            comparison_results[config_name] = results
        
        # Find best configuration
        best_config = None
        best_mrr = 0
        for name, results in comparison_results.items():
            mrr = results['metrics']['mrr']
            if mrr > best_mrr:
                best_mrr = mrr
                best_config = name
        
        print(f"\n🏆 Best configuration: {best_config} (MRR: {best_mrr:.3f})")
        
        return comparison_results


def test_evaluator():
    """Test the RAG evaluator."""
    
    # Initialize RAG system
    if RAG_AVAILABLE:
        rag = ImprovedRAGBuilder(db_type="chroma")
    else:
        rag = None
        print("RAG system not available. Using mock evaluation.")
    
    # Generate sample evaluation dataset
    generator = EvaluationDatasetGenerator(rag_system=rag)
    
    # Create sample papers for testing
    sample_papers = [
        {
            'paper_id': 'test_001',
            'title': 'Deep Learning for NLP',
            'abstract': 'This paper presents a novel approach...'
        }
    ]
    
    # Generate evaluation dataset
    dataset = generator.generate_dataset(
        sample_papers,
        questions_per_paper=5,
        total_questions=5
    )
    
    # Initialize evaluator
    evaluator = RAGEvaluator(rag_system=rag)
    
    # Run evaluation
    if rag:
        results = evaluator.run_full_evaluation(dataset)
        print(f"\nEvaluation complete! MRR: {results['retrieval']['metrics']['mrr']:.3f}")
    else:
        print("\nMock evaluation completed.")
        print("Install required dependencies and initialize RAG system for real evaluation.")


if __name__ == "__main__":
    test_evaluator()