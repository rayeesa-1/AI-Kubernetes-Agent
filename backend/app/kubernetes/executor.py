"""Only fixed read operations are exposed. Never pass a shell command."""
import json
import subprocess
import time
from pathlib import Path
from loguru import logger


class KubectlExecutor:
    def __init__(self, settings, context=None):
        self.settings = settings
        self.context = context
        self.deadline = time.monotonic() + settings.investigation_timeout_seconds

    def run(self, args, as_json=False):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return {"ok": False, "error": "Investigation time budget exhausted"}
        command = ["kubectl"]
        if self.settings.kubeconfig_path:
            if not Path(self.settings.kubeconfig_path).is_file():
                return {"ok": False, "error": "Kubeconfig file is missing. Check the read-only Docker mount and KUBECONFIG_PATH."}
            command += ["--kubeconfig", self.settings.kubeconfig_path]
        if self.context:
            command += ['--context', self.context]
        command += ["--request-timeout=8s", *args]
        try:
            result = subprocess.run(command, shell=False, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace",
                                    timeout=min(self.settings.kubectl_timeout_seconds, remaining))
            if result.returncode:
                logger.warning("kubectl {} failed (exit {})", args[0], result.returncode)
                return {"ok": False, "error": self.friendly_error(result.stderr),
                        "returncode": result.returncode}
            data = json.loads(result.stdout) if as_json else result.stdout
            return {"ok": True, "data": data}
        except FileNotFoundError:
            return {"ok": False, "error": "kubectl executable not found"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "kubectl command timed out"}
        except (ValueError, OSError) as exc:
            logger.warning("kubectl read failed: {}", type(exc).__name__)
            return {"ok": False, "error": "Invalid kubectl output or execution failure"}

    @staticmethod
    def friendly_error(stderr):
        # Raw kubectl stderr can contain URLs, plugin output, or credentials.
        text = stderr.lower()
        if 'forbidden' in text:
            return 'Kubernetes permissions denied (Forbidden). Grant read access to the requested resources and pod logs.'
        if any(word in text for word in ['unauthorized', 'provide credentials', 'logged in']):
            return 'Kubernetes authentication failed. Refresh the selected context credentials.'
        if any(word in text for word in ['certificate', 'x509']):
            return 'Kubernetes certificate verification failed. Check the selected API address and trusted certificate; keep TLS verification enabled.'
        if 'executable' in text or 'exec plugin' in text:
            return 'A kubeconfig credential plugin is missing or failed. Install and configure that plugin inside the backend container.'
        return 'Unable to connect to or read from Kubernetes. Verify the selected context, API address, container network access, and kubectl permissions.'

    def get(self, resource):
        allowed = {"pods", "events", "deployments", "services", "endpointslices", "nodes"}
        if resource not in allowed:
            raise ValueError("Unsupported resource")
        args = ["get", resource]
        if resource != "nodes":
            args += ["--all-namespaces"]
        return self.run([*args, "-o", "json"], as_json=True)

    def logs(self, namespace, pod, container, previous=False):
        # Names are obtained from API objects, never arbitrary client arguments.
        args = ["logs", pod, "--namespace", namespace, "--container", container,
                "--tail=80", "--limit-bytes=12000", "--pod-running-timeout=3s"]
        if previous:
            args.append("--previous")
        return self.run(args)
