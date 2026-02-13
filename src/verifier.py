from typing import Dict
import json
from openai import OpenAI

from src.prompts import verify_answer_prompt

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
        prompt = verify_answer_prompt(question, answer, context)

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
