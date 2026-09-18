from __future__ import annotations

import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class AgentKind(str, Enum):
    LLM = "llm"
    COPILOT = "copilot"


class LLMReturnType(str, Enum):
    CODE = "code"


@dataclass
class AgentResult:
    output: str
    raw: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


Codebase = dict[str, str] # filename to value (e.g. solution.py => implementation)


class CodingAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def run(
        self,
        prompt: str,
        codebase: Codebase,
        task_id: str | None = None,
        api_key: str | None = None,
        status_callback: Any | None = None,
    ) -> AgentResult: ...

    @staticmethod
    def _serialize_codebase(codebase: Codebase) -> str:
        chunks: list[str] = []
        for rel in sorted(codebase):
            chunks.append(f"\n# === {rel} ===\n{codebase[rel]}")
        return "".join(chunks)


    @staticmethod
    def _write_codebase(codebase: Codebase, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        for rel, content in codebase.items():
            path = (dest / rel).resolve()
            if dest.resolve() not in path.parents and path != dest.resolve():
                raise ValueError(f"unsafe path escapes root: {rel}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


class LLM(CodingAgent):
    from model.prompt import RETURN_CODE_PROMPT

    PROMPTS: dict[LLMReturnType, str] = {
        LLMReturnType.CODE: RETURN_CODE_PROMPT,
    }

    # Models that should use litellm.aresponses instead of litellm.acompletion
    RESPONSES_MODELS: set[str] = {
        'openai/gpt-5.3-codex', 'openai/gpt-5.2-codex', 'openai/gpt-5.1-codex',
        'openai/gpt-5.3-codex_2026-02-24', 'openai/gpt-5.2-codex_2026-01-14',
        'openai/gpt-5.1-codex_2025-11-13',
    }
    # Models that need reasoning=medium
    EXPLICIT_REASONING_MODELS: set[str] = {
        'openai/gpt-5.4-mini', 'openai/gpt-5.4-nano',
        'openai/gpt-5.4-mini_2026-03-17', 'openai/gpt-5.4-nano_2026-03-17',
        'openrouter/openai/gpt-5.3-codex', 'openrouter/openai/gpt-5',
        'openrouter/openai/gpt-oss-120b', 'openrouter/openai/gpt-5.4-mini',
        'openrouter/openai/gpt-5.5', 'openrouter/x-ai/grok-4.3',
    } | RESPONSES_MODELS

    def __init__(
        self,
        model_name: str = "openrouter/openai/gpt-5.4-mini",
        return_type: LLMReturnType | str = LLMReturnType.CODE,
        prompt_template: str | None = None,
        max_retries: int | str = 10,
        api_mode: str = "auto",
        **litellm_kwargs: Any,
    ):
        self.model_name = model_name
        self.return_type = LLMReturnType(return_type)
        self.prompt_template = prompt_template or self.PROMPTS[self.return_type]
        self.max_retries = int(max_retries)
        if api_mode not in {"auto", "chat", "responses"}:
            raise ValueError("api_mode must be auto, chat, or responses")
        self.api_mode = api_mode
        self.litellm_kwargs = litellm_kwargs

    @property
    def name(self) -> str:
        return self.return_type.value + "/" + self.model_name

    async def run(
        self,
        prompt: str,
        codebase: Codebase,
        task_id: str | None = None,
        api_key: str | None = None,
        status_callback: Any | None = None,
    ) -> AgentResult:
        import asyncio

        import litellm
        litellm.suppress_debug_info = True

        codebase_text = self._serialize_codebase(codebase)
        content = self.prompt_template.format(
            code_repository=codebase_text,
            problem_statement=prompt,
        )
        messages = [{"role": "user", "content": content}]
        use_responses = self.api_mode == "responses" or (
            self.api_mode == "auto" and self.model_name in self.RESPONSES_MODELS
        )

        raw_output = ""
        parsed = None
        parse_error: str | None = None
        resp = None
        for attempt in range(self.max_retries):
            request_kwargs = dict(self.litellm_kwargs)
            if api_key is not None:
                request_kwargs["api_key"] = api_key
            extra_body = request_kwargs.get("extra_body") or {}
            if self.model_name in self.EXPLICIT_REASONING_MODELS and not (
                "reasoning" in request_kwargs or "reasoning" in extra_body
            ):
                request_kwargs.setdefault("reasoning_effort", "medium")
            if self.model_name == "openrouter/deepseek/deepseek-v3.2" and not (
                "reasoning" in request_kwargs or "reasoning_effort" in request_kwargs
                or "reasoning" in extra_body
            ):
                request_kwargs["extra_body"] = {**extra_body, "reasoning": {"enabled": True}}
            try:
                if use_responses:
                    resp = await litellm.aresponses(
                        model=self.model_name,
                        input=content,
                        **request_kwargs,
                    )
                    raw_output = self._extract_responses_text(resp)
                    
                else:
                    resp = await litellm.acompletion(
                        model=self.model_name,
                        messages=messages,
                        **request_kwargs,
                    )
                    raw_output = resp.choices[0].message.content or ""
                parsed = self._parse_output(raw_output, codebase)
            except Exception as exc:
                parse_error = f"{type(exc).__name__}: {exc}"
                
            if parsed is not None:
                break
            print(f"\n[llm retry {attempt + 1}/{self.max_retries}] {task_id}: {parse_error}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(min(2**attempt + 1, 60))
                
        if parsed is None:
            raise RuntimeError(f"LLM output unparseable after {self.max_retries} attempts: {parse_error}")
        
        output = self._serialize_codebase(parsed)

        # get model usage
        usage = getattr(resp, "usage", None)
        if use_responses:
            n_input_tokens = getattr(usage, "input_tokens", None)
            n_output_tokens = getattr(usage, "output_tokens", None)
        else:
            n_input_tokens = getattr(usage, "prompt_tokens", None)
            n_output_tokens = getattr(usage, "completion_tokens", None)
        try:
            litellm_response = resp.model_dump()
        except Exception:
            litellm_response = None
            
        return AgentResult(
            output=output,
            raw=resp,
            metadata={
                "raw_output": raw_output,
                "parse_error": parse_error,
                "n_input_tokens": n_input_tokens,
                "n_output_tokens": n_output_tokens,
                "litellm_response": litellm_response,
                "litellm_hidden_params": getattr(resp, "_hidden_params", None),
            },
        )

    @staticmethod
    def _extract_responses_text(resp: Any) -> str:
        text = getattr(resp, "output_text", None)
        if text:
            return text
        chunks: list[str] = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    chunks.append(t)
        return "".join(chunks)

    def _parse_output(self, output: str, codebase: Codebase) -> Codebase | None:
        import re
        
        if '</solution>' not in output:
            output += "\n</solution>"

        m = re.search(r"<solution>(.*?)</solution>", output, re.DOTALL)
        body = m.group(1).strip() if m else output
        return self._parse_full_files(body)

    @staticmethod
    def _parse_full_files(body: str) -> Codebase | None:
        import re

        # Split on `# === filename ===` markers
        parts = re.split(r"^\s*#\s*===\s*(.+?)\s*===\s*$", body, flags=re.MULTILINE)
        if len(parts) < 3:
            return None
        result: Codebase = {}
        for i in range(1, len(parts), 2):
            filename = parts[i].strip()
            content = parts[i + 1].strip("\n")
            # Strip trailing fenced code markers if the model wrapped each file
            content = re.sub(r"^```\w*\n", "", content)
            content = re.sub(r"\n```\s*$", "", content)
            result[filename] = content
        return result or None

class CopilotAgent(CodingAgent):
    VALID_MODELS = [
        'claude-opus-4.7',
        'claude-sonnet-4.6',
        'gpt-5.4-mini',
        'gpt-5.5',
        'gemini-3.1-pro-preview',
        'gemini-3.5-flash',
    ]

    def __init__(
        self,
        model_name: str = "claude-sonnet-4.6",
        max_retries: int | str = 3,
        timeout: int = 600,
        docker_image: str = "cabra-copilot:1.0.81",
        docker_network: str = "bridge",
        trace_dir: str = "local_data/copilot_traces",
        cost_log_path: str | None = None,
        debug_keep_container: bool | str = False,
    ):
        assert model_name in self.VALID_MODELS, (
            f"Invalid model name '{model_name}'. Valid models are {self.VALID_MODELS}. Or, run `copilot` and `/model` for an updated list of valid models"
        )
        self.model_name = model_name
        self.max_retries = int(max_retries)
        self.timeout = int(timeout)
        self.docker_image = docker_image
        self.docker_network = docker_network
        self.trace_dir = Path(trace_dir)
        self.cost_log_path = (
            Path(cost_log_path)
            if cost_log_path
            else Path(__file__).resolve().parent.parent / "copilot_cost_log.jsonl"
        )
        self.debug_keep_container = (
            debug_keep_container
            if isinstance(debug_keep_container, bool)
            else debug_keep_container.lower() == "true"
        )

    @property
    def name(self) -> str:
        return f"copilot/{self.model_name}"

    async def run(
        self,
        prompt: str,
        codebase: Codebase,
        task_id: str | None = None,
        api_key: str | None = None,
        status_callback: Any | None = None,
    ) -> AgentResult:
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return await self._run_once(
                    prompt, codebase, task_id, api_key, status_callback, attempt + 1
                )
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    print(f"[copilot-agent retry {attempt + 1}/{self.max_retries}] {exc}")
                    await asyncio.sleep(2 ** attempt + 1)
        raise RuntimeError(f"CopilotAgent failed after {self.max_retries} attempts: {last_exc}")

    async def _run_once(
        self,
        prompt: str,
        codebase: Codebase,
        task_id: str | None = None,
        api_key: str | None = None,
        status_callback: Any | None = None,
        attempt_number: int = 1,
    ) -> AgentResult:
        import asyncio
        import inspect
        import os
        import shutil

        workdir = Path(tempfile.mkdtemp(prefix="cabra-copilot-"))
        container_id: str | None = None
        session_id = str(uuid.uuid4())
        trace_path: Path | None = None
        trace_error: str | None = None
        completed = False

        try:
            self._write_codebase(codebase, workdir)
            self._make_workspace_writable(workdir)

            container_name = f"cabra-copilot-{uuid.uuid4().hex[:12]}"
            create_cmd = self._build_create_command(
                prompt, workdir, session_id, container_name
            )
            token = api_key or os.environ.get("COPILOT_GITHUB_TOKEN")
            if not token:
                raise RuntimeError("COPILOT_GITHUB_TOKEN is required for CopilotAgent")
            process_env = os.environ.copy()
            process_env["COPILOT_GITHUB_TOKEN"] = token

            create_proc = await asyncio.create_subprocess_exec(
                *create_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
            )
            create_stdout, create_stderr = await create_proc.communicate()
            if create_proc.returncode != 0:
                raise RuntimeError(
                    f"Docker could not create Copilot sandbox: {create_stderr.decode()}"
                )
            container_id = create_stdout.decode().strip()

            if status_callback is not None:
                
                # check if we are doing async runs
                maybe_awaitable = status_callback({
                    "status": "running",
                    "session_id": session_id,
                    "task_id": task_id,
                    "workdir": workdir.as_posix(),
                    "timeout": self.timeout,
                    "model_name": self.model_name,
                    "container_id": container_id,
                    "docker_image": self.docker_image,
                })
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

            proc = await asyncio.create_subprocess_exec(
                "docker", "start", "--attach", container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise RuntimeError(f"CopilotAgent timed out after {self.timeout}s")

            if proc.returncode != 0:
                raise RuntimeError(
                    f"CopilotAgent sandbox {container_id} exited {proc.returncode}; "
                    f"stdout={stdout.decode()!r}; stderr={stderr.decode()!r}"
                )

            trace_path = await self._copy_trace(container_id, session_id)

            output = self._read_codebase(workdir, codebase)
            if not output:
                raise RuntimeError("CopilotAgent produced no codebase output")

            completed = True
            return AgentResult(
                output=output,
                metadata={
                    "session_id": session_id,
                    "stdout": stdout.decode(),
                    "stderr": stderr.decode(),
                    "returncode": proc.returncode,
                    "container_id": container_id,
                    "docker_image": self.docker_image,
                    "docker_network": self.docker_network,
                    "trace_path": trace_path.as_posix(),
                    **self._read_usage(trace_path),
                },
            )
        finally:
            if container_id and trace_path is None:
                try:
                    trace_path = await self._copy_trace(container_id, session_id)
                except Exception as exc:
                    trace_error = str(exc)
            usage = self._read_usage(trace_path) if trace_path else {
                "total_nano_aiu": None,
                "total_aiu": None,
                "total_premium_requests": None,
                "usage_source": None,
            }
            self._append_cost_log({
                "session_id": session_id,
                "task_id": task_id,
                "model": self.model_name,
                "attempt": attempt_number,
                "success": completed,
                **usage,
                "trace_path": trace_path.as_posix() if trace_path else None,
                "trace_error": trace_error,
            })
            keep_for_debug = self.debug_keep_container and not completed
            if container_id and not keep_for_debug:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "rm", "--force", container_id,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await cleanup.communicate()
            if not keep_for_debug:
                shutil.rmtree(workdir, ignore_errors=True)
            elif container_id:
                print(
                    f"[copilot-agent debug] kept container={container_id} "
                    f"workdir={workdir}"
                )

    def _build_create_command(
        self,
        prompt: str,
        workdir: Path,
        session_id: str,
        container_name: str,
    ) -> list[str]:
        return [
            "docker", "create",
            "--name", container_name,
            "--label", "cabra.agent=copilot",
            "--network", self.docker_network,
            "--init",
            "--mount", f"type=bind,source={workdir.resolve()},target=/workspace",
            "--workdir", "/workspace",
            "--user", "10001:10001",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "32g",
            "--env", "HOME=/home/agent",
            "--env", "COPILOT_GITHUB_TOKEN",
            self.docker_image,
            "copilot",
            "--model", self.model_name,
            "-C", "/workspace",
            "-p", prompt,
            "--mode", "autopilot",
            "--silent",
            "--allow-all-tools",
            "--excluded-tools=session_store_sql",
            "--deny-tool=session_store_sql",
            f"--session-id={session_id}",
            "--no-ask-user",
            "--no-remote",
            "--no-remote-export",
        ]

    async def _copy_trace(self, container_id: str, session_id: str) -> Path:
        import asyncio

        trace_path = self.trace_dir / session_id / "events.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        source = (
            f"{container_id}:/home/agent/.copilot/session-state/"
            f"{session_id}/events.jsonl"
        )
        proc = await asyncio.create_subprocess_exec(
            "docker", "cp", source, str(trace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not trace_path.is_file():
            raise RuntimeError(
                f"CopilotAgent could not save events trace from container "
                f"{container_id}: {stderr.decode()}"
            )
        return trace_path

    @staticmethod
    def _read_usage(trace_path: Path) -> dict[str, int | float | str | None]:
        import json

        checkpoint_nano_aiu = None
        checkpoint_premium_requests = None
        shutdown_nano_aiu = None
        shutdown_premium_requests = None
        with trace_path.open(encoding="utf-8") as trace_file:
            for line in trace_file:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                event_type = event.get("type")
                nano_aiu = data.get("totalNanoAiu")
                premium_requests = data.get("totalPremiumRequests")
                if event_type == "session.shutdown":
                    if isinstance(nano_aiu, (int, float)):
                        shutdown_nano_aiu = nano_aiu
                    if isinstance(premium_requests, (int, float)):
                        shutdown_premium_requests = premium_requests
                elif event_type == "session.usage_checkpoint":
                    if isinstance(nano_aiu, (int, float)):
                        checkpoint_nano_aiu = nano_aiu
                    if isinstance(premium_requests, (int, float)):
                        checkpoint_premium_requests = premium_requests

        if shutdown_nano_aiu is not None or shutdown_premium_requests is not None:
            total_nano_aiu = shutdown_nano_aiu
            total_premium_requests = shutdown_premium_requests
            usage_source = "session.shutdown"
        else:
            total_nano_aiu = checkpoint_nano_aiu
            total_premium_requests = checkpoint_premium_requests
            usage_source = (
                "session.usage_checkpoint"
                if total_nano_aiu is not None or total_premium_requests is not None
                else None
            )
        return {
            "total_nano_aiu": total_nano_aiu,
            "total_aiu": total_nano_aiu / 1_000_000_000 if total_nano_aiu is not None else None,
            "total_premium_requests": total_premium_requests,
            "usage_source": usage_source,
        }

    def _append_cost_log(self, record: dict[str, Any]) -> None:
        import json
        import os

        self.cost_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode()
        descriptor = os.open(
            self.cost_log_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o644,
        )
        try:
            os.write(descriptor, line)
        finally:
            os.close(descriptor)

    @staticmethod
    def _make_workspace_writable(workdir: Path) -> None:
        for path in workdir.rglob("*"):
            path.chmod(0o777 if path.is_dir() else 0o666)
        workdir.chmod(0o777)

    @staticmethod
    def _read_codebase(workdir: Path, original: Codebase) -> str:
        out: Codebase = {}
        for rel in sorted(original):
            path = workdir / rel
            if path.exists():
                out[rel] = path.read_text()
        return CodingAgent._serialize_codebase(out) if out else ""

class AgentFactory:
    @staticmethod
    def create(kind: AgentKind | str, **kwargs: Any) -> CodingAgent:
        kind = AgentKind(kind)
        if kind is AgentKind.LLM:
            return LLM(**kwargs)
        if kind is AgentKind.COPILOT:
            return CopilotAgent(**kwargs)
        raise ValueError(f"Unknown agent kind: {kind}")