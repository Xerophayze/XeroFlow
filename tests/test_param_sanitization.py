import unittest
import sys
import types

# Mock external modules not required for sanitization tests before importing api_handler
mock_openai = types.ModuleType("openai")
class _MockOpenAI:  # minimal placeholder
    pass
class _MockOpenAIError(Exception):
    pass
mock_openai.OpenAI = _MockOpenAI
mock_openai.OpenAIError = _MockOpenAIError
sys.modules.setdefault("openai", mock_openai)

mock_ollama = types.ModuleType("ollama")
class _MockOllamaClient:
    pass
mock_ollama.Client = _MockOllamaClient
sys.modules.setdefault("ollama", mock_ollama)

# Import sanitization functions/instances from code under test
from services.api_service import APIService
from api_handler import _sanitize_openai_params as sanitize_openai_params_handler


class TestAPIServiceSanitization(unittest.TestCase):
    def setUp(self):
        # Minimal config; no interfaces needed to test sanitization helpers
        self.service = APIService(config={})

    def test_openai_o3_removes_temperature(self):
        params = {"model": "o3-mini", "messages": [], "temperature": 0.5}
        sanitized = self.service._sanitize_params("openai", "o3-mini", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_openai_o3_plain_removes_temperature(self):
        params = {"model": "o3", "messages": [], "temperature": 0.8}
        sanitized = self.service._sanitize_params("openai", "o3", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_openai_gpt5_removes_temperature_when_non_default(self):
        params = {"model": "gpt-5.1", "messages": [], "temperature": 0.7}
        sanitized = self.service._sanitize_params("openai", "gpt-5.1", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_openai_gpt5_omits_temperature_even_if_default(self):
        params = {"model": "gpt-5.1", "messages": [], "temperature": 1}
        sanitized = self.service._sanitize_params("openai", "gpt-5.1", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_openai_other_model_keeps_temperature(self):
        params = {"model": "gpt-4.1-mini", "messages": [], "temperature": 0.3}
        sanitized = self.service._sanitize_params("openai", "gpt-4.1-mini", params.copy())
        self.assertIn("temperature", sanitized)
        self.assertEqual(sanitized["temperature"], 0.3)


class TestApiHandlerSanitization(unittest.TestCase):
    def test_o3_removes_temperature(self):
        params = {"model": "o3-mini", "messages": [], "temperature": 0.2}
        sanitized = sanitize_openai_params_handler("o3-mini", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_o3_plain_removes_temperature(self):
        params = {"model": "o3", "messages": [], "temperature": 0.2}
        sanitized = sanitize_openai_params_handler("o3", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_gpt5_removes_temperature(self):
        params = {"model": "gpt-5.1", "messages": [], "temperature": 0.9}
        sanitized = sanitize_openai_params_handler("gpt-5.1", params.copy())
        self.assertNotIn("temperature", sanitized)

    def test_other_model_keeps_temperature(self):
        params = {"model": "gpt-4.1", "messages": [], "temperature": 0.6}
        sanitized = sanitize_openai_params_handler("gpt-4.1", params.copy())
        self.assertIn("temperature", sanitized)
        self.assertEqual(sanitized["temperature"], 0.6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
