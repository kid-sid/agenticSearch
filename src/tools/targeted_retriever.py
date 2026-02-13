"""
Targeted File Content Retriever.

Reads full file content from the cached full_codebase.md for specific files
identified by the skeleton analysis step. This ensures the LLM always sees
the most relevant files in full, not just partial search hits.
"""

import os
import re
from typing import List, Dict, Optional


class TargetedRetriever:
    """
    Retrieves full file contents from the cached markdown codebase dump.
    
    The full_codebase.md file contains sections like:
        ### File: `path/to/file.py` (lines X-Y)
        ```python
        <full file content>
        ```
    
    This tool parses those sections and returns the content of targeted files.
    """

    def __init__(self, cache_path: str):
        """
        Args:
            cache_path: Path to the cached repo directory containing full_codebase.md
        """
        self.cache_path = cache_path
        self.codebase_path = os.path.join(cache_path, "full_codebase.md")
        self._file_sections: Optional[Dict[str, str]] = None

    def _parse_codebase_md(self) -> Dict[str, str]:
        """
        Parse full_codebase.md into a dict of {file_path: file_content}.
        Caches the result for repeated lookups.
        """
        if self._file_sections is not None:
            return self._file_sections

        self._file_sections = {}

        if not os.path.exists(self.codebase_path):
            print(f"[TargetedRetriever] Warning: {self.codebase_path} not found")
            return self._file_sections

        with open(self.codebase_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern: # File: path/to/file.ext
        # followed by ```<lang>\n<content>\n```
        # Note: markdown_repo_manager uses single hash and no backticks around filename
        pattern = r'# File: ([^\n]+)\n\n```[^\n]*\n(.*?)```'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for file_path, file_content in matches:
            # Normalize path
            normalized = file_path.strip().replace("\\", "/")
            self._file_sections[normalized] = file_content.strip()

        print(f"[TargetedRetriever] Parsed {len(self._file_sections)} files from cache")
        return self._file_sections

    def get_file_content(self, file_path: str) -> Optional[str]:
        """
        Get the full content of a specific file from the cache.
        
        Args:
            file_path: Relative path like 'services/auth_service.py'
            
        Returns:
            Full file content string, or None if not found.
        """
        sections = self._parse_codebase_md()
        normalized = file_path.strip().replace("\\", "/")

        if normalized in sections:
            return sections[normalized]

        # Try suffix match (e.g., 'auth_service.py' matches 'services/auth_service.py')
        for cached_path, content in sections.items():
            if cached_path.endswith(normalized) or normalized.endswith(cached_path):
                return content

        # Try basename match
        target_basename = os.path.basename(normalized)
        for cached_path, content in sections.items():
            if os.path.basename(cached_path) == target_basename:
                return content

        return None

    def retrieve_files(self, file_paths: List[str], max_chars_per_file: int = 100000) -> List[Dict]:
        """
        Retrieve full content for multiple files, formatted as chunks.
        
        Args:
            file_paths: List of file paths to retrieve.
            max_chars_per_file: Max characters per file to avoid context overflow.
            
        Returns:
            List of chunk dicts with keys: file, content, start_line, end_line, source
        """
        chunks = []
        sections = self._parse_codebase_md()

        for fpath in file_paths:
            content = self.get_file_content(fpath)
            if content is None:
                print(f"[TargetedRetriever] File not found in cache: {fpath}")
                continue

            # Truncate if too large
            if len(content) > max_chars_per_file:
                content = content[:max_chars_per_file] + "\n... [truncated]"

            lines = content.split("\n")

            # Find the matching cached path for metadata
            matched_path = fpath
            normalized = fpath.replace("\\", "/").strip()
            for cached_path in sections:
                if cached_path.endswith(normalized) or normalized.endswith(cached_path) or os.path.basename(cached_path) == os.path.basename(normalized):
                    matched_path = cached_path
                    break

            chunks.append({
                "file": matched_path,
                "content": content,
                "start_line": 1,
                "end_line": len(lines),
                "source": "targeted",
                "symbol": "",  # For compatibility with reranker
            })

            print(f"[TargetedRetriever] Retrieved: {matched_path} ({len(lines)} lines)")

        return chunks

    def get_available_files(self) -> List[str]:
        """Return list of all file paths available in the cache."""
        sections = self._parse_codebase_md()
        return list(sections.keys())
