"""Shared Amazon Bedrock Converse invocation, error mapping, and metadata extraction."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from botocore.exceptions import (
    ConnectionError as BotoConnectionError,
)

logger = logging.getLogger(__name__)


async def invoke_bedrock_converse(
    client: Any,
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    system: list[dict[str, Any]] | None = None,
    inference_config: dict[str, Any] | None = None,
    additional_model_request_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke the Bedrock Converse API synchronously on a worker thread."""
    kwargs: dict[str, Any] = {
        "modelId": model_id,
        "messages": messages,
    }
    if system is not None:
        kwargs["system"] = system
    if inference_config is not None:
        kwargs["inferenceConfig"] = inference_config
    if additional_model_request_fields is not None:
        kwargs["additionalModelRequestFields"] = additional_model_request_fields

    return await asyncio.to_thread(client.converse, **kwargs)


def extract_converse_text(response: dict[str, Any]) -> str:
    """Extract and concatenate text blocks from a Bedrock Converse response."""
    output = response.get("output")
    if not isinstance(output, dict):
        return ""
    message = output.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and "text" in item and isinstance(item["text"], str):
            text_parts.append(item["text"])
    return "\n".join(text_parts).strip()


def extract_json_payload(raw: str) -> Any:
    """Extract and parse JSON payload from raw model text, handling markdown code blocks."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Empty or non-string response content.")

    text = raw.strip()

    # If text is enclosed in markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    elif "```" in text:
        # Extract content between first ``` and closing ```
        first_fence = text.find("```")
        closing_fence = text.rfind("```")
        if first_fence != -1 and closing_fence > first_fence:
            snippet = text[first_fence + 3 : closing_fence].strip()
            # If language specifier exists on first line of snippet (e.g. 'json')
            snippet_lines = snippet.splitlines()
            if snippet_lines and snippet_lines[0].strip().lower() in {"json", "text"}:
                snippet = "\n".join(snippet_lines[1:]).strip()
            text = snippet

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as primary_err:
        # Fallback: attempt to find JSON object or array bounds
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")

        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace : last_brace + 1])
            except Exception:
                pass

        if first_bracket != -1 and last_bracket > first_bracket:
            try:
                return json.loads(text[first_bracket : last_bracket + 1])
            except Exception:
                pass

        raise ValueError(f"Failed to parse JSON payload: {primary_err}") from primary_err


def extract_returned_model(response: dict[str, Any]) -> str | None:
    """Truthfully extract returned model identity from Bedrock Converse response.

    Extracts from additionalModelResponseFields.get("model") or HTTP header
    'x-amzn-bedrock-model-id'. Returns None if absent.
    NEVER copies requested_model into returned_model.
    """
    # 1. Inspect additionalModelResponseFields["model"]
    additional = response.get("additionalModelResponseFields")
    if isinstance(additional, dict):
        model = additional.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()

    # 2. Inspect HTTP headers from ResponseMetadata
    resp_meta = response.get("ResponseMetadata")
    if isinstance(resp_meta, dict):
        headers = resp_meta.get("HTTPHeaders")
        if isinstance(headers, dict):
            for header_name in ("x-amzn-bedrock-model-id", "X-Amzn-Bedrock-Model-Id"):
                model_header = headers.get(header_name)
                if isinstance(model_header, str) and model_header.strip():
                    return model_header.strip()

    return None


def extract_response_id(response: dict[str, Any]) -> str | None:
    """Extract RequestId from Bedrock ResponseMetadata."""
    resp_meta = response.get("ResponseMetadata")
    if isinstance(resp_meta, dict):
        req_id = resp_meta.get("RequestId")
        if isinstance(req_id, str) and req_id.strip():
            return req_id.strip()
    return None


def extract_token_usage[TUsage](
    response: dict[str, Any],
    usage_cls: type[TUsage],
) -> tuple[TUsage, bool]:
    """Extract and validate token usage counts into the provided dataclass."""
    usage_dict = response.get("usage")
    if not isinstance(usage_dict, dict):
        return usage_cls(None, None, None), True

    values: list[int | None] = []
    invalid = False
    for key in ("inputTokens", "outputTokens", "totalTokens"):
        val = usage_dict.get(key)
        if val is None:
            values.append(None)
        elif isinstance(val, bool) or not isinstance(val, int) or val < 0:
            values.append(None)
            invalid = True
        else:
            values.append(val)

    return usage_cls(*values), invalid


def classify_bedrock_error[TError](error: Exception, error_cls: type[TError]) -> TError:
    """Classify botocore ClientError, timeouts, and network errors into domain SafeError."""
    if isinstance(error, ClientError):
        error_info = error.response.get("Error", {})
        code = error_info.get("Code", "")
        status_code = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

        if code in {"ThrottlingException", "RequestLimitExceeded", "TooManyRequestsException"} or status_code == 429:
            return error_cls(
                code="provider_rate_limited",
                message="The Bedrock provider rate limit was reached.",
                retryable=True,
            )
        if code in {"AccessDeniedException", "AuthFailure", "UnrecognizedClientException"} or status_code == 403:
            return error_cls(
                code="provider_permission_denied",
                message="The Bedrock provider access was denied.",
                retryable=False,
            )
        if code == "ValidationException" or status_code == 400:
            return error_cls(
                code="invalid_request",
                message="The Bedrock provider rejected the request.",
                retryable=False,
            )
        if code in {"ModelTimeoutException", "ServiceUnavailableException", "ModelNotReadyException", "InternalServerException", "ModelErrorException"}:
            return error_cls(
                code="provider_unavailable",
                message="The Bedrock service is unavailable.",
                retryable=True,
            )
        if code == "ResourceNotFoundException" or status_code == 404:
            return error_cls(
                code="provider_unavailable",
                message="The Bedrock model resource was not found.",
                retryable=False,
            )
        if status_code is not None and 500 <= status_code <= 599:
            return error_cls(
                code="provider_unavailable",
                message="The Bedrock provider returned a server error.",
                retryable=True,
            )
        # Unhandled ClientError
        return error_cls(
            code="provider_unavailable",
            message="The Bedrock provider could not complete the request.",
            retryable=True,
        )

    if isinstance(
        error,
        (
            ReadTimeoutError,
            ConnectTimeoutError,
            EndpointConnectionError,
            BotoConnectionError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return error_cls(
            code="provider_unavailable",
            message="The Bedrock provider connection timed out or failed.",
            retryable=True,
        )

    return error_cls(
        code="provider_error",
        message="The Bedrock provider returned an unclassified error.",
        retryable=False,
    )


def elapsed_ms(started: float) -> int:
    """Calculate elapsed milliseconds from a perf_counter timestamp."""
    return max(0, round((time.perf_counter() - started) * 1000))
