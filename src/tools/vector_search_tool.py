"""
FAISS-based vector search tool using HNSW index.
Provides semantic code search by embedding file chunks and performing
approximate nearest-neighbor search.
"""

import os
import json
import fnmatch
import faiss
import numpy as np
from typing import List, Dict, Optional


# Extensions to index for search
INDEXABLE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java', '.c', '.cpp', '.h', 
    '.cs', '.rb', '.php', '.rs', '.swift', '.kt', '.m', '.mm', '.sh', '.bat', 
    '.md', '.txt', '.log', '.json', '.yaml', '.yml', '.toml', '.env', '.ini', 
    '.cfg', '.conf', '.csv', '.xml', '.rst', '.sql', '.html', '.css'
}

# Directories to skip entirely
SKIP_DIRS = {
    'node_modules', '.git', '.cache', '__pycache__', 'venv', '.venv',
    'dist', 'build', 'target', 'bin', 'obj', 'vendor', '.idea', '.vscode'
}

# HNSW parameters
HNSW_M = 32             # Number of connections per node (higher = better recall, more memory)
HNSW_EF_CONSTRUCTION = 200  # Build-time search depth (higher = better graph quality)
HNSW_EF_SEARCH = 128    # Query-time search depth (higher = better recall, slower)

# Chunking parameters
CHUNK_SIZE = 50          # Lines per chunk
CHUNK_OVERLAP = 10       # Overlapping lines between chunks


