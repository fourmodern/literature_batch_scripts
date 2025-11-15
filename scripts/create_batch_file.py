#!/usr/bin/env python3
"""
Zotero PDF 배치 파일 생성
vector_db_builder.py에서 사용할 JSON 파일 생성
"""

import os
import json
from pathlib import Path

# 스크립트 디렉토리를 path에 추가
import sys
sys.path.insert(0, 'scripts')

from zotero_path_finder import get_default_pdf_dir

def create_batch_file():
    """모든 PDF 정보를 담은 배치 파일 생성"""
    
    pdf_dir = get_default_pdf_dir()
    print(f"📂 Zotero 디렉토리: {pdf_dir}")
    
    papers = []
    
    # 모든 PDF 찾기
    for root, dirs, files in os.walk(pdf_dir):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_path = os.path.join(root, file)
                
                # storage 키 추출
                parts = pdf_path.split(os.sep)
                for i, part in enumerate(parts):
                    if part == 'storage' and i + 1 < len(parts):
                        storage_key = parts[i + 1]
                        if len(storage_key) == 8:
                            papers.append({
                                'pdf_path': pdf_path,
                                'paper_id': storage_key,
                                'metadata': {
                                    'filename': file,
                                    'storage_key': storage_key
                                }
                            })
                            break
    
    print(f"📄 발견된 PDF: {len(papers)}개")
    
    # JSON 파일로 저장
    output_file = 'papers_batch.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 배치 파일 생성 완료: {output_file}")
    print(f"\n사용법:")
    print(f"  python scripts/vector_db_builder.py --batch {output_file}")
    print(f"  python scripts/vector_db_builder.py --batch {output_file} --db pinecone")
    
    return output_file

if __name__ == "__main__":
    create_batch_file()