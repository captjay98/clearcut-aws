"""Google Cloud Vertex AI LLM Runtime Adapter."""
import json
import logging
import os
import subprocess
from typing import Any

import httpx

logger = logging.getLogger(__name__)

VERTEX_MODEL = os.getenv("VERTEX_MODEL", "gemini-1.5-flash")
DEFAULT_LOCATION = os.getenv("VERTEX_LOCATION", "global")


class VertexGeminiAdapter:
    """Enterprise Vertex AI runtime using native Google Cloud IAM authentication and Workload Identity."""

    def __init__(self, project_id: str | None = None, location: str = DEFAULT_LOCATION) -> None:
        self.project_id = project_id or os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "clearcut-workspace"))
        self.location = location

    def _get_access_token(self) -> str | None:
        """Fetch ambient OAuth2 token from Cloud Run metadata server or local gcloud auth ADC."""
        # 1. Check Google Cloud Metadata Server (Cloud Run / GCE)
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(
                    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                    headers={"Metadata-Flavor": "Google"},
                )
                if res.status_code == 200:
                    return res.json().get("access_token")
        except Exception:
            pass

        # 2. Check local gcloud CLI print-access-token for local developer environment
        try:
            token = subprocess.check_output(
                ["gcloud", "auth", "print-access-token"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if token:
                return token
        except Exception:
            pass

        return None

    def _get_endpoint_url(self) -> str:
        """Construct Vertex AI REST endpoint URL supporting global and regional routing."""
        if self.location in ("global", ""):
            host = "aiplatform.googleapis.com"
            location_path = "global"
        else:
            host = f"{self.location}-aiplatform.googleapis.com"
            location_path = self.location

        return (
            f"https://{host}/v1/projects/{self.project_id}/"
            f"locations/{location_path}/publishers/google/models/{VERTEX_MODEL}:generateContent"
        )

    async def generate_completion(self, prompt: str, system_instruction: str | None = None) -> str:
        """Generate text completion directly from Google Cloud Vertex AI global endpoint."""
        token = self._get_access_token()
        if not token or not self.project_id:
            raise RuntimeError(
                f"Vertex AI authentication failed: No Google Cloud IAM credentials or project found (project='{self.project_id}')."
            )

        url = self._get_endpoint_url()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, headers=headers, json=body)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    return candidates[0]["content"]["parts"][0]["text"]
                raise RuntimeError("Vertex AI returned no candidate completions")
            else:
                raise RuntimeError(f"Vertex AI error HTTP {res.status_code}: {res.text}")


# Alias for backwards compatibility with test harness
GeminiAdkRuntime = VertexGeminiAdapter
