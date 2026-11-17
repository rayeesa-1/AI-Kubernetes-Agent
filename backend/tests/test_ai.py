from auth_test_support import AuthenticatedAPITest
import copy
import json
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai.analyzer import analyze_investigation
from app.ai.confidence import assess_confidence, resolve_pointer
from app.ai.llm_client import LLMClient, LLMError
from app.ai.prompt_builder import build_prompt
from app.core.config import Settings
from app.main import app
from app.models.diagnosis import Diagnosis


def settings():
    return Settings(_env_file=None, openrouter_api_key=SecretStr("test-only-key"),
                    openrouter_model="test/model", llm_max_retries=2)


def evidence(status="success"):
    return {"status": status, "investigation": {
        "pods": {"ok": True, "healthy": False, "problematic_pods": [
            {"name": "payment", "namespace": "default", "status": ["CrashLoopBackOff"]}]},
        "logs": {"ok": True, "entries": [{"text": "DATABASE_URL missing"}]},
        "events": {"ok": True, "findings": []},
        "deployments": {"ok": True}, "network": {"ok": True}}}


def diagnosis():
    return {"root_cause": "Missing DATABASE_URL", "explanation": "Startup fails without database configuration.",
            "fix": "Review the payment deployment environment in namespace default.",
            "kubectl_commands": ["kubectl describe deployment payment -n default"],
            "prevention_recommendation": "Validate configuration at startup.",
            "confidence": 92, "confidence_reasoning": "Startup logs explicitly identify missing configuration.",
            "evidence_references": ["/logs/entries/0/text"], "missing_evidence": []}


