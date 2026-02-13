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

    def _generate_tree_structure(self, tree: List[Dict]) -> str:
        """Converts GitHub tree data into an ASCII tree string."""
        paths = sorted([x["path"] for x in tree])
        
        # Build nested dict structure
        root = {}
        for path in paths:
            parts = path.split('/')
            curr = root
            for part in parts:
                if part not in curr:
                    curr[part] = {}
                curr = curr[part]

        lines = []
        def walk(node, prefix=""):
            items = sorted(node.keys())
            for i, name in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{name}")
                
                new_prefix = prefix + ("    " if is_last else "│   ")
                walk(node[name], new_prefix)

        walk(root)
        return "\n".join(lines)

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
            # 1. Get default branch
            repo_info_url = f"https://api.github.com/repos/{repo_name}"
            print(f"[MD Manager] Resolving default branch...")
            info_resp = requests.get(repo_info_url, headers=self.headers)
            branch = "main"
            if info_resp.status_code == 200:
                branch = info_resp.json().get("default_branch", "main")
            print(f"[MD Manager] Default branch is '{branch}'")

            tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{branch}?recursive=1"
            print(f"[MD Manager] Fetching file tree...")
            resp = requests.get(tree_url, headers=self.headers)
            
            if resp.status_code == 403:
                print(f"[MD Manager] Error 403: Rate limit exceeded or invalid token.")
                raise Exception("GitHub API Rate Limit / Auth Error")
                
            if resp.status_code != 200:
                 raise Exception(f"Tree fetch failed: {resp.status_code}")
                 
            tree_data = resp.json().get("tree", [])
            
            # Generate and save project structure
            tree_str = self._generate_tree_structure(tree_data)
            structure_path = os.path.join(repo_dir, "project_structure.txt")
            with open(structure_path, "w", encoding='utf-8') as f:
                f.write(tree_str)
            print(f"[MD Manager] Generated project structure at: {structure_path}")

            blobs = [x for x in tree_data if x["type"] == "blob"]
            
            skip_exts = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.zip', '.exe', '.pyc', '.svg'}
            target_blobs = [b for b in blobs if os.path.splitext(b["path"])[1].lower() not in skip_exts]
            
            print(f"[MD Manager] Syncing {len(target_blobs)} files...")
            
            all_content = []
            batch_size = 50
            batches = [target_blobs[i:i + batch_size] for i in range(0, len(target_blobs), batch_size)]
            
            total_batches = len(batches)
            for i, batch in enumerate(batches):
                print(f"[MD Manager] Fetching batch {i+1}/{total_batches}...")
                batch_content = self._fetch_batch_graphql(repo_name, batch)
                all_content.extend(batch_content)
                import time
                time.sleep(0.5)

            all_content.sort()
            
            full_md_path = os.path.join(repo_dir, "full_codebase.md")
            with open(full_md_path, "w", encoding='utf-8') as f:
                f.write(f"# Codebase Dump for {repo_name}\n\n")
                f.write("## Project Structure\n")
                f.write("```text\n")
                f.write(tree_str)
                f.write("\n```\n\n")
                f.write("## File Contents\n\n")
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

    def _fetch_batch_graphql(self, repo_name: str, blobs: List[Dict]) -> List[str]:
        """
        Fetches a batch of blobs using a single GraphQL query.
        """
        owner, name = repo_name.split("/")
        
        # Build Query
        query_parts = []
        path_map = {}
        
        for idx, blob in enumerate(blobs):
            path = blob["path"]
            alias = f"f{idx}"
            path_map[alias] = path
            # Escape quotes in path just in case
            safe_path = path.replace('"', '\\"')
            query_parts.append(f'{alias}: object(expression: "HEAD:{safe_path}") {{ ... on Blob {{ isBinary text }} }}')
            
        inner_query = "\n".join(query_parts)
        query = f"""
        query {{
            repository(owner: "{owner}", name: "{name}") {{
                {inner_query}
            }}
        }}
        """
        
        url = "https://api.github.com/graphql"
        results = []
        
        try:
            resp = requests.post(url, json={"query": query}, headers=self.headers)
            if resp.status_code != 200:
                print(f"GraphQL Error {resp.status_code}: {resp.text}")
                return []
                
            data = resp.json()
            if "errors" in data:
                # Log first error but try to process partial data
                print(f"GraphQL Errors (Sample): {data['errors'][0].get('message')}")
            
            repo_data = data.get("data", {}).get("repository", {})
            if not repo_data:
                return []
                
            for alias, file_data in repo_data.items():
                if not file_data: continue
                
                if file_data.get("isBinary"):
                    continue
                    
                text = file_data.get("text", "")
                if not text: continue
                
                path = path_map.get(alias, "unknown")
                ext = os.path.splitext(path)[1].lstrip(".")
                if not ext: ext = "text"
                
                # Check for empty content
                if not text.strip(): continue

                md_block = f"# File: {path}\n\n```{ext}\n{text}\n```\n\n"
                results.append(md_block)
                
        except Exception as e:
            print(f"Batch fetch error: {e}")
            
        return results

    def get_cache_path(self, repo_name: str) -> str:
        """Returns the path to the cached repo if it exists, else None."""
        if "/tree/" in repo_name:
            repo_name = repo_name.split("/tree/")[0]
        safe_name = repo_name.replace("/", "_").replace("\\", "_") + "_md"
        repo_dir = os.path.join(self.cache_dir, safe_name)
        full_md = os.path.join(repo_dir, "full_codebase.md")
        if os.path.exists(repo_dir) and os.path.exists(full_md):
            if os.path.getsize(full_md) > 0:
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