class VectorSearchTool:
    """
    FAISS HNSW-based semantic search over a codebase.

    Workflow:
        1. build_index(path) — walks files, chunks, embeds, builds HNSW index
        2. search(query) — embeds query, searches index, returns top-k results
    """

    INDEX_FILENAME = "index.faiss"
    META_FILENAME = "metadata.json"

    def __init__(self, embedding_client, cache_dir: str = ".cache/vector_index"):
        """
        Args:
            embedding_client: An object with embed(texts) -> np.ndarray
                              and embed_query(query) -> np.ndarray methods.
            cache_dir: Directory to persist the FAISS index and metadata.
        """
        self.embedding_client = embedding_client
        self.cache_dir = os.path.abspath(cache_dir)
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict] = []  # Parallel to index vectors

    def is_available(self) -> bool:
        """Check if the tool has a loaded/built index ready for search."""
        return self.index is not None and self.index.ntotal > 0

    def build_index(self, search_path: str, force_rebuild: bool = False) -> int:
        """
        Build the FAISS HNSW index from files under search_path.

        Args:
            search_path: Root directory to index.
            force_rebuild: If True, ignore cached index and rebuild.

        Returns:
            Number of chunks indexed.
        """
        search_path = os.path.abspath(search_path)

        # Try loading from cache first
        if not force_rebuild and self._load_cache():
            print(f"[VectorSearch] Loaded cached index ({self.index.ntotal} vectors)")
            return self.index.ntotal

        # 1. Collect and chunk files
        print(f"[VectorSearch] Scanning files in: {search_path}")
        chunks = self._chunk_files(search_path)

        if not chunks:
            print("[VectorSearch] No indexable files found.")
            return 0

        print(f"[VectorSearch] Chunked into {len(chunks)} segments")

        # 2. Generate embeddings
        print(f"[VectorSearch] Generating embeddings...")
        texts = [c["content"] for c in chunks]
        vectors = self.embedding_client.embed(texts)

        # 3. Build HNSW index
        print(f"[VectorSearch] Building HNSW index (M={HNSW_M})...")
        dimension = vectors.shape[1]

        self.index = faiss.IndexHNSWFlat(dimension, HNSW_M)
        self.index.hnsw.efConstruction = HNSW_EF_CONSTRUCTION
        self.index.hnsw.efSearch = HNSW_EF_SEARCH
        self.index.add(vectors)

        self.metadata = chunks

        # 4. Persist to cache
        self._save_cache()

        print(f"[VectorSearch] Index built: {self.index.ntotal} vectors")
        return self.index.ntotal

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        Search the index for chunks most similar to the query.

        Args:
            query: Natural language search query.
            top_k: Number of results to return.

        Returns:
            List of result dicts with keys:
                file, line_number, content, score, start_line, end_line
        """
        if not self.is_available():
            print("[VectorSearch] No index available. Call build_index() first.")
            return []

        # Clamp top_k to index size
        top_k = min(top_k, self.index.ntotal)

        query_vector = self.embedding_client.embed_query(query)
        distances, indices = self.index.search(query_vector, top_k)

        results = []
        for rank, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < 0 or idx >= len(self.metadata):
                continue  # FAISS returns -1 for empty slots

            chunk = self.metadata[idx]
            results.append({
                "file": chunk["file"],
                "line_number": chunk["start_line"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "content": chunk["content"],
                "score": float(dist),
            })

        return results

    # ── File Chunking ────────────────────────────────────────────────

    def _load_gitignore_patterns(self, root_path: str) -> List[str]:
        """Load .gitignore patterns from the root path."""
        gitignore_path = os.path.join(root_path, ".gitignore")
        patterns = []
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except Exception:
                pass
        return patterns

    def _is_gitignored(self, rel_path: str, patterns: List[str]) -> bool:
        """Check if a relative path matches any .gitignore pattern."""
        # Normalize to forward slashes for consistent matching
        rel_path_normalized = rel_path.replace(os.sep, "/")
        for pattern in patterns:
            # Directory pattern (e.g., "build/")
            if pattern.endswith("/"):
                dir_pattern = pattern.rstrip("/")
                if any(part == dir_pattern for part in rel_path_normalized.split("/")):
                    return True
            # Match against filename or full relative path
            if fnmatch.fnmatch(rel_path_normalized, pattern):
                return True
            if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
                return True
            # Handle patterns like "*.pyc" against full path
            if fnmatch.fnmatch(rel_path_normalized, f"**/{pattern}"):
                return True
        return False

    def _chunk_files(self, root_path: str) -> List[Dict]:
        """Walk directory tree, read files, and split into overlapping chunks."""
        chunks = []
        gitignore_patterns = self._load_gitignore_patterns(root_path)
        if gitignore_patterns:
            print(f"[VectorSearch] Loaded {len(gitignore_patterns)} .gitignore patterns")

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune skip directories in-place
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]

            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()

                # Also index extensionless files with known names
                basename_lower = filename.lower()
                is_known_file = basename_lower in {
                    'dockerfile', 'makefile', 'readme', 'license', 'changelog',
                    'contributing', 'authors', '.gitignore', '.dockerignore',
                }

                if ext not in INDEXABLE_EXTENSIONS and not is_known_file:
                    continue

                filepath = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(filepath, root_path)

                # Skip files matching .gitignore patterns
                if gitignore_patterns and self._is_gitignored(rel_path, gitignore_patterns):
                    continue

                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except Exception:
                    continue  # Skip unreadable files

                if not lines:
                    continue

                # Skip very large files (likely generated/vendored)
                if len(lines) > 10000:
                    continue

                # Create overlapping chunks
                file_chunks = self._split_into_chunks(rel_path, lines)
                chunks.extend(file_chunks)

        return chunks

    def _split_into_chunks(self, rel_path: str, lines: List[str]) -> List[Dict]:
        """Split file lines into overlapping chunks with metadata."""
        chunks = []
        total_lines = len(lines)

        if total_lines <= CHUNK_SIZE:
            # Small file — single chunk
            content = "".join(lines).strip()
            if content:
                chunks.append({
                    "file": rel_path,
                    "start_line": 1,
                    "end_line": total_lines,
                    "content": f"File: {rel_path}\n\n{content}",
                })
            return chunks

        start = 0
        while start < total_lines:
            end = min(start + CHUNK_SIZE, total_lines)
            content = "".join(lines[start:end]).strip()

            if content:
                chunks.append({
                    "file": rel_path,
                    "start_line": start + 1,  # 1-indexed
                    "end_line": end,
                    "content": f"File: {rel_path} (lines {start + 1}-{end})\n\n{content}",
                })

            start += CHUNK_SIZE - CHUNK_OVERLAP
            if start >= total_lines:
                break

        return chunks

    def chunk_by_symbols(self, root_path: str, symbol_index: dict) -> List[Dict]:
        """
        Create chunks aligned to function/class boundaries using symbol data.
        Falls back to line-based chunking for files without symbol data.
        """
        chunks = []
        gitignore_patterns = self._load_gitignore_patterns(root_path)

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]

            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                basename_lower = filename.lower()
                is_known_file = basename_lower in {
                    'dockerfile', 'makefile', 'readme', 'license', 'changelog',
                    'contributing', 'authors', '.gitignore', '.dockerignore',
                }
                if ext not in INDEXABLE_EXTENSIONS and not is_known_file:
                    continue

                filepath = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(filepath, root_path)

                if gitignore_patterns and self._is_gitignored(rel_path, gitignore_patterns):
                    continue

                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except Exception:
                    continue

                if not lines or len(lines) > 10000:
                    continue

                # Check if we have symbol data for this file
                file_symbols = symbol_index.get(rel_path, [])
                code_symbols = [
                    s for s in file_symbols
                    if s.get("type") in ("class", "function", "method")
                ]

                if code_symbols:
                    # Symbol-aware chunking
                    for sym in code_symbols:
                        start = max(0, sym.get("start_line", 1) - 1)
                        end = min(len(lines), sym.get("end_line", len(lines)))
                        content = "".join(lines[start:end]).strip()

                        if not content:
                            continue

                        sym_name = sym.get("name", "unknown")
                        parent = sym.get("parent")
                        qualified = f"{parent}.{sym_name}" if parent else sym_name
                        sym_type = sym.get("type", "symbol")

                        header = f"File: {rel_path} | {sym_type}: {qualified} (lines {start+1}-{end})"
                        calls = sym.get("calls", [])
                        if not calls and sym.get("methods"):
                            # For classes, list method names
                            calls = [m.get("name", "") for m in sym.get("methods", [])]

                        call_info = ""
                        if calls:
                            call_info = f"\nCalls: {', '.join(calls[:15])}"

                        chunks.append({
                            "file": rel_path,
                            "start_line": start + 1,
                            "end_line": end,
                            "content": f"{header}{call_info}\n\n{content}",
                            "symbol": qualified,
                            "symbol_type": sym_type,
                        })
                else:
                    # Fallback to standard line-based chunking
                    file_chunks = self._split_into_chunks(rel_path, lines)
                    chunks.extend(file_chunks)

        return chunks

    def build_index_with_symbols(self, search_path: str, symbol_index: dict, force_rebuild: bool = False) -> int:
        """Build FAISS index using symbol-aware chunks."""
        search_path = os.path.abspath(search_path)

        if not force_rebuild and self._load_cache():
            print(f"[VectorSearch] Loaded cached index ({self.index.ntotal} vectors)")
            return self.index.ntotal

        print(f"[VectorSearch] Building symbol-aware index for: {search_path}")
        chunks = self.chunk_by_symbols(search_path, symbol_index)

        if not chunks:
            print("[VectorSearch] No indexable files found.")
            return 0

        print(f"[VectorSearch] Chunked into {len(chunks)} symbol-aligned segments")

        texts = [c["content"] for c in chunks]
        vectors = self.embedding_client.embed(texts)

        dimension = vectors.shape[1]
        self.index = faiss.IndexHNSWFlat(dimension, HNSW_M)
        self.index.hnsw.efConstruction = HNSW_EF_CONSTRUCTION
        self.index.hnsw.efSearch = HNSW_EF_SEARCH
        self.index.add(vectors)

        self.metadata = chunks
        self._save_cache()

        print(f"[VectorSearch] Symbol-aware index built: {self.index.ntotal} vectors")
        return self.index.ntotal

    # ── Cache Persistence ────────────────────────────────────────────

    def _save_cache(self):
        """Save FAISS index and metadata to disk."""
        os.makedirs(self.cache_dir, exist_ok=True)

        index_path = os.path.join(self.cache_dir, self.INDEX_FILENAME)
        meta_path = os.path.join(self.cache_dir, self.META_FILENAME)

        faiss.write_index(self.index, index_path)

        # Save metadata without the full content to save space
        meta_for_save = []
        for m in self.metadata:
            meta_for_save.append({
                "file": m["file"],
                "start_line": m["start_line"],
                "end_line": m["end_line"],
                "content": m["content"],
            })

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_for_save, f, ensure_ascii=False)

        print(f"[VectorSearch] Index cached to: {self.cache_dir}")

    def _load_cache(self) -> bool:
        """Load FAISS index and metadata from disk. Returns True if successful."""
        index_path = os.path.join(self.cache_dir, self.INDEX_FILENAME)
        meta_path = os.path.join(self.cache_dir, self.META_FILENAME)

        if not os.path.exists(index_path) or not os.path.exists(meta_path):
            return False

        try:
            self.index = faiss.read_index(index_path)
            self.index.hnsw.efSearch = HNSW_EF_SEARCH  # Re-apply search param

            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)

            if self.index.ntotal != len(self.metadata):
                print("[VectorSearch] Cache mismatch. Rebuilding...")
                self.index = None
                self.metadata = []
                return False

            return True

        except Exception as e:
            print(f"[VectorSearch] Cache load error: {e}")
            self.index = None
            self.metadata = []
            return False
