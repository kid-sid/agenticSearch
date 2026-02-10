import requests
import os
from typing import List, Dict, Optional

class GitHubSearchTool:
    def __init__(self, repo_name: str):
        """
        repo_name: "owner/repo" (e.g., "google/guava")
        """
        self.repo_name = repo_name
        self.api_key = os.getenv("GITHUB_TOKEN")
        if not self.api_key:
            print("Warning: GITHUB_TOKEN not found in environment variables.")
            print("Rate limits will be strict, and private repos will be inaccessible.")
        
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"token {self.api_key}"

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/repos/{self.repo_name}", headers=self.headers)
            if resp.status_code == 200:
                return True
            else:
                print(f"Error accessing repo '{self.repo_name}': {resp.status_code} - {resp.reason}")
                return False
        except Exception as e:
            print(f"Error connecting to GitHub: {e}")
            return False

    def search(self, query: str, search_path: str = ".", extra_args: Optional[List[str]] = None) -> List[Dict]:
        """
        Searches the GitHub repository for the query.
        GitHub Code Search API has limitations:
        - Exact match might not be perfect.
        - Requires constructing a specific query string.
        """

        search_query = f"{query} repo:{self.repo_name}"
        
        url = f"{self.base_url}/search/code"
        params = {"q": search_query, "per_page": 5} # Limit to top 5 results per query to avoid noise
        
        print(f"  [GitHub API] Searching for: '{query}'...")
        
        import time
        time.sleep(2)

        try:
            resp = requests.get(url, headers=self.headers, params=params)
                
            if resp.status_code == 403:
                print("  [GitHub API] Rate limit exceeded or access denied.")
                return []
            
            if resp.status_code != 200:
                print(f"  [GitHub API] Error: {resp.status_code}")
                return []

            data = resp.json()
            items = data.get("items", [])
            
            print(f"  [GitHub API] Found {len(items)} items for query '{query}'.")
            
            parsed_results = []
            for item in items:
                file_path = item["path"]
                
                try:
                    content_url = item["url"]
                    content_resp = requests.get(content_url, headers=self.headers)
                    
                    if content_resp.status_code == 200:
                        content_json = content_resp.json()
                        import base64
                        
                        if "content" in content_json and content_json["encoding"] == "base64":
                            file_content = base64.b64decode(content_json["content"]).decode('utf-8', errors='replace')
                            lines = file_content.splitlines()
                            
                            match_count = 0
                            for i, line in enumerate(lines):
                                if query.lower() in line.lower():
                                    parsed_results.append({
                                        "file": file_path,
                                        "line_number": i + 1,
                                        "content": line.strip()
                                    })
                                    match_count += 1
                            if match_count == 0:
                                print(f"    [Debug] Content fetched for {file_path}, but no local string match for '{query}'.")
                        else:
                            print(f"    [Debug] {file_path}: No content or unknown encoding.")
                    else:
                        print(f"    [Debug] Failed to fetch content for {file_path}: {content_resp.status_code}")

                except Exception as e:
                    print(f"    [Debug] Error processing {file_path}: {e}")
            
            if len(parsed_results) == 0:
                print("  [GitHub API] No results from Code Search API. Attempting Deep Search (scan all files)...")
                return self._deep_search(query)
            
            return parsed_results

        except Exception as e:
            print(f"Error during GitHub search: {e}")
            return [{"error": str(e)}]

    def _deep_search(self, query: str) -> List[Dict]:
        """
        Fallback method: Fetches the file tree, downloads relevant files, and searches in-memory.
        Useful for repos not yet indexed by GitHub Code Search.
        """
        try:
            repo_info = requests.get(f"{self.base_url}/repos/{self.repo_name}", headers=self.headers).json()
            branch = repo_info.get("default_branch", "main")
            
            tree_url = f"{self.base_url}/repos/{self.repo_name}/git/trees/{branch}?recursive=1"
            print(f"  [Deep Search] Fetching file tree for {branch}...")
            resp = requests.get(tree_url, headers=self.headers)
            if resp.status_code != 200:
                print(f"  [Deep Search] Failed to get tree: {resp.status_code}")
                return []
            
            tree = resp.json().get("tree", [])
            skip_exts = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.exe', '.pyc'}
            blobs = [x for x in tree if x["type"] == "blob" and os.path.splitext(x["path"])[1].lower() not in skip_exts]
            
            if len(blobs) > 100:
                print(f"  [Deep Search] Warning: Repo has {len(blobs)} files. Deep search might be slow. Limiting to first 100.")
                blobs = blobs[:100]
            
            print(f"  [Deep Search] Scanning {len(blobs)} files...")
            
            results = []
            import concurrent.futures
            import base64

            def fetch_and_search(blob):
                try:
                    b_resp = requests.get(blob["url"], headers=self.headers)
                    if b_resp.status_code == 200:
                        data = b_resp.json()
                        if "content" in data and data["encoding"] == "base64":
                            content = base64.b64decode(data["content"]).decode('utf-8', errors='replace')
                            file_matches = []
                            lines = content.splitlines()
                            for i, line in enumerate(lines):
                                if query.lower() in line.lower():
                                    file_matches.append({
                                        "file": blob["path"],
                                        "line_number": i + 1,
                                        "content": line.strip()
                                    })
                            return file_matches
                except Exception:
                    pass
                return []

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_and_search, b) for b in blobs]
                for f in concurrent.futures.as_completed(futures):
                    results.extend(f.result())
            
            return results

        except Exception as e:
            print(f"  [Deep Search] Error: {e}")
            return []
