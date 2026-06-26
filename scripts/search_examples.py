#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
멀티모달 검색 실제 사용 예시
"""

from search_multimodal import MultimodalSearcher
import json

def run_examples():
    """다양한 검색 예시 실행"""

    searcher = MultimodalSearcher()

    print("\n" + "="*60)
    print("🔬 멀티모달 RAG 검색 예시")
    print("="*60)

    # 예시 1: LNP 관련 텍스트 검색
    print("\n### 예시 1: LNP (Lipid Nanoparticle) 관련 검색")
    results = searcher.search_text("lipid nanoparticle delivery system", top_k=5)
    for r in results[:3]:
        print(f"- [{r['type']}] {r['paper_id']}: 유사도 {r['similarity']:.3f}")

    # 예시 2: 이미지만 검색 (다이어그램, 그래프 등)
    print("\n### 예시 2: 실험 결과 그래프 이미지 검색")
    results = searcher.search_text("dose response curve graph", top_k=5, search_type="image")
    for r in results[:3]:
        print(f"- {r['id']}: 유사도 {r['similarity']:.3f}")
        if 'caption' in r['metadata']:
            print(f"  캡션: {r['metadata']['caption'][:100]}...")

    # 예시 3: 분자 구조 검색
    print("\n### 예시 3: 분자 구조 다이어그램 검색")
    results = searcher.search_text("chemical structure diagram molecule", top_k=5, search_type="image")
    for r in results[:3]:
        print(f"- 논문 {r['paper_id']}: 유사도 {r['similarity']:.3f}")

    # 예시 4: 한국어 검색
    print("\n### 예시 4: 한국어로 검색")
    results = searcher.search_text("세포 사멸 apoptosis", top_k=5)
    for r in results[:3]:
        print(f"- [{r['type']}] {r['paper_id']}: 유사도 {r['similarity']:.3f}")

    # 예시 5: EGFR 관련 pathway 다이어그램
    print("\n### 예시 5: EGFR signaling pathway 검색")
    results = searcher.search_text("EGFR signaling pathway diagram", top_k=5)
    for r in results[:3]:
        print(f"- [{r['type']}] {r['paper_id']}: 유사도 {r['similarity']:.3f}")

    # 예시 6: 통계 출력
    print("\n### 📊 데이터베이스 통계")
    total_items = searcher.collection.count()
    print(f"총 저장된 벡터: {total_items}개")

    # 샘플로 몇 개 논문의 구성 확인
    sample_papers = ["ZI67CEHF", "FCSQL7SI", "PY3FXCZU"]
    for paper_id in sample_papers:
        results = searcher.search_by_paper(paper_id)
        if results['ids']:
            text_count = sum(1 for m in results['metadatas'] if m.get('type') == 'text')
            image_count = sum(1 for m in results['metadatas'] if m.get('type') == 'image')
            print(f"- {paper_id}: 텍스트 {text_count}개, 이미지 {image_count}개")


def advanced_search_example():
    """고급 검색 예시"""

    searcher = MultimodalSearcher()

    print("\n" + "="*60)
    print("🎯 고급 멀티모달 검색 예시")
    print("="*60)

    # Cross-modal 검색: 텍스트로 관련 이미지 찾기
    print("\n### Cross-modal 검색: 텍스트 → 이미지")
    query = "Western blot protein expression analysis"
    results = searcher.search_text(query, top_k=10, search_type="image")

    image_papers = set()
    for r in results:
        if r['type'] == 'image':
            image_papers.add(r['paper_id'])

    print(f"'{query}' 관련 이미지가 있는 논문 {len(image_papers)}개 발견")
    for paper in list(image_papers)[:5]:
        print(f"  - {paper}")

    # 유사도 기반 논문 추천
    print("\n### 유사 논문 찾기")
    # 특정 논문의 벡터로 유사한 논문 찾기
    base_paper = "ZI67CEHF"
    paper_data = searcher.search_by_paper(base_paper)

    if paper_data['ids']:
        # 첫 번째 텍스트 청크의 임베딩으로 검색
        first_text_idx = next((i for i, m in enumerate(paper_data['metadatas'])
                              if m.get('type') == 'text'), None)

        if first_text_idx is not None:
            # 해당 텍스트로 유사 논문 검색
            text_content = paper_data['documents'][first_text_idx][:200]
            similar = searcher.search_text(text_content, top_k=10)

            similar_papers = set()
            for r in similar:
                if r['paper_id'] != base_paper:
                    similar_papers.add(r['paper_id'])

            print(f"{base_paper}와 유사한 논문:")
            for paper in list(similar_papers)[:5]:
                print(f"  - {paper}")


if __name__ == "__main__":
    # 기본 예시 실행
    run_examples()

    # 고급 예시 실행
    advanced_search_example()

    print("\n✅ 모든 예시 완료!")