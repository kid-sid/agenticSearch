import subprocess
import shutil
import os
from typing import List, Dict, Optional
import json

class SearchTool:
    def is_available(self) -> bool:
        return shutil.which(self.executable_path) is not None

    def __init__(self, executable_path: str = "rg"):
        self.executable_path = executable_path
        
        # Check standard PATH
        if not self.is_available():
            # Check known fallback locations
            user_profile = os.environ.get("USERPROFILE", "")
            fallback_path = os.path.join(user_profile, r"AppData\Local\Microsoft\WinGet\Packages\BurntSushi.ripgrep.MSVC_Microsoft.Winget.Source_8wekyb3d8bbwe\ripgrep-15.1.0-x86_64-pc-windows-msvc\rg.exe")
            
            if os.path.exists(fallback_path):
                self.executable_path = fallback_path
                # Silent adoption of fallback
            else:
                print(f"Warning: '{self.executable_path}' not found in PATH.")

    def search(self, query: str, search_path: str = ".", extra_args: Optional[List[str]] = None) -> List[Dict]:
        """
        Executes ripgrep with the given query in the search_path.
        Returns a list of results.
        """
        if not self.is_available():
            raise FileNotFoundError(f"ripgrep executable '{self.executable_path}' not found.")

        # Construct command: rg --json <query> <path>
        cmd = [self.executable_path, "--json", "-i", query, search_path]
        if extra_args:
            cmd.extend(extra_args)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8', errors='replace')
        except Exception as e:
            return [{"error": str(e)}]

        parsed_results = []
        for line in result.stdout.splitlines():
            try:
                data = json.loads(line)
                if data["type"] == "match":
                    # Extract relevant info
                    match_data = data["data"]
                    parsed_results.append({
                        "file": match_data["path"]["text"],
                        "line_number": match_data["line_number"],
                        "content": match_data["lines"]["text"].strip()
                    })
            except json.JSONDecodeError:
                continue
        
        return parsed_results
