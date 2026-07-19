from gemini import GeminiClient
from screen import take_screenshot
from config import MAX_ITERATIONS


class Agent:
    def __init__(self):
        self.client = GeminiClient()
        self.iteration = 0

    def run(self, user_input: str) -> str:
        """Process user input through the agent loop."""
        self.iteration = 0
        print(f"\n[IRA] Processing: {user_input}\n")

        try:
            response = self.client.send_with_screenshot(user_input)
            return self._handle_response(response)
        except Exception as e:
            return f"Error: {str(e)}"

    def _handle_response(self, response_text: str) -> str:
        """Handle the response, potentially executing more tool calls."""
        self.iteration += 1

        if self.iteration >= MAX_ITERATIONS:
            return "Maximum iterations reached. Stopping to prevent infinite loop."

        return response_text

    def chat(self, message: str) -> str:
        """Simple chat without auto-screenshot."""
        try:
            response = self.client.send_message(message)
            return response
        except Exception as e:
            return f"Error: {str(e)}"
