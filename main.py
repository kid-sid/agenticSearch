import argparse
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from agentic_search.tools.search_tool import SearchTool
from agentic_search.tools.repo_manager import RepoManager
from agentic_search.tools.markdown_repo_manager import MarkdownRepoManager
from agentic_search.llm_client import LLMClient
from agentic_search.history_manager import HistoryManager

# Force UTF-8 for stdout/stderr (fixes Windows console encoding issues)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="Agentic Search Tool")
    parser.add_argument("question", nargs="?", help="The question you want to ask about the codebase.")
    parser.add_argument("--path", default=".", help="Root path to search in (for local search).")
    parser.add_argument("--github-repo", help="GitHub repo to search (e.g., 'owner/repo'). Overrides local path.")
    parser.add_argument("--provider", default="mock", help="LLM Provider to use (default: mock).")
    parser.add_argument("--reset", action="store_true", help="Reset conversation history.")
    parser.add_argument("--clone", action="store_true", help="Use full git clone (legacy behavior). Default is markdown cache.")
    parser.add_argument("--suggest", action="store_true", help="Generate sample questions based on the codebase context.")
    
    args = parser.parse_args()

    # 1. Initialize Components
    llm = LLMClient(provider=args.provider)
    history_mgr = HistoryManager()

    if args.reset:
        history_mgr.clear_history()
        print("Conversation history reset.")
        if not args.question: # Allow running just with --reset
            return

    print(f"Analyzing question: '{args.question}'...")
    
    # Get recent history for context
    history_context = history_mgr.get_recent_context()
    
    search_path = args.path
    
    project_context = ""
    
    if args.github_repo:
        if args.clone:
            # Legacy Clone Mode
            print(f"Mode: GitHub Search ({args.github_repo}) - Git Clone")
            repo_mgr = RepoManager()
            try:
                search_path = repo_mgr.sync_repo(args.github_repo)
            except Exception as e:
                print(f"Error syncing repo: {e}")
                sys.exit(1)
        else:
            # Context-Aware Markdown Mode
            print(f"Mode: GitHub Search ({args.github_repo}) - Context-Aware Markdown Cache")
            token = os.getenv("GITHUB_TOKEN")
            if not token:
                print("Error: GITHUB_TOKEN required for Markdown Cache mode.")
                sys.exit(1)
            # Simple debug (masked)
            print(f"Debug: Using GITHUB_TOKEN starting with {token[:4]}...")
                
            repo_mgr = MarkdownRepoManager(token=token, cache_dir=".cache")

            if args.suggest:
                print(f"Generating suggested questions for {args.github_repo}...")
                cached_path = repo_mgr.get_cache_path(args.github_repo)
                context = ""
                
                if cached_path:
                    try:
                        print(f"Reading local cache: {cached_path}...")
                        with open(os.path.join(cached_path, "full_codebase.md"), "r", encoding="utf-8") as f:
                            context = f.read()
                    except Exception as e:
                        print(f"Error reading cache: {e}")
                else:
                    print("Repo not cached. Fetching README for context...")
                    context = repo_mgr.fetch_readme(args.github_repo)
                
                if context:
                    print("Asking LLM to generate questions...")
                    questions = llm.generate_questions(context)
                    print("\n=== Suggested Questions & Answers ===\n")
                    print(questions)
                    print("\n=====================================\n")
                else:
                    print("Error: Could not retrieve any context (Cache or README) to generate questions.")
                
                return # Exit after suggestions
            
            # Check if already cached
            cached_path = repo_mgr.get_cache_path(args.github_repo)
            
            if cached_path:
                print(f"Mode: Using Cached Repo ({cached_path})")
                print("Step 1/2: Reading Local Context...")
                try:
                    # Read context from cache
                    readme_part = repo_mgr.get_local_context(args.github_repo)
                    if readme_part:
                        print("Step 2/2: Analyzing Project Context...")
                        project_context = llm.analyze_project_context(readme_part)
                        if project_context:
                            print(f" Context Derived: {project_context[:100].replace(chr(10), ' ')}...")
                except Exception as e:
                    print(f"Warning: Could not read local context: {e}")
                
                search_path = cached_path
                
            else:
                # Not cached, perform full sync flow
                # 1. Fetch & Analyze README (Fast)
                print("Step 1/4: Fetching README (API)...")
                readme_content = repo_mgr.fetch_readme(args.github_repo)
                
                if readme_content:
                    print("Step 2/4: Analyzing Project Context...")
                    project_context = llm.analyze_project_context(readme_content)
                    if project_context:
                        print(f" Context Derived: {project_context[:100].replace(chr(10), ' ')}...")
                else:
                    print("Warning: No README found. Proceeding without context.")
    
                # 2. Sync Repo (Slow)
                print("Step 3/4: Caching Repository (API)...")
                try:
                    search_path = repo_mgr.sync_repo(args.github_repo)
                except Exception as e:
                    print(f"Error syncing repo: {e}")
                    sys.exit(1)
            
        print(f"Searching in cached repo at: {search_path}")
            
    else:
        # Local Search Mode
        print(f"Mode: Local Search ({search_path})")
        
    # 3. Setup Searcher
    rg_path = "rg"
    searcher = SearchTool(executable_path=rg_path)

    if not searcher.is_available():
        print("Error: 'rg' (ripgrep) is not found in your PATH.")
        sys.exit(1)

    # 4. Generate Search Queries (using derived context)
    print("Generating Queries & Searching...")
    queries = llm.generate_search_queries(args.question, tool="ripgrep", history=history_context, project_context=project_context)
    print(f"Generated search queries: {queries}")

    if not queries:
        print("No search queries generated. Exiting.")
        return

    # 4. Execute Searches
    all_results = []
    for query in queries:
        print(f"Searching for: {query}")
        results = searcher.search(query, search_path=search_path)
        all_results.extend(results)

    print(f"Found {len(all_results)} matches.")

    # 5. Synthesize Answer
    # Deduplicate results or format them for context
    context_lines = []
    seen = set()
    for r in all_results:
        key = (r['file'], r['line_number'])
        if key not in seen:
            seen.add(key)
            context_lines.append(f"File: {r['file']}, Line: {r['line_number']}\nContent: {r['content']}")
    
    full_context = "\n\n".join(context_lines)
    
    # Limit context size if necessary (placeholder logic)
    if len(full_context) > 10000:
        full_context = full_context[:10000] + "...(truncated)"

    print("Synthesizing answer...")
    answer = llm.answer_question(args.question, full_context, history=history_context)
    
    print("\n=== ANSWER ===\n")
    print(answer)
    
    # 6. Save Interaction
    history_mgr.add_interaction(args.question, answer)

if __name__ == "__main__":
    main()
