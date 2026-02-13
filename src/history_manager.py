import json
import os
from typing import List, Dict

class HistoryManager:
    def __init__(self, history_file: str = ".history.json"):
        self.history_file = history_file
        self.history: List[Dict[str, str]] = []
        self._load()

    def _load(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except json.JSONDecodeError:
                self.history = []

    def _save(self):
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, indent=2)

    def clear_history(self):
        self.history = []
        if os.path.exists(self.history_file):
            os.remove(self.history_file)

    def add_interaction(self, question: str, answer: str):
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})
        # Keep last 10 messages (5 interactions) to avoid infinite growth
        if len(self.history) > 10:
            self.history = self.history[-10:]
        self._save()

    def get_recent_context(self, limit: int = 5) -> List[Dict[str, str]]:
        """Returns the last 'limit' messages for LLM context."""
        return self.history[-limit:]
