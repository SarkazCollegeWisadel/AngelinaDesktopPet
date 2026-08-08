from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QObject, Signal


def completion_endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    lower = base.lower()
    if "api.stepfun.com" in lower and lower.endswith("/step_plan"):
        base += "/v1"
        lower = base.lower()
    if "api.stepfun.com" in lower and lower.endswith("/v1/messages"):
        base = base[: -len("/messages")]
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def recommended_reasoning_effort(base_url: str, model: str) -> str | None:
    """Use inexpensive reasoning only for Step models that document the field."""
    base = base_url.strip().lower()
    name = model.strip().lower()
    if "api.stepfun.com" in base and name in {"step-3.7-flash", "step-3.5-flash-2603"}:
        return "low"
    return None


def recommended_thinking(base_url: str, model: str) -> dict[str, str] | None:
    """Keep official DeepSeek V4 desktop chatter fast and inexpensive."""
    base = base_url.strip().lower()
    name = model.strip().lower()
    if "api.deepseek.com" in base and name in {"deepseek-v4-flash", "deepseek-v4-pro"}:
        return {"type": "disabled"}
    return None


def _extract_text(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("接口响应里没有可用的回复") from exc
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                value = part.get("text")
                if isinstance(value, str):
                    parts.append(value)
        content = "".join(parts)
    if content is None:
        return ""
    if not isinstance(content, str):
        return ""
    return content.strip()


def _empty_response_error(body: dict[str, Any]) -> RuntimeError:
    try:
        choice = body["choices"][0]
        finish_reason = str(choice.get("finish_reason") or "")
    except (KeyError, IndexError, TypeError):
        finish_reason = ""
    if finish_reason == "length":
        return RuntimeError("模型输出预算已耗尽，未生成可显示的正文")
    return RuntimeError("模型完成了推理但没有生成正文；请重试或在设置中切换模型")


def _can_retry_empty(body: dict[str, Any]) -> bool:
    try:
        choice = body["choices"][0]
        message = choice.get("message") or {}
        return choice.get("finish_reason") == "length" or bool(
            message.get("reasoning_content") or message.get("reasoning")
        )
    except (KeyError, IndexError, TypeError, AttributeError):
        return False


def _post_completion(endpoint: str, api_key: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "AngelinaDesktopPet/0.2",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"接口返回 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络连接失败：{exc.reason}") from exc


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 180,
    temperature: float = 0.9,
    reasoning_effort: str | None = None,
    thinking: dict[str, str] | None = None,
    timeout: float = 45.0,
) -> str:
    if not api_key.strip():
        raise ValueError("还没有填写 API Key")
    payload = {
        "model": model.strip(),
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if thinking:
        payload["thinking"] = dict(thinking)
    endpoint = completion_endpoint(base_url)
    body = _post_completion(endpoint, api_key, payload, timeout)
    text = _extract_text(body)
    # Reasoning models can spend a very small max_tokens budget before they
    # reach the user-visible answer. Retry once with a sane ceiling; never show
    # reasoning_content as if it were the assistant's reply.
    if not text and max_tokens < 1024 and _can_retry_empty(body):
        retry_payload = dict(payload)
        retry_payload["max_tokens"] = min(1024, max(512, max_tokens * 2))
        body = _post_completion(endpoint, api_key, retry_payload, timeout)
        text = _extract_text(body)
    if not text:
        raise _empty_response_error(body)
    return text


class AIService(QObject):
    completed = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="angelina-ai")

    def submit(self, request_id: str, **kwargs: Any) -> None:
        future = self._pool.submit(chat_completion, **kwargs)

        def done(item: Any) -> None:
            try:
                self.completed.emit(request_id, item.result())
            except Exception as exc:  # surfaced to the UI, never swallowed
                self.failed.emit(request_id, str(exc))

        future.add_done_callback(done)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
