import os
import subprocess
import shutil

class RepoManager:
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = os.path.abspath(cache_dir)
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def sync_repo(self, repo_name: str) -> str:
        """
        Clones or updates the given repo (e.g., "owner/repo") in the cache directory.
        Returns the absolute path to the local copy.
        """
        # Sanitization: owner/repo -> owner_repo
        # Also strip /tree/main if present
        if "/tree/" in repo_name:
            repo_name = repo_name.split("/tree/")[0]
        
        safe_name = repo_name.replace("/", "_").replace("\\", "_")
        repo_path = os.path.join(self.cache_dir, safe_name)
        
        repo_url = f"https://github.com/{repo_name}.git"

        if os.path.exists(repo_path):
            # Check if it's a git repo
            if os.path.exists(os.path.join(repo_path, ".git")):
                print(f"[RepoManager] Updating existing repo: {repo_name}...")
                try:
                    subprocess.run(["git", "pull"], cwd=repo_path, check=True, capture_output=True)
                    print(f"[RepoManager] Updated {repo_name}.")
                except subprocess.CalledProcessError as e:
                    print(f"[RepoManager] Warning: Failed to pull '{repo_name}'. Using existing state. Error: {e}")
            else:
                print(f"[RepoManager] Directory exists but not a git repo. Re-cloning...")
                shutil.rmtree(repo_path)
                self._clone(repo_url, repo_path)
        else:
            print(f"[RepoManager] Cloning new repo: {repo_name}...")
            self._clone(repo_url, repo_path)
            
        return repo_path

    def _clone(self, url: str, path: str):
        try:
            subprocess.run(["git", "clone", "--depth", "1", url, path], check=True)
            print(f"[RepoManager] Cloned {url} to {path}.")
        except subprocess.CalledProcessError as e:
            print(f"[RepoManager] Error cloning {url}: {e}")
            raise
