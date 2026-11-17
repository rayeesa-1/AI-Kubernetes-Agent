from auth_test_support import AuthenticatedAPITest
import json
import subprocess
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import Settings
from app.kubernetes.executor import KubectlExecutor
from app.kubernetes.pods import inspect_pods
from app.kubernetes.network import inspect_network
from app.kubernetes.deployments import inspect_deployments
from app.services.investigation import investigate_cluster


def ok(items):
    return {"ok": True, "data": {"items": items}}


def pod(state=None, last=None, phase="Running"):
    return {"metadata": {"name": "demo", "namespace": "default", "creationTimestamp": "2020-01-01T00:00:00Z"},
            "status": {"phase": phase, "containerStatuses": [{"name": "app", "state": state or {},
                       "lastState": last or {}, "restartCount": 1}]}}


class FakeExecutor:
    def __init__(self, fail=False): self.fail = fail
    def get(self, resource):
        return {"ok": False, "error": "Forbidden"} if self.fail else ok([])
    def logs(self, *args): return {"ok": False, "error": "No logs"}


class InvestigationTests(AuthenticatedAPITest, unittest.TestCase):
    def test_current_waiting_and_previous_oom(self):
        result = inspect_pods(ok([pod({"waiting": {"reason": "CrashLoopBackOff"}},
                                     {"terminated": {"reason": "OOMKilled"}})]))
        self.assertFalse(result["healthy"])
        self.assertEqual(result["problematic_pods"][0]["status"], ["CrashLoopBackOff", "OOMKilled"])

    def test_init_container_and_completed_job(self):
        item = pod()
        item["status"]["initContainerStatuses"] = [{"name": "init", "state": {"waiting": {"reason": "ImagePullBackOff"}}}]
        self.assertFalse(inspect_pods(ok([item]))["healthy"])
        self.assertTrue(inspect_pods(ok([pod({"terminated": {"exitCode": 0}}, phase="Succeeded")]))["healthy"])

    def test_container_creating_threshold(self):
        item = pod({"waiting": {"reason": "ContainerCreating"}})
        item["metadata"]["creationTimestamp"] = "2999-01-01T00:00:00Z"
        self.assertTrue(inspect_pods(ok([item]))["healthy"])
        item["metadata"]["creationTimestamp"] = "2020-01-01T00:00:00Z"
        self.assertFalse(inspect_pods(ok([item]))["healthy"])

    def test_network_service_exceptions_and_missing_endpoints(self):
        base = {"metadata": {"name": "api", "namespace": "default"}}
        services = [{**base, "spec": {"type": "ExternalName"}},
                    {**base, "spec": {}}, {**base, "spec": {"selector": {"app": "missing"}}}]
        result = inspect_network(ok(services), ok([]), ok([]))
        self.assertEqual(len(result["findings"]), 1)
        self.assertIn("NoReadyEndpoints", result["findings"][0]["observations"])
        self.assertIn("Not verified", result["dns"]["status"])

    def test_deployment_rollout_failure(self):
        item = {"metadata": {"name": "api", "namespace": "default", "generation": 1},
                "spec": {"replicas": 1}, "status": {"availableReplicas": 0,
                "conditions": [{"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded"}]}}
        self.assertFalse(inspect_deployments(ok([item]))["healthy"])

    def test_collection_status_and_missing_permissions(self):
        self.assertEqual(investigate_cluster(FakeExecutor())["status"], "success")
        self.assertEqual(investigate_cluster(FakeExecutor(True))["status"], "error")

    def test_executor_missing_binary_timeout_and_invalid_json(self):
        for failure in [FileNotFoundError(), subprocess.TimeoutExpired("kubectl", 1)]:
            with patch("app.kubernetes.executor.subprocess.run", side_effect=failure):
                self.assertFalse(KubectlExecutor(Settings()).get("pods")["ok"])
        with patch("app.kubernetes.executor.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "bad", "")):
            self.assertFalse(KubectlExecutor(Settings()).get("pods")["ok"])

    def test_executor_no_shell_and_forbidden_output(self):
        with patch("app.kubernetes.executor.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "Forbidden")) as run:
            self.assertIn("Forbidden", KubectlExecutor(Settings()).get("pods")["error"])
            self.assertIs(run.call_args.kwargs["shell"], False)
            self.assertIsInstance(run.call_args.args[0], list)
        with self.assertRaises(ValueError): KubectlExecutor(Settings()).get("secrets")

    def test_bounded_logs_previous_container_and_partial_results(self):
        from app.kubernetes.logs import collect_logs
        raw = ok([pod({"waiting": {"reason": "CrashLoopBackOff"}})])
        executor = FakeExecutor()
        with patch.object(executor, "logs", return_value={"ok": True, "data": "startup error\nnormal line"}) as logs:
            result = collect_logs(executor, inspect_pods(raw), raw, max_requests=1)
            self.assertTrue(result["truncated"])
            self.assertEqual(logs.call_count, 1)
            self.assertEqual(result["entries"][0]["matching_lines"], ["startup error"])
        with patch.object(executor, "logs", return_value={"ok": True, "data": ""}) as logs:
            collect_logs(executor, inspect_pods(raw), raw)
            self.assertTrue(logs.call_args.args[-1])
        original_get = executor.get
        executor.get = lambda resource: {"ok": False, "error": "Forbidden"} if resource == "events" else original_get(resource)
        self.assertEqual(investigate_cluster(executor)["status"], "partial")

    def test_event_evidence_and_investigation_budget(self):
        from app.kubernetes.events import analyze_events
        result = analyze_events(ok([{"metadata": {"namespace": "default"}, "type": "Warning",
                                     "reason": "FailedScheduling", "message": "Insufficient cpu"}]))
        self.assertEqual(result["findings"][0]["reason"], "FailedScheduling")
        executor = KubectlExecutor(Settings())
        executor.deadline = 0
        self.assertIn("budget", executor.get("pods")["error"])

    def test_concurrent_request_is_rejected(self):
        from app.api.investigate import _lock
        _lock.acquire()
        try:
            self.assertEqual(TestClient(app).post("/investigate").status_code, 409)
        finally:
            _lock.release()

    def test_health_and_post_contract(self):
        client = TestClient(app)
        self.assertEqual(client.get("/health").json(), {"status": "healthy", "service": "ai-kubernetes-agent"})
        with patch("app.api.investigate.investigate_cluster", return_value=investigate_cluster(FakeExecutor())):
            response = client.post("/investigate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()["investigation"]), {"pods", "logs", "events", "deployments", "network"})
        response = client.options("/investigate", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__": unittest.main()
