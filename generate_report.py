
import os
import re
import json

TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")

# Ground Truth from cleanup_tests.py
EXPECTED = {
    1: "Supabase",
    2: "gpt-3.5-turbo (Lazy mode) and gpt-4o (Pro mode)",
    3: "Port 8001",
    4: "RateLimiter class using sliding window of timestamps, 60 req/min OpenAI, 100 req/min auth",
    5: "Redis",
    6: "Goes to /optimize-prompt, checks Redis cache, routes to lazy/pro inference, calls OpenAI, caches result",
    7: "JWT tokens with access_token and refresh_token from Supabase. Stored in localStorage on frontend",
    8: "Min 8 chars, uppercase+lowercase+digit required, checks against common passwords",
    9: "Lazy: gpt-3.5-turbo, 250 tokens, 0.3 temp. Pro: gpt-4o, 2500 tokens, 0.7 temp with chain-of-thought",
    10: "Toggle checkbox, localStorage for theme preference, data-theme attribute on HTML element",
    11: "Redis cache_prompt_history/get_prompt_history methods per user, 7-day TTL, max 50 entries. But NOT wired up in inference_router.",
    12: "Login attempts tracked per email, max 5 in 5 min triggers lockout. Rate limiting at 100 req/min.",
    13: "OpenAI: client.models.list(). Supabase: auth.get_user(). Both raise RuntimeError on failure.",
    14: "Supabase profiles table: id (UUID), email, created_at, status, last_login. RLS policies.",
    15: "helpers.py maps errors: rate limit->429, auth->401, quota->402, model not found->400, default->500",
    16: "Yes, Redis optional. RedisService handles failures gracefully. Inference still works without cache.",
    17: "Yes, _validate_jwt_and_get_user is a stub returning mock user regardless of token. Security vulnerability.",
    18: "Token counting (shows 0), prompt history not wired, user dashboard, batch processing, analytics, etc.",
    19: "MD5 hash of prompt:inference_type, prefix prompt_optimization:, TTL 24 hours (86400s).",
    20: "CORS allows ALL origins (*), ALL methods, ALL headers, credentials=True. NOT secure for production.",
}

QUESTIONS = [
    "Which database is the project using?",
    "What AI models does the application use?",
    "What port does the server run on?",
    "How is rate limiting implemented?",
    "What caching technology is used?",
    "What happens when a user submits a prompt for optimization?",
    "How are authentication tokens managed?",
    "What validation is performed on user passwords?",
    "What is the difference between Lazy and Pro inference modes?",
    "How does the frontend handle theme switching?",
    "How does the app store conversation history?",
    "What security measures prevent brute force attacks?",
    "How does the system verify it can talk to external services on startup?",
    "What data is persisted about user profiles and where?",
    "How does the app handle OpenAI API errors?",
    "What happens if Redis is unavailable - does the app still work?",
    "Is there a bug in the JWT token validation?",
    "What features are planned but not yet implemented?",
    "How is the prompt cache key generated and what is the TTL?",
    "What CORS configuration is used and is it secure for production?",
]

def get_difficulty(q_num):
    if 1 <= q_num <= 5: return "EASY"
    if 6 <= q_num <= 10: return "MEDIUM"
    if 11 <= q_num <= 15: return "HARD"
    return "VERY_HARD"

def extract_content(content):
    # Extract only the answer part, removing header and footer
    parts = content.split("## Answer")
    if len(parts) > 1:
        answer = parts[1].strip()
        # Remove [STDERR] if present (should be clean now, but safe to check)
        stderr_idx = answer.find("[STDERR]")
        if stderr_idx != -1:
            answer = answer[:stderr_idx].strip()
        return answer
    return content

def main():
    report_lines = []
    report_lines.append("# Final Pipeline Comparison Report\n")
    report_lines.append("| ID | Difficulty | Question | Your Answer (Pipeline) | My Answer (Ground Truth) | Comments |\n")
    report_lines.append("|---|---|---|---|---|---|\n")

    for q_num in range(1, 21):
        diff = get_difficulty(q_num)
        filename = f"Q{q_num:02d}_{diff}.md"
        filepath = os.path.join(TESTS_DIR, filename)
        
        your_answer_summary = "MISSING"
        comments = "Not run"
        
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                full_answer = extract_content(content)
                # First 200 chars for table summary
                your_answer_summary = full_answer[:200].replace("\n", " ") + "..."
                
                # Basic validation (same logic as cleanup_tests.py essentially)
                expected_keywords = EXPECTED[q_num].lower().split()
                matches = sum(1 for w in expected_keywords if w in full_answer.lower())
                score = (matches / len(expected_keywords)) * 100 if expected_keywords else 0
                
                if score > 70:
                    comments = "✅ Pass"
                elif score > 40:
                    comments = "⚠️ Partial"
                else:
                    comments = "❌ Review"
        
        row = f"| Q{q_num:02d} | {diff} | {QUESTIONS[q_num-1]} | {your_answer_summary} | {EXPECTED[q_num]} | {comments} |\n"
        report_lines.append(row)

    report_lines.append("\n\n## Detailed Comparisons\n")
    
    for q_num in range(1, 21):
        diff = get_difficulty(q_num)
        filename = f"Q{q_num:02d}_{diff}.md"
        filepath = os.path.join(TESTS_DIR, filename)
        
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                full_answer = extract_content(content)
                
            report_lines.append(f"### Q{q_num}: {QUESTIONS[q_num-1]}\n")
            report_lines.append(f"**My Answer (Ground Truth):**\n> {EXPECTED[q_num]}\n\n")
            report_lines.append(f"**Your Answer (Pipeline):**\n{full_answer}\n\n")
            report_lines.append("---\n")

    with open("final_report.md", "w", encoding="utf-8") as f:
        f.writelines(report_lines)
    
    print("Report generated: final_report.md")

if __name__ == "__main__":
    main()
