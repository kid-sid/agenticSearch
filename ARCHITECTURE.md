# Architecture: Agentic Search Tool

This document outlines the high-level architecture and processing pipeline of the Agentic Search Tool. The system is designed to perform context-aware, semantic code searches across large repositories by combining statistical models with LLM intelligence.

## System Architecture

The tool follows a **Modular Pipeline Architecture**, separating context acquisition, search execution, and answer synthesis.

```mermaid
graph TD
    User([User Question]) --> Main[main.py: Orchestrator]
    
    subgraph "Phase 1: Context & Intelligence"
        Main --> Skeleton[LLM: Skeleton Analysis]
        Main --> QM[LLM: Query Manager]
    end
    
    subgraph "Phase 2: Hybrid Retrieval"
        Skeleton --> TR[Targeted Retriever: Full Files]
        QM --> VS[Vector Search: FAISS HNSW]
        QM --> BM25[BM25 Search: Statistical]
        QM --> RG[Grep Search: Keywords]
    end
    
    subgraph "Phase 3: Processing & Synthesis"
        TR & VS & BM25 & RG --> Merge[Deduplication & Reranking]
        Merge --> RE[Cross-Encoder Reranker]
        RE --> Synthesis[LLM: Code-Aware Synthesis]
    end
    
    Synthesis --> Output([Final Answer])
```

---

## Core Components

### 1. The Orchestrator (`main.py`)
The primary entry point that manages the lifecycle of a search request.
### 3. Search Workflow (8-Step Pipeline)

1.  **Project Skeleton & MiniMap Loading**: Load file tree + `symbol_minimap.json` (signatures, docstrings, keywords).
2.  **Query Expansion**: LLM refines user question into "Technical Intent" + keywords (e.g. "auth" -> "JWT validation").
3.  **Skeleton Analysis**: LLM identifies 3-8 key files using the MiniMap and file tree.
4.  **Targeted Retrieval**: Full content of identified files is read immediately.
5.  **Symbol & Call Graph Analysis**: Extract symbols and relationships from targeted files.
6.  **Triple-Hybrid Search**: Parallel Vector + BM25 + Ripgrep (regex) search for broader context.
7.  **Merge & Rerank**: Combine targeted files + search results, rerank using Cross-Encoder.
8.  **Answer Synthesis**: LLM generates answer using the curated context.

### 4. Key Components

-   **`LLMClient`**: Handles all LLM interactions (now using `src/prompts.py`).
-   **`MarkdownRepoManager`**: Syncs GitHub repos to `.cache`, builds `symbol_minimap.json`.
-   **`TargetedRetriever`**: surgically reads files identified by Skeleton Analysis.
-   **`SymbolExtractor` / `CallGraph`**: Static analysis for Python/JS.
-   **`VectorSearchTool` / `BM25SearchTool`**: Semantic & Keyword search.
-   **`SearchTool` (Ripgrep)**: Regex pattern matching with technical keywords.
- **Synthesize Answers**: Combines retrieved code snippets, call graphs, and file structure to produce high-fidelity answers.

### 3. The Search Engine
The tool uses a **Triple-Hybrid Search** strategy to maximize recall:
- **Vector Search (`src/tools/vector_search_tool.py`)**: Uses `text-embedding-3-small` and FAISS (HNSW) for semantic understanding (e.g., finding "auth logic" when searching for "security").
- **BM25 Search (`src/tools/bm25_search_tool.py`)**: A statistical model that finds the most relevant code chunks based on term frequency (TF-IDF).
- **Regex Search (`src/tools/search_tool.py`)**: A high-speed `ripgrep` wrapper that finds literal matches and complex patterns.

### 4. Data & Retrieval Tools
- **Targeted Retriever (`src/tools/targeted_retriever.py`)**: Specifically designed to bypass search limitations by loading the entire content of small-to-medium files (up to 100k characters).
- **Markdown Repo Manager (`src/tools/markdown_repo_manager.py`)**: Efficiently fetches remote GitHub repositories using GraphQL batching and caches them locally as flattened Markdown.

---

## Data Flow
1. **Discovery**: The tool reads the `README.md` and file structure to understand the "big picture."
2. **Focus**: Instead of searching everything, it "targets" likely files (e.g., `config.py` for settings).
3. **Retrieval**: It gathers broad semantic matches (Vector) and exact matches (BM25/Grep).
4. **Filtering**: A **Cross-Encoder Reranker** verifies the relevance of each snippet against the actual question.
5. **Grounding**: The final LLM call is "clamped" to the provided context to prevent hallucinations.
