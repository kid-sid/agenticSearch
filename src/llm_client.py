from typing import List, Dict
import re
import os
import sys
import json
from openai import OpenAI

class LLMClient:
    def __init__(self, provider: str = "mock"):
        self.provider = provider
        self.api_key = None
        self.client = None
        if self.provider == "openai":
            self.api_key = os.getenv("OPENAI_API_KEY")
            if self.api_key:
                self.client = OpenAI(api_key=self.api_key)
            else:
                print("Warning: OPENAI_API_KEY not set. LLM calls will fail.")
        
    def identify_relevant_files(self, user_question: str, file_structure: str) -> List[str]:
        """
        Skeleton-first analysis: Given a project file tree, identify the files
        most likely to contain the answer to the user's question.
        Returns a list of 3-8 file paths.
        """
        if self.provider == "mock":
            return []

        prompt = f"""You are an expert developer. Given this project file structure, identify which files are MOST LIKELY to contain the answer to the user's question.

Project Structure:
```
{file_structure}
```

Question: {user_question}

RULES:
- Return 3-8 file paths that are most relevant
- Prioritize source code files (.py, .js, .ts) over docs/tests
- For questions about configuration, constants, or specific model names/ports, ALWAYS include 'config.py' or equivalent config files.
- For questions about data storage, caching, or history, ALWAYS include relevant service files (e.g., 'services/redis.py', 'services/database.py') even if the feature sounds missing.
- For questions about security/auth, include auth-related files  
- For questions about features, include the main app file AND relevant service files
- For questions about CORS, middleware, or server config, ALWAYS include main.py
- Think about which files a developer would open to answer this question

Return ONLY JSON array of file paths, no explanation. Example:
["services/auth_service.py", "routes/auth_router.py", "config.py"]"""

        if self.provider == "openai" and self.client:
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "You are a helpful assistant. Return ONLY valid JSON."},
                              {"role": "user", "content": prompt}],
                    temperature=0.1
                )
                content = response.choices[0].message.content.strip()
                
                # Robust JSON extraction
                match = re.search(r'\[.*\]', content, re.DOTALL)
                if match:
                    json_str = match.group(0)
                    try:
                        files = json.loads(json_str)
                        if isinstance(files, list):
                            print(f"[Skeleton] Identified {len(files)} relevant files: {files}")
                            return files[:8]
                    except json.JSONDecodeError as e:
                        print(f"[Skeleton] Warning: JSON Decode Error: {e}")
                else:
                    print(f"[Skeleton] Warning: No JSON list found in response: {content[:100]}...")
            except Exception as e:
                print(f"[Skeleton] Warning: Could not parse file list: {e}. Raw content: {content[:100]}...")
                return []

        return []

    def generate_search_queries(self, user_question: str, tool: str = "ripgrep", history: List[Dict] = None, project_context: str = "", file_structure: str = "") -> List[str]:
        """
        Generates search queries based on the user's question and optional history.
        Now accepts file_structure to generate more targeted queries.
        """
        if self.provider == "mock":
            words = user_question.split()
            return [w for w in words if len(w) > 3]

        # Format history for prompt
        history_str = ""
        if history:
            history_str = "Conversation History:\n" + "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history]) + "\n"

        structure_hint = ""
        if file_structure:
            structure_hint = f"""\nProject File Structure:
```
{file_structure[:2000]}
```
Use this structure to generate targeted queries. For example, if you see 'services/auth_service.py', search for function names or patterns likely in that file.\n"""
            
        if tool == "github":
             prompt = f"Search query for {user_question}"
        else:
             prompt = f"""
You are an expert developer assistant. Your task is to generate 5-10 search queries to find code relevant to the user's question.
Target tool: ripgrep (regex supported).

Project Context (Summary):
{project_context}
{structure_hint}
Strategies:
1.  **Simple Keywords**: Start with broad, single-word terms (e.g., 'platform', 'linux', 'windows', 'support').
2.  **Code Patterns**: Search for class names, function definitions, variable assignments related to the question.
3.  **Exact Matches**: Look for exact string literals if the user asks for a specific message or error.
4.  **Synonyms**: Include synonyms and related terms (e.g., for 'brute force' also search 'login_attempt', 'lockout', 'blocked').
5.  **Configuration Patterns**: For config questions, search for middleware, env vars, constants (e.g., 'CORSMiddleware', 'allow_origins').
6.  **Avoid Complex Regex**: Do NOT use complex regex (like `.*`) unless searching for a strict code pattern. Prefer simple substrings.

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

        return "Error: LLM provider not configured or unavailable."

    def answer_code_question(self, user_question: str, context: str,
                              call_graph_context: str = "",
                              project_structure: str = "",
                              skeleton_context: str = "",
                              history: List[Dict] = None) -> str:
        """
        Code-aware answer synthesis with call graph and structure context.
        Designed for GitHub repo search where function relationships matter.
        Now includes skeleton_context listing which files were specifically targeted.
        """
        if self.provider == "mock":
            return f"[Code-Aware Mock Answer for '{user_question}']"

        history_str = ""
        if history:
            history_str = "Conversation History:\n"
            for msg in history:
                history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"
            history_str += "\n"

        structure_section = ""
        if project_structure:
            structure_section = f"""
Project Structure:
```
{project_structure[:5000]}
```
"""

        graph_section = ""
        if call_graph_context:
            graph_section = f"""
Call Graph Analysis:
{call_graph_context}
"""

        skeleton_section = ""
        if skeleton_context:
            skeleton_section = f"""
Targeted Files Analysis:
The following files were identified as most relevant to this question. Pay special attention to code from these files:
{skeleton_context}
"""

        prompt = f"""You are an expert code analyst. Answer the user's question using the provided code context, call graph, and project structure.

ANALYSIS STRATEGY:
1. **Targeted Files First**: Start by analyzing the code from the specifically targeted files — these were identified as most relevant.
2. **Context Awareness**: Understand where each code snippet fits in the project architecture.
3. **Function Relationships**: Use the call graph to trace which functions interact with each other.
4. **Call Chain Tracing**: When a function is relevant, identify what it calls (downstream) and what calls it (upstream).
5. **Root Cause Identification**: If the question is about a bug or issue, trace the dependency chain to find the actual source — not just the symptom.
6. **Look for Stubs/Mocks/TODOs/Dead Code**: 
   - Carefully check for stub implementations, TODO comments, hardcoded test values, or mock returns.
   - Even if a feature is marked as 'missing' in a README, check if service methods exist but are not 'wired up' (called) in the routes.
7. **Find Hardcoded Constants**: For questions about specific values (model names, ports, expirations), look for the actual string or integer definitions in config files, not just the setting variable name.

RULES:
- Always cite the file path and line numbers for your answer.
- If you find a function is causing an issue, trace its callers and callees to explain the full impact.
- If the answer is not in the context, say so clearly.
- Do NOT hallucinate code that doesn't exist in the context.
- When analyzing security or configuration, examine the ACTUAL values in code (not docs or comments about what they should be).

{history_str}
{structure_section}
{skeleton_section}
{graph_section}

Code Context:
{context}

Question: {user_question}"""

        if self.provider == "openai" and self.client:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are an expert code analyst with deep understanding of software architecture and function dependencies."},
                          {"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content

        return "Error: LLM provider not configured or unavailable."


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