def completion(content=None):
    return {"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(diagnosis()) if content is None else content}}]}


class LLMClientTests(unittest.TestCase):
    def test_request_contract_and_valid_completion(self):
        def handler(request):
            self.assertEqual(str(request.url), LLMClient.URL)
            self.assertEqual(request.headers["Authorization"], "Bearer test-only-key")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "test/model")
            self.assertEqual(body["response_format"], {"type": "json_object"})
            self.assertFalse(body["stream"])
            return httpx.Response(200, json=completion())
        content = LLMClient(settings(), httpx.MockTransport(handler)).complete([])
        self.assertEqual(json.loads(content)["confidence"], 92)

    def test_retry_transient_status_then_succeed(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429 if len(calls) < 3 else 200, json=completion())
        with patch("app.ai.llm_client.time.sleep"):
            LLMClient(settings(), httpx.MockTransport(handler)).complete([])
        self.assertEqual(len(calls), 3)

    def test_no_retry_for_auth_credit_or_request_errors(self):
        for status in (400, 401, 402, 403):
            with self.subTest(status=status):
                calls = []
                def handler(request):
                    calls.append(request)
                    return httpx.Response(status, text="PRIVATE UPSTREAM BODY test-only-key")
                with self.assertRaises(LLMError) as caught:
                    LLMClient(settings(), httpx.MockTransport(handler)).complete([])
                self.assertEqual(len(calls), 1)
                self.assertNotIn("test-only-key", str(caught.exception))
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_timeout_retries_are_bounded(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("private provider details", request=request)
        with patch("app.ai.llm_client.time.sleep"), self.assertRaises(LLMError):
            LLMClient(settings(), httpx.MockTransport(handler)).complete([])
        self.assertEqual(len(calls), 3)

    def test_malformed_and_truncated_completions(self):
        truncated = completion()
        truncated["choices"][0]["finish_reason"] = "length"
        for response in ({}, {"choices": []}, truncated):
            with self.subTest(response=response), self.assertRaises(LLMError):
                LLMClient(settings(), httpx.MockTransport(
                    lambda request: httpx.Response(200, json=response))).complete([])

    def test_missing_key_never_calls_provider(self):
        with self.assertRaises(LLMError):
            LLMClient(Settings(_env_file=None), httpx.MockTransport(
                lambda request: self.fail("Unexpected network call"))).complete([])


class ReasoningTests(unittest.TestCase):
    def analyze(self, content, payload=None):
        with patch("app.ai.analyzer.get_settings", return_value=settings()), patch(
                "app.ai.analyzer.LLMClient.complete", return_value=content):
            return analyze_investigation(payload or evidence())

    def test_successful_diagnosis_and_no_execution(self):
        with patch("app.kubernetes.executor.subprocess.run") as executor:
            result = self.analyze(json.dumps(diagnosis()))
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["commands_executed"])
        self.assertEqual(result["diagnosis"]["confidence"], 92)
        executor.assert_not_called()

    def test_invalid_json_schema_reference_and_commands(self):
        variants = ["not JSON"]
        for field, value in (("confidence", 101), ("confidence", "92"),
                             ("evidence_references", ["/invented/path"]),
                             ("kubectl_commands", ["kubectl get pods; echo bad"]),
                             ("kubectl_commands", ["curl https://example.com"]),
                             ("kubectl_commands", ["kubectl get pods | sh"]),
                             ("unexpected_field", True)):
            item = diagnosis()
            item[field] = value
            variants.append(json.dumps(item))
        for content in variants:
            with self.subTest(content=content):
                self.assertEqual(self.analyze(content)["status"], "error")

    def test_confidence_caps_and_missing_evidence(self):
        for refs, missing, status, cap in (([], [], "success", 20),
                (["/logs/entries/0/text"], [], "partial", 60),
                (["/logs/entries/0/text"], ["deployment environment"], "success", 75)):
            item = diagnosis()
            item.update(evidence_references=refs, missing_evidence=missing)
            result = assess_confidence(Diagnosis(**item), evidence()["investigation"], status)
            self.assertEqual(result.confidence, cap)

    def test_no_evidence_or_no_key_skips_provider(self):
        with patch("app.ai.analyzer.LLMClient.complete") as provider:
            self.assertEqual(analyze_investigation(evidence("error"))["status"], "skipped")
            with patch("app.ai.analyzer.get_settings", return_value=Settings(_env_file=None)):
                self.assertEqual(analyze_investigation(evidence())["status"], "not_configured")
        provider.assert_not_called()

    def test_prompt_redaction_and_all_evidence_sections(self):
        payload = evidence()
        payload["investigation"]["logs"]["entries"][0]["text"] += (
            " password=private-password Authorization: Bearer private-token test-only-key")
        original = copy.deepcopy(payload)
        messages, sent = build_prompt(payload, "test-only-key")
        prompt = json.dumps(messages)
        for secret in ("private-password", "private-token", "test-only-key"):
            self.assertNotIn(secret, prompt)
        self.assertEqual(set(sent), {"pods", "logs", "events", "deployments", "network"})
        self.assertEqual(payload, original)
        self.assertIn("untrusted DATA", messages[0]["content"])

    def test_prompt_large_logs_do_not_remove_other_sections(self):
        payload = evidence()
        payload["investigation"]["logs"] = {"entries": [{"text": "x" * 5000}] * 10000}
        messages, sent = build_prompt(payload)
        self.assertLess(len(messages[1]["content"]), 70000)
        self.assertEqual(sent["pods"]["problematic_pods"][0]["name"], "payment")

    def test_output_redacts_configured_key(self):
        item = diagnosis()
        item["explanation"] = "The test-only-key must never appear in output"
        result = self.analyze(json.dumps(item))
        self.assertEqual(result["status"], "success")
        self.assertNotIn("test-only-key", json.dumps(result))

    def test_pointer_through_string_is_not_a_valid_reference(self):
        self.assertFalse(resolve_pointer({"text": "abc"}, "/text/0"))
        self.assertTrue(resolve_pointer({"a/b": [False]}, "/a~1b/0"))

    def test_healthy_cluster_can_have_no_suggested_command(self):
        item = diagnosis()
        item.update(root_cause="No demonstrated failure", kubectl_commands=[], confidence=50)
        result = self.analyze(json.dumps(item))
        self.assertEqual(result["diagnosis"]["kubectl_command"], "")


class APIIntegrationTests(AuthenticatedAPITest, unittest.TestCase):
    def test_endpoint_preserves_evidence_and_adds_diagnosis(self):
        payload = evidence()
        with patch("app.api.investigate.investigate_cluster", return_value=payload), patch(
                "app.ai.analyzer.get_settings", return_value=settings()), patch(
                "app.ai.analyzer.LLMClient.complete", return_value=json.dumps(diagnosis())):
            response = TestClient(app).post("/investigate")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["investigation"], evidence()["investigation"])
        self.assertEqual(body["ai"]["status"], "success")
        self.assertIsInstance(body["diagnosis"], dict)

    def test_provider_failure_keeps_evidence(self):
        with patch("app.api.investigate.investigate_cluster", return_value=evidence()), patch(
                "app.ai.analyzer.get_settings", return_value=settings()), patch(
                "app.ai.analyzer.LLMClient.complete", side_effect=LLMError("Check OpenRouter credits (HTTP 402)")):
            body = TestClient(app).post("/investigate").json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["ai"]["status"], "error")
        self.assertIsNone(body["diagnosis"])
        self.assertIn("pods", body["investigation"])


if __name__ == "__main__":
    unittest.main()
