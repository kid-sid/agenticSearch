from typing import Dict
import json
from openai import OpenAI

class AnswerVerifier:
    """
    Verifies the generated answer against the provided codebase context.
    Checks for factual accuracy, hallucinations, and completeness.
    """

    def __init__(self, client: OpenAI, model: str = "gpt-4o-mini"):
        self.client = client
        self.model = model

    def verify(self, question: str, answer: str, context: str) -> Dict:
        """
        Verifies the answer and returns a verdict and reasoning.
        """
        prompt = f"""
You are an expert technical auditor. Your task is to verify an answer provided by an AI assistant based strictly on the provided codebase context.

User Question: {question}
AI Answer: {answer}

Codebase Context:
{context[:10000]}

Evaluate the answer based on the following criteria:
1. **Factual Accuracy**: Is the answer correct according to the context?
2. **Hallucination**: Does the answer mention things not found in the context?
3. **Completeness**: Does it fully address the user's question?

Format your response as a JSON object with the following keys:
- "verdict": "PASS", "FAIL", or "PARTIAL"
- "confidence_score": (float between 0 and 1)
- "reasoning": (concise explanation of your evaluation)
- "suggested_correction": (optional, if FAIL or PARTIAL)

JSON Response:
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that verifies technical answers and returns only JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"Error during verification: {e}")
            return {
                "verdict": "ERROR",
                "reasoning": f"Verification failed due to an error: {e}",
                "confidence_score": 0.0
            }
