"""
Test Runner: Runs all 20 questions from test_questions.md against the pipeline
and saves results to tests/ folder.

Usage:
    python run_tests.py --github-repo kid-sid/reprompt
"""

import subprocess
import os
import sys
import re
import time
import json

# All 20 test questions
QUESTIONS = [
    # EASY (Q1-Q5)
    "Which database is the project using?",
    "What AI models does the application use?",
    "What port does the server run on?",
    "How is rate limiting implemented?",
    "What caching technology is used?",
    # MEDIUM (Q6-Q10)
    "What happens when a user submits a prompt for optimization?",
    "How are authentication tokens managed?",
    "What validation is performed on user passwords?",
    "What is the difference between Lazy and Pro inference modes?",
    "How does the frontend handle theme switching?",
    # HARD (Q11-Q15)
    "How does the app store conversation history?",
    "What security measures prevent brute force attacks?",
    "How does the system verify it can talk to external services on startup?",
    "What data is persisted about user profiles and where?",
    "How does the app handle OpenAI API errors?",
    # VERY HARD (Q16-Q20)
    "What happens if Redis is unavailable - does the app still work?",
    "Is there a bug in the JWT token validation?",
    "What features are planned but not yet implemented?",
    "How is the prompt cache key generated and what is the TTL?",
    "What CORS configuration is used and is it secure for production?",
]

DIFFICULTY = {
    1: "EASY", 2: "EASY", 3: "EASY", 4: "EASY", 5: "EASY",
    6: "MEDIUM", 7: "MEDIUM", 8: "MEDIUM", 9: "MEDIUM", 10: "MEDIUM",
    11: "HARD", 12: "HARD", 13: "HARD", 14: "HARD", 15: "HARD",
    16: "VERY_HARD", 17: "VERY_HARD", 18: "VERY_HARD", 19: "VERY_HARD", 20: "VERY_HARD",
}

def extract_final_answer(output: str) -> str:
    """Extract only the FINAL ANSWER section from pipeline output."""
    marker = "=== FINAL ANSWER ==="
    idx = output.find(marker)
    if idx != -1:
        return output[idx + len(marker):].strip()
    # Fallback: return last 2000 chars
    return output[-2000:].strip()

def run_question(question: str, repo: str, skip_verify: bool = False) -> str:
    """Run a single question through the pipeline."""
    cmd = [
        sys.executable, "main.py",
        question,
        "--github-repo", repo,
        "--skip-verify" if skip_verify else "",
    ]
    # Remove empty strings
    cmd = [c for c in cmd if c]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,  # 5 min timeout per question
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return result.stdout + ("\n[STDERR]\n" + result.stderr if result.stderr else "")
    except subprocess.TimeoutExpired:
        return "[ERROR] Timeout after 300 seconds"
    except Exception as e:
        return f"[ERROR] {str(e)}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run test questions against pipeline")
    parser.add_argument("--github-repo", default="kid-sid/reprompt", help="GitHub repo to test against")
    parser.add_argument("--skip-verify", action="store_true", help="Skip verification step for speed")
    parser.add_argument("--start-from", type=int, default=1, help="Start from question N (1-indexed)")
    parser.add_argument("--only", type=int, help="Run only question N")
    args = parser.parse_args()

    # Create tests directory
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    os.makedirs(tests_dir, exist_ok=True)

    results = {}
    total_time = 0

    # Determine which questions to run
    if args.only:
        indices = [args.only - 1]
    else:
        indices = list(range(args.start_from - 1, len(QUESTIONS)))

    print(f"\n{'='*70}")
    print(f"  RUNNING {len(indices)} QUESTIONS AGAINST: {args.github_repo}")
    print(f"{'='*70}\n")

    for i in indices:
        q_num = i + 1
        question = QUESTIONS[i]
        difficulty = DIFFICULTY[q_num]

        print(f"\n[Q{q_num:02d}/{len(QUESTIONS)}] [{difficulty}] {question}")
        print("-" * 60)

        start = time.time()
        raw_output = run_question(question, args.github_repo, args.skip_verify)
        elapsed = time.time() - start
        total_time += elapsed

        final_answer = extract_final_answer(raw_output)

        # Save individual result
        filename = f"Q{q_num:02d}_{difficulty}.md"
        filepath = os.path.join(tests_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Q{q_num}: {question}\n")
            f.write(f"**Difficulty:** {difficulty}\n")
            f.write(f"**Time:** {elapsed:.1f}s\n\n")
            f.write(f"## Answer\n\n")
            f.write(final_answer)
            f.write("\n")

        print(f"  Saved: {filename} ({elapsed:.1f}s)")
        print(f"  Preview: {final_answer[:150]}...")

        results[q_num] = {
            "question": question,
            "difficulty": difficulty,
            "time_seconds": round(elapsed, 1),
            "answer_length": len(final_answer),
            "answer_preview": final_answer[:200],
            "has_error": "[ERROR]" in final_answer,
        }

    # Save summary JSON
    summary = {
        "repo": args.github_repo,
        "total_questions": len(indices),
        "total_time_seconds": round(total_time, 1),
        "results": results,
    }
    summary_path = os.path.join(tests_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Generate comparison report
    report_lines = []
    report_lines.append(f"# Test Results Summary")
    report_lines.append(f"**Repo:** {args.github_repo}")
    report_lines.append(f"**Total Time:** {total_time:.1f}s ({total_time/60:.1f} min)")
    report_lines.append(f"**Questions Run:** {len(indices)}")
    report_lines.append("")
    report_lines.append("| # | Difficulty | Question | Time | Answer Length | Error? |")
    report_lines.append("|---|-----------|----------|------|---------------|--------|")

    for q_num, data in sorted(results.items()):
        err = "❌" if data["has_error"] else "✅"
        report_lines.append(
            f"| Q{q_num:02d} | {data['difficulty']} | {data['question'][:50]}... | {data['time_seconds']}s | {data['answer_length']} chars | {err} |"
        )

    report_lines.append("")
    report_lines.append("## Per-Difficulty Breakdown")
    for diff in ["EASY", "MEDIUM", "HARD", "VERY_HARD"]:
        diff_results = {k: v for k, v in results.items() if v["difficulty"] == diff}
        if diff_results:
            avg_time = sum(v["time_seconds"] for v in diff_results.values()) / len(diff_results)
            errors = sum(1 for v in diff_results.values() if v["has_error"])
            report_lines.append(f"- **{diff}**: {len(diff_results)} questions, avg {avg_time:.1f}s, {errors} errors")

    report_path = os.path.join(tests_dir, "comparison_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\n{'='*70}")
    print(f"  ALL DONE! Results saved to: {tests_dir}")
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"  Summary: {summary_path}")
    print(f"  Report:  {report_path}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
