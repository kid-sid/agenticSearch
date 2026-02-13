"""
Symbol Extractor — Parses code files into structured symbols.

Uses Python's built-in `ast` module for .py files (reliable).
Falls back to regex-based extraction for JS/TS/Go/Java/C (best-effort).
"""

import ast
import os
import re
import json
from typing import List, Dict, Optional


class SymbolExtractor:
    """
    Extracts structured symbols (classes, functions, methods, imports)
    from source code files using AST parsing (Python) or regex (others).
    """

    PYTHON_EXTENSIONS = {'.py'}
    JS_EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx'}
    C_FAMILY_EXTENSIONS = {'.c', '.cpp', '.h', '.hpp', '.cs', '.java', '.go', '.rs', '.kt', '.swift'}

    def __init__(self, cache_dir: str = ".cache/symbols"):
        self.cache_dir = os.path.abspath(cache_dir)
        self.symbols: Dict[str, List[Dict]] = {}  # file -> list of symbols
        os.makedirs(self.cache_dir, exist_ok=True)

    def extract_from_directory(self, root_path: str, force_rebuild: bool = False) -> Dict[str, List[Dict]]:
        """Walk a directory and extract symbols from all supported files."""
        cache_file = os.path.join(self.cache_dir, "symbol_index.json")

        if not force_rebuild and os.path.exists(cache_file):
            print("[SymbolExtractor] Loading cached symbol index...")
            with open(cache_file, "r", encoding="utf-8") as f:
                self.symbols = json.load(f)
            return self.symbols

        print("[SymbolExtractor] Extracting symbols from source files...")
        skip_dirs = {
            'node_modules', '.git', '.cache', '__pycache__', 'venv', '.venv',
            'dist', 'build', 'target', 'bin', 'obj', 'vendor', '.idea', '.vscode'
        }

        file_count = 0
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]

            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(filepath, root_path)
                ext = os.path.splitext(filename)[1].lower()

                symbols = []
                if ext in self.PYTHON_EXTENSIONS:
                    symbols = self._extract_python(filepath)
                elif ext in self.JS_EXTENSIONS:
                    symbols = self._extract_js(filepath)
                elif ext in self.C_FAMILY_EXTENSIONS:
                    symbols = self._extract_c_family(filepath)

                if symbols:
                    self.symbols[rel_path] = symbols
                    file_count += 1

        print(f"[SymbolExtractor] Extracted symbols from {file_count} files.")

        # Cache the index
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(self.symbols, f, indent=2)

        return self.symbols

    # ------------------------------------------------------------------ #
    #  Python AST Extraction (High Accuracy)
    # ------------------------------------------------------------------ #

    def _extract_python(self, filepath: str) -> List[Dict]:
        """Extract symbols from a Python file using the ast module."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception:
            return []

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return []

        symbols = []
        lines = source.splitlines()

        # Collect imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    symbols.append({
                        "type": "import",
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    symbols.append({
                        "type": "import",
                        "name": f"{module}.{alias.name}",
                        "alias": alias.asname,
                        "line": node.lineno
                    })

        # Extract top-level classes and functions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append(self._extract_python_class(node, lines))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(self._extract_python_function(node, lines, parent=None))

        return symbols

    def _extract_python_class(self, node: ast.ClassDef, lines: List[str]) -> Dict:
        """Extract a class and all its methods."""
        methods = []
        for item in ast.iter_child_nodes(node):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_python_function(item, lines, parent=node.name))

        return {
            "type": "class",
            "name": node.name,
            "start_line": node.lineno,
            "end_line": node.end_lineno or node.lineno,
            "docstring": ast.get_docstring(node) or "",
            "bases": [self._get_name(b) for b in node.bases],
            "methods": methods
        }

    def _extract_python_function(self, node, lines: List[str], parent: Optional[str]) -> Dict:
        """Extract a function/method with its calls."""
        params = []
        for arg in node.args.args:
            if arg.arg != 'self' and arg.arg != 'cls':
                params.append(arg.arg)

        # Find all function calls inside this function
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)
                if call_name:
                    calls.append(call_name)

        return {
            "type": "method" if parent else "function",
            "name": node.name,
            "parent": parent,
            "start_line": node.lineno,
            "end_line": node.end_lineno or node.lineno,
            "params": params,
            "calls": list(set(calls)),  # deduplicate
            "docstring": ast.get_docstring(node) or "",
            "is_async": isinstance(node, ast.AsyncFunctionDef)
        }

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extract the name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            value = self._get_name(node.func.value)
            if value:
                return f"{value}.{node.func.attr}"
            return node.func.attr
        return None

    def _get_name(self, node) -> str:
        """Get a dotted name from an AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._get_name(node.value)
            if value:
                return f"{value}.{node.attr}"
            return node.attr
        elif isinstance(node, ast.Constant):
            return str(node.value)
        return ""

    # ------------------------------------------------------------------ #
    #  JavaScript/TypeScript Regex Extraction (Best-Effort)
    # ------------------------------------------------------------------ #

    def _extract_js(self, filepath: str) -> List[Dict]:
        """Extract symbols from JS/TS files using regex."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception:
            return []

        symbols = []
        lines = source.splitlines()

        # Classes: class Foo { or class Foo extends Bar {
        for m in re.finditer(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', source):
            line_num = source[:m.start()].count('\n') + 1
            symbols.append({
                "type": "class",
                "name": m.group(1),
                "start_line": line_num,
                "end_line": self._find_block_end(lines, line_num - 1),
                "bases": [m.group(2)] if m.group(2) else []
            })

        # Functions: function foo(, const foo = (, export function foo(
        func_pattern = r'(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>)'
        for m in re.finditer(func_pattern, source):
            name = m.group(1) or m.group(2)
            line_num = source[:m.start()].count('\n') + 1
            calls = self._find_js_calls(lines, line_num - 1)
            symbols.append({
                "type": "function",
                "name": name,
                "parent": None,
                "start_line": line_num,
                "end_line": self._find_block_end(lines, line_num - 1),
                "calls": calls
            })

        return symbols

    def _find_js_calls(self, lines: List[str], start_idx: int) -> List[str]:
        """Find function calls in a JS block using regex."""
        end_idx = min(self._find_block_end(lines, start_idx), len(lines))
        block = "\n".join(lines[start_idx:end_idx])
        calls = re.findall(r'(?<!\w)(\w+)\s*\(', block)
        # Filter out common keywords
        keywords = {'if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'typeof', 'instanceof'}
        return list(set(c for c in calls if c not in keywords))

    # ------------------------------------------------------------------ #
    #  C-Family Regex Extraction (Best-Effort)
    # ------------------------------------------------------------------ #

    def _extract_c_family(self, filepath: str) -> List[Dict]:
        """Extract symbols from C/C++/Java/Go/Rust files using regex."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception:
            return []

        symbols = []
        lines = source.splitlines()

        # Classes: class Foo, struct Foo, type Foo struct
        for m in re.finditer(r'(?:class|struct|type)\s+(\w+)', source):
            line_num = source[:m.start()].count('\n') + 1
            symbols.append({
                "type": "class",
                "name": m.group(1),
                "start_line": line_num,
                "end_line": self._find_block_end(lines, line_num - 1)
            })

        # Functions: various patterns for C/Go/Java/Rust
        func_patterns = [
            r'(?:public|private|protected|static|async)?\s*(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{',  # Java/C
            r'func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(',  # Go
            r'fn\s+(\w+)\s*\(',  # Rust
        ]
        for pattern in func_patterns:
            for m in re.finditer(pattern, source):
                name = m.group(1)
                if name in {'if', 'for', 'while', 'switch', 'return', 'new'}:
                    continue
                line_num = source[:m.start()].count('\n') + 1
                symbols.append({
                    "type": "function",
                    "name": name,
                    "parent": None,
                    "start_line": line_num,
                    "end_line": self._find_block_end(lines, line_num - 1)
                })

        return symbols

    # ------------------------------------------------------------------ #
    #  Shared Helpers
    # ------------------------------------------------------------------ #

    def _find_block_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end of a brace-delimited block starting near start_idx."""
        depth = 0
        started = False
        for i in range(start_idx, min(start_idx + 500, len(lines))):
            for char in lines[i]:
                if char == '{':
                    depth += 1
                    started = True
                elif char == '}':
                    depth -= 1
                    if started and depth == 0:
                        return i + 1  # 1-indexed
        return min(start_idx + 50, len(lines))

    def get_symbol_at_line(self, file_path: str, line_num: int) -> Optional[Dict]:
        """Get the symbol (function/class) that contains a given line."""
        file_symbols = self.symbols.get(file_path, [])
        best_match = None

        for sym in file_symbols:
            if sym["type"] in ("class", "function", "method"):
                start = sym.get("start_line", 0)
                end = sym.get("end_line", 0)
                if start <= line_num <= end:
                    if best_match is None or (end - start) < (best_match["end_line"] - best_match["start_line"]):
                        best_match = sym

            # Check methods inside classes
            if sym["type"] == "class":
                for method in sym.get("methods", []):
                    start = method.get("start_line", 0)
                    end = method.get("end_line", 0)
                    if start <= line_num <= end:
                        if best_match is None or (end - start) < (best_match["end_line"] - best_match["start_line"]):
                            best_match = method

        return best_match

    def get_all_functions(self) -> List[Dict]:
        """Flatten all functions/methods across all files into a single list."""
        all_funcs = []
        for file_path, file_symbols in self.symbols.items():
            for sym in file_symbols:
                if sym["type"] in ("function", "method"):
                    func = dict(sym)
                    func["file"] = file_path
                    all_funcs.append(func)
                elif sym["type"] == "class":
                    for method in sym.get("methods", []):
                        func = dict(method)
                        func["file"] = file_path
                        all_funcs.append(func)
        return all_funcs
