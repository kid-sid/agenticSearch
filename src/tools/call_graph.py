"""
Call Graph Builder — Builds a directed graph of function-to-function relationships.

Consumes the symbol index from SymbolExtractor and creates a traversable
graph that supports caller/callee lookups and chain tracing.
"""

import os
import json
from typing import List, Dict, Set, Optional
from collections import defaultdict


class CallGraph:
    """
    Directed graph of function call relationships.

    Nodes: Fully-qualified function names (e.g., "AuthService.login")
    Edges: "A calls B" relationship
    """

    def __init__(self, cache_dir: str = ".cache/call_graph"):
        self.cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

        # Adjacency lists
        self.callees: Dict[str, Set[str]] = defaultdict(set)  # func -> set of funcs it calls
        self.callers: Dict[str, Set[str]] = defaultdict(set)  # func -> set of funcs that call it

        # Metadata for each node
        self.node_info: Dict[str, Dict] = {}  # qualified_name -> {file, start_line, end_line, ...}

    def build_from_symbols(self, symbol_index: Dict[str, List[Dict]], force_rebuild: bool = False) -> None:
        """Build the call graph from the symbol extractor's output."""
        cache_file = os.path.join(self.cache_dir, "call_graph.json")

        if not force_rebuild and os.path.exists(cache_file):
            print("[CallGraph] Loading cached call graph...")
            self._load_cache(cache_file)
            return

        print("[CallGraph] Building call graph from symbol index...")

        # First pass: register all known symbols
        known_symbols = set()
        for file_path, file_symbols in symbol_index.items():
            for sym in file_symbols:
                if sym["type"] in ("function", "method"):
                    qname = self._qualified_name(sym)
                    known_symbols.add(qname)
                    self.node_info[qname] = {
                        "file": file_path,
                        "start_line": sym.get("start_line", 0),
                        "end_line": sym.get("end_line", 0),
                        "params": sym.get("params", []),
                        "docstring": sym.get("docstring", ""),
                        "parent": sym.get("parent"),
                    }
                elif sym["type"] == "class":
                    for method in sym.get("methods", []):
                        qname = self._qualified_name(method)
                        known_symbols.add(qname)
                        self.node_info[qname] = {
                            "file": file_path,
                            "start_line": method.get("start_line", 0),
                            "end_line": method.get("end_line", 0),
                            "params": method.get("params", []),
                            "docstring": method.get("docstring", ""),
                            "parent": method.get("parent"),
                        }

        # Second pass: build edges from call data
        for file_path, file_symbols in symbol_index.items():
            for sym in file_symbols:
                if sym["type"] in ("function", "method"):
                    self._process_calls(sym, known_symbols)
                elif sym["type"] == "class":
                    for method in sym.get("methods", []):
                        self._process_calls(method, known_symbols)

        node_count = len(self.node_info)
        edge_count = sum(len(v) for v in self.callees.values())
        print(f"[CallGraph] Built graph with {node_count} nodes and {edge_count} edges.")

        # Cache
        self._save_cache(cache_file)

    def _process_calls(self, sym: Dict, known_symbols: Set[str]) -> None:
        """Process the calls list of a symbol and build edges."""
        caller = self._qualified_name(sym)
        parent = sym.get("parent")

        for call_name in sym.get("calls", []):
            # Try to resolve the call to a known symbol
            resolved = self._resolve_call(call_name, parent, known_symbols)
            if resolved:
                self.callees[caller].add(resolved)
                self.callers[resolved].add(caller)

    def _resolve_call(self, call_name: str, parent_class: Optional[str], known_symbols: Set[str]) -> Optional[str]:
        """
        Try to resolve a call name to a known symbol.
        
        Resolution order:
        1. Exact match (e.g., "helper_func")
        2. self.method → ParentClass.method
        3. Partial match on method name (e.g., "login" → "AuthService.login")
        """
        # Direct match
        if call_name in known_symbols:
            return call_name

        # self.method pattern → resolve to ParentClass.method
        if call_name.startswith("self.") and parent_class:
            resolved = f"{parent_class}.{call_name[5:]}"
            if resolved in known_symbols:
                return resolved

        # Strip the object prefix and try bare method name
        if "." in call_name:
            bare_name = call_name.split(".")[-1]
            if bare_name in known_symbols:
                return bare_name

            # Try all classes: ClassName.method
            matches = [s for s in known_symbols if s.endswith(f".{bare_name}")]
            if len(matches) == 1:
                return matches[0]

        # Try prefixing with parent class
        if parent_class and f"{parent_class}.{call_name}" in known_symbols:
            return f"{parent_class}.{call_name}"

        return None

    # ------------------------------------------------------------------ #
    #  Query Methods
    # ------------------------------------------------------------------ #

    def get_callers(self, func_name: str) -> List[Dict]:
        """Get all functions that call the given function."""
        resolved = self._fuzzy_resolve(func_name)
        if not resolved:
            return []

        result = []
        for caller in self.callers.get(resolved, set()):
            info = dict(self.node_info.get(caller, {}))
            info["name"] = caller
            result.append(info)
        return result

    def get_callees(self, func_name: str) -> List[Dict]:
        """Get all functions that the given function calls."""
        resolved = self._fuzzy_resolve(func_name)
        if not resolved:
            return []

        result = []
        for callee in self.callees.get(resolved, set()):
            info = dict(self.node_info.get(callee, {}))
            info["name"] = callee
            result.append(info)
        return result

    def trace_chain(self, func_name: str, direction: str = "down", depth: int = 3) -> Dict:
        """
        Trace the call chain from a function.
        
        direction="down": What does this function call? (callee chain)
        direction="up": What calls this function? (caller chain)
        
        Returns a nested dict representing the tree.
        """
        resolved = self._fuzzy_resolve(func_name)
        if not resolved:
            return {"name": func_name, "not_found": True}

        visited = set()
        return self._trace_recursive(resolved, direction, depth, visited)

    def _trace_recursive(self, name: str, direction: str, depth: int, visited: Set[str]) -> Dict:
        """Recursively trace the call chain."""
        if depth <= 0 or name in visited:
            return {"name": name, "truncated": True}

        visited.add(name)
        info = dict(self.node_info.get(name, {}))
        info["name"] = name

        neighbors = self.callees.get(name, set()) if direction == "down" else self.callers.get(name, set())

        children = []
        for neighbor in sorted(neighbors):
            children.append(self._trace_recursive(neighbor, direction, depth - 1, visited))

        if children:
            key = "calls" if direction == "down" else "called_by"
            info[key] = children

        return info

    def format_chain_ascii(self, chain: Dict, prefix: str = "", is_last: bool = True) -> str:
        """Format a call chain as an ASCII tree for display."""
        connector = "└── " if is_last else "├── "
        name = chain.get("name", "?")
        file_info = chain.get("file", "")
        line_info = f":{chain['start_line']}" if "start_line" in chain else ""

        line = f"{prefix}{connector}{name}"
        if file_info:
            line += f"  ({file_info}{line_info})"
        if chain.get("truncated"):
            line += " ..."

        lines = [line]

        children_key = "calls" if "calls" in chain else "called_by"
        children = chain.get(children_key, [])
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(children):
            is_child_last = (i == len(children) - 1)
            lines.append(self.format_chain_ascii(child, new_prefix, is_child_last))

        return "\n".join(lines)

    def get_context_for_function(self, func_name: str, depth: int = 2) -> str:
        """
        Build rich context string for a function, including its callers and callees.
        Used to inject into the LLM prompt for code-aware answers.
        """
        resolved = self._fuzzy_resolve(func_name)
        if not resolved:
            return f"No call graph data found for '{func_name}'."

        parts = [f"## Call Graph Context for `{resolved}`\n"]

        info = self.node_info.get(resolved, {})
        if info:
            parts.append(f"**Location**: `{info.get('file', '?')}` (lines {info.get('start_line', '?')}-{info.get('end_line', '?')})")
            if info.get("docstring"):
                parts.append(f"**Docstring**: {info['docstring'][:200]}")
            parts.append("")

        # Callers
        callers = self.get_callers(resolved)
        if callers:
            parts.append("### Called By (upstream):")
            for c in callers:
                parts.append(f"- `{c['name']}` in `{c.get('file', '?')}`")
        else:
            parts.append("### Called By: *No known callers*")

        parts.append("")

        # Callees
        callees = self.get_callees(resolved)
        if callees:
            parts.append("### Calls (downstream):")
            for c in callees:
                parts.append(f"- `{c['name']}` in `{c.get('file', '?')}`")
        else:
            parts.append("### Calls: *No known callees*")

        parts.append("")

        # Full chain visualization
        down_chain = self.trace_chain(resolved, direction="down", depth=depth)
        parts.append("### Call Chain (downstream):")
        parts.append("```")
        parts.append(self.format_chain_ascii(down_chain))
        parts.append("```")

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def _qualified_name(self, sym: Dict) -> str:
        """Build a qualified name like 'ClassName.method' or 'function'."""
        parent = sym.get("parent")
        if parent:
            return f"{parent}.{sym['name']}"
        return sym["name"]

    def _fuzzy_resolve(self, name: str) -> Optional[str]:
        """Try to resolve a fuzzy name to a known node."""
        if name in self.node_info:
            return name

        # Try case-insensitive
        lower = name.lower()
        for key in self.node_info:
            if key.lower() == lower:
                return key

        # Try suffix match (e.g., "login" → "AuthService.login")
        matches = [k for k in self.node_info if k.endswith(f".{name}") or k == name]
        if len(matches) == 1:
            return matches[0]

        # Try substring match
        matches = [k for k in self.node_info if name.lower() in k.lower()]
        if len(matches) == 1:
            return matches[0]

        return None

    def _save_cache(self, cache_file: str):
        """Save the graph to disk."""
        data = {
            "callees": {k: list(v) for k, v in self.callees.items()},
            "callers": {k: list(v) for k, v in self.callers.items()},
            "node_info": self.node_info
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_cache(self, cache_file: str):
        """Load the graph from disk."""
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.callees = defaultdict(set, {k: set(v) for k, v in data.get("callees", {}).items()})
        self.callers = defaultdict(set, {k: set(v) for k, v in data.get("callers", {}).items()})
        self.node_info = data.get("node_info", {})
