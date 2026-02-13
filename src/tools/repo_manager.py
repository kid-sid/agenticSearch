import os
import subprocess
import shutil

class RepoManager:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = os.path.abspath(cache_dir)
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _generate_local_tree(self, root_path: str) -> str:
        """Generates an ASCII tree for the local repository."""
        skip_dirs = {
            'node_modules', '.git', '.cache', '__pycache__', 'venv', '.venv',
            'dist', 'build', 'target', 'bin', 'obj', 'vendor', '.idea', '.vscode'
        }
        
        lines = []
        def walk(path, prefix=""):
            try:
                items = sorted(os.listdir(path))
            except PermissionError:
                return
                
            filtered_items = [i for i in items if i not in skip_dirs]
            
            for i, name in enumerate(filtered_items):
                full_path = os.path.join(path, name)
                is_last = (i == len(filtered_items) - 1)
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{name}")
                
                if os.path.isdir(full_path):
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    walk(full_path, new_prefix)

        walk(root_path)
        return "\n".join(lines)

    def sync_repo(self, repo_name: str) -> str:
        """
        Clones or updates the given repo (e.g., "owner/repo") in the cache directory.
        Returns the absolute path to the local copy.
        """
        if "/tree/" in repo_name:
            repo_name = repo_name.split("/tree/")[0]
        
        safe_name = repo_name.replace("/", "_").replace("\\", "_")
        repo_path = os.path.join(self.cache_dir, safe_name)
        
        repo_url = f"https://github.com/{repo_name}.git"

        if os.path.exists(repo_path):
            if os.path.exists(os.path.join(repo_path, ".git")):
                print(f"[RepoManager] Updating existing repo: {repo_name}...")
                try:
                    subprocess.run(["git", "pull"], cwd=repo_path, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    print(f"[RepoManager] Warning: Failed to pull '{repo_name}'. Error: {e}")
            else:
                shutil.rmtree(repo_path)
                self._clone(repo_url, repo_path)
        else:
            self._clone(repo_url, repo_path)
            
        # Generate and save project structure
        tree_str = self._generate_local_tree(repo_path)
        structure_path = os.path.join(repo_path, "project_structure.txt")
        with open(structure_path, "w", encoding='utf-8') as f:
            f.write(tree_str)
        print(f"[RepoManager] Generated project structure at: {structure_path}")
            
        return repo_path

    def _clone(self, url: str, path: str):
        try:
            subprocess.run(["git", "clone", "--depth", "1", url, path], check=True)
            print(f"[RepoManager] Cloned {url} to {path}.")
        except subprocess.CalledProcessError as e:
            print(f"[RepoManager] Error cloning {url}: {e}")
            raise
