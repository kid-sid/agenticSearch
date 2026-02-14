import os
import re
import pickle
from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi

class BM25SearchTool:
    """
    Statistical search using BM25.
    Treats code chunks as documents and ranks them based on term frequency
    and inverse document frequency.
    """
    
    CACHE_FILENAME = "bm25_index.pkl"

    def __init__(self, cache_dir: str = ".cache/bm25_index"):
        self.cache_dir = os.path.abspath(cache_dir)
        self.bm25 = None
        self.metadata = [] # Parallel to BM25 documents

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer for code and text."""
        # Split by non-alphanumeric and keep it simple
        return re.findall(r'\w+', text.lower())

    def is_available(self) -> bool:
        return self.bm25 is not None

    def build_index(self, chunks: List[Dict], force_rebuild: bool = False):
        """
        Build index from chunks provided (usually from VectorSearchTool's chunking).
        """
        os.makedirs(self.cache_dir, exist_ok=True)
        cache_path = os.path.join(self.cache_dir, self.CACHE_FILENAME)

        if not force_rebuild and os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    data = pickle.load(f)
                    self.bm25 = data["bm25"]
                    self.metadata = data["metadata"]
                print(f"[BM25] Loaded cached index ({len(self.metadata)} documents)")
                return
            except Exception as e:
                print(f"[BM25] Cache load error: {e}")

        if not chunks:
            print("[BM25] No chunks provided. Skipping index build.")
            self.bm25 = None
            self.metadata = []
            return

        print(f"[BM25] Building index from {len(chunks)} chunks...")
        self.metadata = chunks
        tokenized_corpus = [self._tokenize(chunk["content"]) for chunk in chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

        try:
            with open(cache_path, "wb") as f:
                pickle.dump({"bm25": self.bm25, "metadata": self.metadata}, f)
            print(f"[BM25] Index cached to: {self.cache_dir}")
        except Exception as e:
            print(f"[BM25] Failed to cache index: {e}")

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """Search the BM25 index."""
        if not self.is_available():
            return []

        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] <= 0: continue
            
            chunk = self.metadata[idx]
            results.append({
                "file": chunk["file"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "content": chunk["content"],
                "score": float(scores[idx]),
                "source": "bm25"
            })
        
        return results
