import os
import requests
import base64
from typing import List, Dict
import concurrent.futures
import shutil

class MarkdownRepoManager:
    def __init__(self, token: str, cache_dir: str = ".cache"):
        self.token = token
        self.cache_dir = os.path.abspath(cache_dir)
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def sync_repo(self, repo_name: str) -> str:
        """
        Fetches repo content via API and saves as a SINGLE Markdown file in cache.
        Returns the path to the cached directory.
        """
        if "/tree/" in repo_name:
            repo_name = repo_name.split("/tree/")[0]
            
        safe_name = repo_name.replace("/", "_").replace("\\", "_") + "_md"
        repo_dir = os.path.join(self.cache_dir, safe_name)
        
        if os.path.exists(repo_dir):
            print(f"[MD Manager] Clearing existing cache for {repo_name}...")
            shutil.rmtree(repo_dir)
            
        os.makedirs(repo_dir)
        print(f"[MD Manager] initializing cache for {repo_name}...")
            
        try:
            branch = "main"
            tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{branch}?recursive=1"
            print(f"[MD Manager] Fetching file tree...")
            resp = requests.get(tree_url, headers=self.headers)
            
            if resp.status_code == 403:
                print(f"[MD Manager] Error 403: Rate limit exceeded or invalid token.")
                print(f"  - Check your GITHUB_TOKEN.")
                print(f"  - Large repos may hit API limits. Try using '--clone' instead.")
                raise Exception("GitHub API Rate Limit / Auth Error")
                
            if resp.status_code != 200:
                 raise Exception(f"Tree fetch failed: {resp.status_code}")
                 
            tree = resp.json().get("tree", [])
            blobs = [x for x in tree if x["type"] == "blob"]
            
            skip_exts = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.exe', '.pyc', '.svg'}
            target_blobs = [b for b in blobs if os.path.splitext(b["path"])[1].lower() not in skip_exts]
            
            print(f"[MD Manager] Syncing {len(target_blobs)} files...")
            
            all_content = []
            completed = 0
            total = len(target_blobs)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(self._fetch_content, b): b["path"] for b in target_blobs}
                
                for future in concurrent.futures.as_completed(futures):
                    path = futures[future]
                    completed += 1
                    if completed % 100 == 0:
                        print(f"[MD Manager] Fetched {completed}/{total} files...")
                        
                    try:
                        content = future.result()
                        if content:
                            all_content.append(content)
                    except Exception as e:
                        print(f"Failed to fetch {path}: {e}")

            all_content.sort()
            
            full_md_path = os.path.join(repo_dir, "full_codebase.md")
            with open(full_md_path, "w", encoding='utf-8') as f:
                f.write(f"# Codebase Dump for {repo_name}\n\n")
                f.write("\n".join(all_content))
                
            print(f"[MD Manager] Saved single markdown file at: {full_md_path}")
                
        except Exception as e:
            print(f"[MD Manager] Error: {e}")
            
        return repo_dir

    def _fetch_content(self, blob) -> str:
        """Fetches a single blob and returns formatted markdown string."""
        rel_path = blob["path"]
        
        try:
            resp = requests.get(blob["url"], headers=self.headers)
            if resp.status_code == 200:
                data = resp.json()
                content = ""
                if "content" in data and data["encoding"] == "base64":
                    content = base64.b64decode(data["content"]).decode('utf-8', errors='replace')
                    content = content.replace('\x00', '')
                
                ext = os.path.splitext(rel_path)[1].lstrip(".")
                if not ext: ext = "text"
                
                md_block = f"# File: {rel_path}\n\n```{ext}\n{content}\n```\n\n"
                return md_block
        except Exception as e:
            print(f"Error fetching {rel_path}: {e}")
            
        return ""

    def get_cache_path(self, repo_name: str) -> str:
        """Returns the path to the cached repo if it exists, else None."""
        if "/tree/" in repo_name:
            repo_name = repo_name.split("/tree/")[0]
        safe_name = repo_name.replace("/", "_").replace("\\", "_") + "_md"
        repo_dir = os.path.join(self.cache_dir, safe_name)
        if os.path.exists(repo_dir) and os.path.exists(os.path.join(repo_dir, "full_codebase.md")):
            return repo_dir
        return None

    def get_local_context(self, repo_name: str) -> str:
        """
        Extracts README content from the CACHED full_codebase.md file.
        Used when avoiding API calls for already cached repos.
        """
        repo_dir = self.get_cache_path(repo_name)
        if not repo_dir:
            return ""
            
        full_md_path = os.path.join(repo_dir, "full_codebase.md")
        try:
            with open(full_md_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            if "# File: README" in content:
                parts = content.split("# File: README")
                if len(parts) > 1:
                    readme_part = parts[1]
                    if "# File: " in readme_part:
                        readme_part = readme_part.split("# File: ")[0]
                    return readme_part[:10000]
            
            return content[:2000]
            
        except Exception as e:
            print(f"[MD Manager] Error reading local context: {e}")
            return ""

    def fetch_readme(self, repo_name: str) -> str:
        """
        Fetches the README file content directly via API (without full sync).
        """
        if "/tree/" in repo_name:
            repo_name = repo_name.split("/tree/")[0]
            
        print(f"[MD Manager] Fetching README for {repo_name}...")
        try:
            for name in ["README.md", "README", "readme.md", "README.txt"]:
                url = f"https://api.github.com/repos/{repo_name}/contents/{name}"
                resp = requests.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if "content" in data and data["encoding"] == "base64":
                        content = base64.b64decode(data["content"]).decode('utf-8', errors='replace')
                        return content
            
            print("[MD Manager] No README found.")
            return ""
            
        except Exception as e:
            print(f"[MD Manager] Error fetching README: {e}")
            return ""
