# Agentic Search Tool

An AI-powered CLI tool that performs semantic search over your codebase using `ripgrep` and answers questions using an LLM (OpenAI).

## Features
- **Context-Aware Search**: Automatically fetches `README.md` first to understand the project architecture before searching.
- **Smart Caching**: checks for existing local caches to skip API calls, enabling instant subsequent searches on the same repo.
- **Deep Context**: Retrieves file content and synthesizes answers based on actual code.
- **Cross-Platform**: Works on Windows, macOS, and Linux.

## Setup

1.  **Clone the repository**:
    ```bash
    git clone <your-repo-url>
    cd agenticSearch
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install Ripgrep**:
    - **Windows**: `winget install BurntSushi.ripgrep.MSVC`
    - **macOS**: `brew install ripgrep`
    - **Linux**: `apt-get install ripgrep`

4.  **Configure Environment**:
    Create a `.env` file in the root directory:
    ```env
    OPENAI_API_KEY=sk-...
    GITHUB_TOKEN=ghp_... (Required for GitHub Search)
    ```

## Usage

### 1. GitHub Context-Aware Search (Recommended)
This mode fetches the README, analyzes project context, caches the repo structure (as Markdown), and then performs a smart search.
```bash
python main.py "How does the search logic work?" --github-repo owner/repo --provider openai
```

### 2. Local Search with Context
Run the tool against your local files. It will try to read a local `README.md` for context.
```bash
python main.py "Where is the main entry point?" --path . --provider openai
```

### 3. Smart Suggestions
Generate relevant technical questions from the codebase.
```bash
python main.py --github-repo owner/repo --suggest
```

### 4. Legacy Full Clone
If you need the actual raw code files (e.g. for execution), use `--clone`.
```bash
python main.py "query" --github-repo owner/large-repo --clone
```

## GraphQL Optimization
The tool now uses GitHub's GraphQL API to fetch file contents in batches (50 files/request). This significantly reduces HTTP overhead and rate limit usage compared to standard REST API calls.

## Structure
- `main.py`: CLI entry point. Orchestrates the flow: **Context -> Cache -> Search -> Answer**.
- `agentic_search/`:
    - `llm_client.py`: LLM integration (OpenAI). Handles context analysis and query generation.
    - `tools/`:
        - `markdown_repo_manager.py`: Handles fetching repo content via API and caching as Markdown.
        - `search_tool.py`: Wrapper for local `ripgrep`.
