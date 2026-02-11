from typing import List, Dict
import os
import sys
from openai import OpenAI

class LLMClient:
    def __init__(self, provider: str = "mock"):
        self.provider = provider
        self.api_key = None
        self.client = None
        self.provider = "openai"
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        
    def generate_search_queries(self, user_question: str, tool: str = "ripgrep", history: List[Dict] = None, project_context: str = "") -> List[str]:
        """
        Generates search queries based on the user's question and optional history.
        """
        if self.provider == "mock":
            words = user_question.split()
            return [w for w in words if len(w) > 3]

        # Format history for prompt
        history_str = ""
        if history:
            history_str = "Conversation History:\n" + "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history]) + "\n"
            
        if tool == "github":
             prompt = f"Search query for {user_question}"
        else:
             prompt = f"""
You are an expert developer assistant. Your task is to generate 5-10 search queries to find code relevant to the user's question.
Target tool: ripgrep (regex supported).

Project Context (Summary):
{project_context}

Strategies:
1.  **Simple Keywords**: Start with broad, single-word terms (e.g., 'platform', 'linux', 'windows', 'support').
2.  **Exact Matches**: Look for exact string literals if the user asks for a specific message or error.
3.  **File Names**: Include specific filenames if known (e.g., 'README.md', 'config.json').
4.  **Avoid Complex Regex**: Do NOT use complex regex (like `.*`) unless searching for a strict code pattern (e.g. `def .*method`). Prefer simple substrings.

Format: Return ONLY the search queries, one per line. No bullets, no numbering.

{history_str}
Question: {user_question}
        """

        if self.provider == "openai" and self.client:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a helpful assistant."},
                          {"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content
            content = content.replace("```", "").strip()
            return [line.strip() for line in content.splitlines() if line.strip()]

        return []

    def answer_question(self, user_question: str, context: str, history: List[Dict] = None) -> str:
        if self.provider == "mock":
            return f"Based on the search results, here is the answer to '{user_question}':\n\n[Mock Answer]"

        history_str = ""
        if history:
            history_str = "Conversation History:\n"
            for msg in history:
                history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"
            history_str += "\n"

        prompt = f"""
You are an expert developer assistant. Answer the user's question based strictly on the provided codebase context and the conversation history.
If the answer is not in the context, say so. Do not hallucinate.

{history_str}
Question: {user_question}

Context:
{context}
        """

        if self.provider == "openai" and self.client:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a helpful assistant."},
                          {"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content

    def analyze_project_context(self, readme_content: str) -> str:
        """
        Analyzes the README content to extract key project details for search context.
        """
        if not readme_content:
            return ""
            
        if self.provider == "mock":
            return "Mock Project Context"

        prompt = f"""
You are an expert developer assistant. Analyze the following README content and provide a concise summary to help with code search.
Focus on:
1. Core Functionality & Purpose
2. Key Architectural Components (if mentioned)
3. Important Terminology or Jargon
4. Folder Structure hints (if mentioned)

Keep it under 200 words.

README Content:
{readme_content[:1000]} 
        """

        if self.provider == "openai" and self.client:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a helpful assistant."},
                          {"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content

        return ""

    def generate_questions(self, context: str, num: int = 5) -> str:
        """
        Generates sample questions and answers based on the project context.
        """
        if self.provider == "mock":
            return "1. **Question**: What is this? \n   - **Answer**: A mock project."

        # Truncate context to safe limit (approx 15k tokens) to avoid errors
        # GPT-4o has 128k context, but we want to be cost-effective and safe.
        safe_context = context[:50000] 

        prompt = f"""
You are an expert developer assistant. 
Based on the following project codebase dump, generate {num} insightful technical questions that a new developer might ask to understand the architecture, key features, or usage of this system.
For each question, provide a brief, accurate answer derived ONLY from the provided context.

Format:
1. **Question**: [Question text]
   - **Answer**: [Brief answer]

Context (Truncated):
{safe_context}
        """

        if self.provider == "openai" and self.client:
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "You are a helpful assistant."},
                              {"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            except Exception as e:
                return f"Error generating questions: {e}"

        return "LLM Provider not configured."
