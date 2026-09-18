"""Viewer for Merge Code refactoring tasks.

Supports browsing generated tasks under ``local_data/tasks`` and scored model outputs
under ``data/results``. Each task run file is a JSON list of
``{"prompt": <text>, "input": <source>, "input_with_space": <source>,
"solution": <source>}`` records. The results view also loads matching response
JSONL records from ``local_data/responses`` so scores and generated code appear in one
place.

Run with::

    uv run streamlit run data/tasks/merge_code/viewer.py -- --data_root local_data
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import os
import re
import sys

import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data_root",
        type=str,
        default=os.path.join(_HERE, "data"),
        help="Root containing tasks/, responses/, results/ subdirs.",
    )
    parser.add_argument(
        "--run_name",
        type=str,
        default=None,
        help="Optional run name (JSON file stem) to select by default.",
    )
    return parser.parse_known_args(sys.argv[1:])[0]


def _list_runs(run_dir):
    if not os.path.isdir(run_dir):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(run_dir)
        if f.endswith(".json")
    )


def _list_response_runs(responses_root):
    if not os.path.isdir(responses_root):
        return []
    runs = []
    for name in sorted(os.listdir(responses_root)):
        path = os.path.join(responses_root, name)
        if os.path.isdir(path) and any(f.endswith(".jsonl") for _, _, files in os.walk(path) for f in files):
            runs.append(name)
    return runs


def _list_response_models(responses_root, run_name):
    run_dir = os.path.join(responses_root, run_name)
    if not os.path.isdir(run_dir):
        return []
    models = []
    for root, _, files in os.walk(run_dir):
        for filename in files:
            if not filename.endswith(".jsonl"):
                continue
            path = os.path.join(root, filename)
            rel = os.path.relpath(path, run_dir)
            models.append(os.path.splitext(rel)[0].replace(os.sep, "/"))
    return sorted(models)


def _list_jsonl_runs(root_dir):
    if not os.path.isdir(root_dir):
        return []
    runs = []
    for name in sorted(os.listdir(root_dir)):
        path = os.path.join(root_dir, name)
        if os.path.isdir(path) and any(f.endswith(".jsonl") for _, _, files in os.walk(path) for f in files):
            runs.append(name)
    return runs


def _list_jsonl_models(root_dir, run_name):
    run_dir = os.path.join(root_dir, run_name)
    if not os.path.isdir(run_dir):
        return []
    models = []
    for root, _, files in os.walk(run_dir):
        for filename in files:
            if not filename.endswith(".jsonl"):
                continue
            rel = os.path.relpath(os.path.join(root, filename), run_dir)
            models.append(os.path.splitext(rel)[0].replace(os.sep, "/"))
    return sorted(models)


@st.cache_data(show_spinner=False)
def _load_run(path, _mtime):
    with open(path) as f:
        return json.load(f)


def load_run(run_dir, run_name):
    path = os.path.join(run_dir, f"{run_name}.json")
    return _load_run(path, os.path.getmtime(path))


@st.cache_data(show_spinner=False)
def _load_jsonl(path, _mtime):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_response_records(responses_root, run_name, model):
    path = os.path.join(responses_root, run_name, *model.split("/")) + ".jsonl"
    return _load_jsonl(path, os.path.getmtime(path))


def load_jsonl_records(root_dir, run_name, model):
    path = os.path.join(root_dir, run_name, *model.split("/")) + ".jsonl"
    return _load_jsonl(path, os.path.getmtime(path))


def _parse_codebase(output):
    parts = re.split(r"^\s*#\s*===\s*(.+?)\s*===\s*$", output or "", flags=re.MULTILINE)
    if len(parts) < 3:
        return {}
    return {parts[i].strip(): parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def _task_index_from_record(record):
    metadata = record.get("metadata") or {}
    if isinstance(metadata.get("task_index"), int):
        return metadata["task_index"]
    for key in ("dag_id", "name"):
        value = record.get(key)
        if not isinstance(value, str):
            continue
        match = re.search(r"(\d+)$", value)
        if match:
            return int(match.group(1))
    return None


def _latest_records(records):
    by_key = {}
    order = []
    for record in records:
        key = (record.get("name"), record.get("dag_id"))
        if key not in by_key:
            order.append(key)
        by_key[key] = record
    return [by_key[key] for key in order]


def _records_by_dag_id(records):
    by_dag_id = {}
    for record in records:
        dag_id = record.get("dag_id")
        if dag_id:
            by_dag_id[dag_id] = record
    return by_dag_id


def _result_status(record):
    status = record.get("status") or (record.get("metadata") or {}).get("status")
    if status and status != "completed":
        return status
    if "parsed_ok" not in record and record.get("output"):
        return status or "completed"
    if not record.get("parsed_ok"):
        return "parse error"
    summary = record.get("summary") or {}
    if not summary:
        return "no scores"
    statuses = []
    for kind in sorted(summary):
        counts = summary[kind]
        if counts.get("error", 0):
            statuses.append(f"{kind}:error")
        elif counts.get("fail", 0):
            statuses.append(f"{kind}:fail")
        elif counts.get("pass", 0):
            statuses.append(f"{kind}:pass")
        else:
            statuses.append(f"{kind}:empty")
    return ", ".join(statuses)


def _summary_markdown(summary):
    bits = []
    for kind, counts in sorted((summary or {}).items()):
        bits.append(
            f"**{kind}**: {counts.get('pass', 0)}P / {counts.get('fail', 0)}F / "
            f"{counts.get('error', 0)}E ({counts.get('pass_rate', 0):.2f})"
        )
    return " · ".join(bits)


def _task_from_result(tasks, result_record):
    task_idx = _task_index_from_record(result_record)
    if task_idx is not None and 0 <= task_idx < len(tasks):
        return task_idx, tasks[task_idx]
    return task_idx, {}


def _render_source_panel(title, source, *, language="python"):
    st.markdown(f"#### {title}")
    st.code(source or "(missing)", language=language)


def _extract_class_source(source, class_name):
    if not source:
        return ""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            if node.end_lineno is None:
                return ""
            return "\n".join(lines[node.lineno - 1:node.end_lineno])
    return ""


_MAX_LIST_ITEMS = 20
_MAX_STR_CHARS = 5000


def _truncate_for_display(obj):
    if isinstance(obj, dict):
        return {k: _truncate_for_display(v) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > _MAX_LIST_ITEMS:
            head = [_truncate_for_display(item) for item in obj[:_MAX_LIST_ITEMS]]
            return head + [f"... ({len(obj) - _MAX_LIST_ITEMS} more items truncated)"]
        return [_truncate_for_display(item) for item in obj]
    if isinstance(obj, str) and len(obj) > _MAX_STR_CHARS:
        return obj[:_MAX_STR_CHARS] + f"... ({len(obj) - _MAX_STR_CHARS} more chars truncated)"
    return obj


def _iter_jsonl(path):
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _copilot_events_path(session_id):
    return os.path.expanduser(
        os.path.join("~", ".copilot", "session-state", session_id, "events.jsonl")
    )


def _load_copilot_events(session_id):
    path = _copilot_events_path(session_id)
    if not os.path.isfile(path):
        return None
    return {
        "session_id": session_id,
        "path": path,
        "events": list(_iter_jsonl(path)),
    }


def _load_trace(response):
    metadata = response.get("metadata") or {}
    session_id = metadata.get("session_id")
    if session_id:
        trace = _load_copilot_events(session_id)
        if trace:
            return "copilot_events", trace

    logs_dir = metadata.get("agent_logs_dir")
    if logs_dir and os.path.isdir(logs_dir):
        txts = sorted(f for f in os.listdir(logs_dir) if f.endswith(".txt"))
        if txts:
            with open(os.path.join(logs_dir, txts[0])) as f:
                return "text", f.read()
        jsons = sorted(f for f in os.listdir(logs_dir) if f.endswith(".json"))
        if jsons:
            with open(os.path.join(logs_dir, jsons[0])) as f:
                return "json", json.load(f)

    raw = metadata.get("raw_output", "")
    if isinstance(raw, str):
        thoughts = re.findall(r"<thought>(.*?)</thought>", raw, flags=re.DOTALL)
        if thoughts:
            return "text", "\n\n---\n\n".join(t.strip() for t in thoughts)
    return None, None


def _event_time(event):
    timestamp = event.get("timestamp") or ""
    if isinstance(timestamp, str) and "T" in timestamp:
        return timestamp.replace("T", " ").replace("Z", " UTC")
    return str(timestamp)


def _clip_text(value, limit=4000):
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... truncated {len(text) - limit} chars"


def _wrapped_trace_text(value, limit=4000):
    text = html.escape(_clip_text(value, limit=limit))
    st.markdown(
        f"""
        <pre style="
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            word-break: break-word;
            background: #f6f8fa;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 0.75rem;
            font-size: 0.875rem;
            line-height: 1.45;
        ">{text}</pre>
        """,
        unsafe_allow_html=True,
    )


def _tool_name_for_event(event, starts_by_call_id):
    data = event.get("data") or {}
    if data.get("toolName"):
        return data["toolName"]
    start = starts_by_call_id.get(data.get("toolCallId"), {})
    return (start.get("data") or {}).get("toolName", "tool")


def _tool_argument_summary(arguments):
    if not isinstance(arguments, dict):
        return ""
    for key in ("command", "path", "filePath", "file_path", "uri"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return _clip_text(value.replace("\n", " "), limit=120)
    return ""


def _render_tool_arguments(arguments):
    if not arguments:
        st.caption("No arguments recorded.")
        return
    if isinstance(arguments, str):
        _wrapped_trace_text(arguments, limit=12000)
        return
    if isinstance(arguments, dict):
        for key in ("command", "path", "filePath", "file_path", "uri"):
            value = arguments.get(key)
            if isinstance(value, str) and value:
                st.caption(key)
                _wrapped_trace_text(value, limit=12000)
        st.caption("Raw arguments")
    st.json(_truncate_for_display(arguments), expanded=False)


def _render_copilot_trace(trace):
    events = trace.get("events") or []
    session_id = trace.get("session_id", "")
    path = trace.get("path", "")

    starts_by_call_id = {
        (event.get("data") or {}).get("toolCallId"): event
        for event in events
        if event.get("type") == "tool.execution_start"
    }
    starts_by_call_id = {key: value for key, value in starts_by_call_id.items() if key}
    tool_completes = [event for event in events if event.get("type") == "tool.execution_complete"]
    assistant_messages = [event for event in events if event.get("type") == "assistant.message"]
    turn_ids = sorted({(event.get("data") or {}).get("turnId") for event in assistant_messages if (event.get("data") or {}).get("turnId")})

    session_start = next((event for event in events if event.get("type") == "session.start"), {})
    session_data = session_start.get("data") or {}
    shutdown = next((event for event in reversed(events) if event.get("type") == "session.shutdown"), {})
    shutdown_data = shutdown.get("data") or {}
    task_complete = next((event for event in reversed(events) if event.get("type") == "session.task_complete"), {})
    task_data = task_complete.get("data") or {}

    st.caption(f"Copilot session `{session_id}` from `{path}`")
    cols = st.columns(4)
    cols[0].metric("Events", len(events))
    cols[1].metric("Turns", len(turn_ids))
    cols[2].metric("Tools", len(tool_completes))
    duration_ms = shutdown_data.get("totalApiDurationMs")
    cols[3].metric("API time", f"{duration_ms / 1000:.1f}s" if isinstance(duration_ms, (int, float)) else "-")

    if session_data:
        st.markdown(
            f"**Model:** `{session_data.get('selectedModel', '-')}`  "
            f"**Copilot:** `{session_data.get('copilotVersion', '-')}`"
        )
    if task_data:
        status = "success" if task_data.get("success") else "failed"
        st.info(f"Task complete ({status}): {task_data.get('summary', '')}")

    tabs = st.tabs(["Timeline", "Tools", "Raw events"])
    with tabs[0]:
        for event in events:
            event_type = event.get("type", "event")
            data = event.get("data") or {}
            timestamp = _event_time(event)
            if event_type in {"hook.start", "hook.end", "assistant.turn_start", "assistant.turn_end"}:
                continue
            if event_type == "system.message":
                with st.expander(f"{timestamp} system prompt", expanded=False):
                    _wrapped_trace_text(data.get("content"), limit=20000)
            elif event_type == "user.message":
                with st.expander(f"{timestamp} user prompt", expanded=False):
                    st.markdown(data.get("content") or "")
            elif event_type == "assistant.message":
                turn_id = data.get("turnId", "?")
                title = data.get("content") or data.get("reasoningText") or "assistant message"
                with st.expander(f"Assistant turn {turn_id}: {_clip_text(title, 120)}", expanded=True):
                    if data.get("content"):
                        st.markdown(data["content"])
                    if data.get("reasoningText"):
                        st.caption("Reasoning summary")
                        _wrapped_trace_text(data["reasoningText"], limit=12000)
                    for request in data.get("toolRequests") or []:
                        label = request.get("intentionSummary") or request.get("name") or "tool"
                        summary = _tool_argument_summary(request.get("arguments"))
                        suffix = f" - {summary}" if summary else ""
                        st.markdown(f"**{request.get('name', 'tool')}:** {label}{suffix}")
                        _render_tool_arguments(request.get("arguments"))
            elif event_type == "tool.execution_start":
                tool_name = data.get("toolName", "tool")
                summary = _tool_argument_summary(data.get("arguments"))
                suffix = f" - {summary}" if summary else ""
                with st.expander(f"{timestamp} tool start: {tool_name}{suffix}", expanded=False):
                    _render_tool_arguments(data.get("arguments"))
            elif event_type == "tool.execution_complete":
                tool_name = _tool_name_for_event(event, starts_by_call_id)
                success = "ok" if data.get("success") else "failed"
                with st.expander(f"{timestamp} tool complete: {tool_name} ({success})", expanded=False):
                    result = data.get("result") or {}
                    if isinstance(result, dict) and result.get("content"):
                        _wrapped_trace_text(result.get("content"), limit=12000)
                    else:
                        st.json(_truncate_for_display(result), expanded=False)
            elif event_type.startswith("session."):
                with st.expander(f"{timestamp} {event_type}", expanded=event_type == "session.start"):
                    st.json(_truncate_for_display(data), expanded=False)
            else:
                with st.expander(f"{timestamp} {event_type}", expanded=False):
                    st.json(_truncate_for_display(data), expanded=False)

    with tabs[1]:
        if not tool_completes:
            st.caption("No tool calls recorded.")
        for event in tool_completes:
            data = event.get("data") or {}
            start = starts_by_call_id.get(data.get("toolCallId"), {})
            start_data = start.get("data") or {}
            tool_name = _tool_name_for_event(event, starts_by_call_id)
            success = "ok" if data.get("success") else "failed"
            with st.expander(f"{_event_time(event)} {tool_name} ({success})", expanded=False):
                if start_data.get("arguments"):
                    st.caption("Arguments")
                    _render_tool_arguments(start_data["arguments"])
                st.caption("Result")
                result = data.get("result") or {}
                if isinstance(result, dict) and result.get("content"):
                    _wrapped_trace_text(result.get("content"), limit=12000)
                else:
                    st.json(_truncate_for_display(result), expanded=False)

    with tabs[2]:
        st.json(_truncate_for_display(events), expanded=False)


def _render_trace(response):
    kind, content = _load_trace(response)
    if kind == "copilot_events":
        _render_copilot_trace(content)
    elif kind == "text":
        _wrapped_trace_text(content, limit=20000)
    elif kind == "json":
        st.json(_truncate_for_display(content), expanded=False)
    else:
        metadata = response.get("metadata") or {}
        session_id = metadata.get("session_id")
        if session_id:
            st.caption(f"No trace file found at `{_copilot_events_path(session_id)}`.")
        else:
            st.caption("No trace available for this response.")


@st.cache_data(show_spinner=False)
def _load_prompt(path, _mtime):
    with open(path) as f:
        return f.read()


def load_prompt_fallback():
    path = os.path.join(_HERE, "prompt.txt")
    if not os.path.exists(path):
        return ""
    return _load_prompt(path, os.path.getmtime(path))


def run_tasks_viewer(tasks_root, default_run_name):
    runs = _list_runs(tasks_root)
    if not runs:
        st.error(f"No task JSON files found in `{tasks_root}`.")
        return

    default_index = runs.index(default_run_name) if default_run_name in runs else 0
    run_name = st.sidebar.selectbox("Run", runs, index=default_index)

    tasks = load_run(tasks_root, run_name)
    if not tasks:
        st.warning(f"Run `{run_name}` contains no tasks.")
        return

    task_idx = st.sidebar.number_input(
        "Task index",
        min_value=0,
        max_value=len(tasks) - 1,
        value=0,
        step=1,
    )
    st.sidebar.markdown(f"**Tasks in run:** {len(tasks)}")
    st.sidebar.markdown(f"**Run dir:** `{tasks_root}`")

    task = tasks[task_idx]
    st.markdown(f"### Task `{task_idx}` — run `{run_name}`")

    input_src = task.get("input", "")
    spaced_input_src = task.get("input_with_space") or input_src
    prompt_src = task.get("prompt") or load_prompt_fallback()
    solution_src = task.get("solution", "")

    class_a_src = _extract_class_source(spaced_input_src, "CalculateA")
    class_b_src = _extract_class_source(spaced_input_src, "CalculateB")

    tabs = st.tabs(["Classes", "Task/Solution", "Input", "Solution", "Prompt"])
    with tabs[0]:
        left, right = st.columns(2)
        with left:
            _render_source_panel("CalculateA", class_a_src or "(missing CalculateA)")
        with right:
            _render_source_panel("CalculateB", class_b_src or "(missing CalculateB)")
    with tabs[1]:
        left, right = st.columns(2)
        with left:
            st.caption("Input with spacing")
            st.code(spaced_input_src or "(missing)", language="python")
        with right:
            st.caption("Solution")
            st.code(solution_src or "(missing)", language="python")
    with tabs[2]:
        st.code(input_src or "(missing)", language="python")
    with tabs[3]:
        st.code(solution_src or "(missing)", language="python")
    with tabs[4]:
        st.code(prompt_src or "(missing)", language="markdown")

    extra_keys = [
        k for k in task
        if k not in ("prompt", "input", "input_with_space", "solution")
    ]
    if extra_keys:
        with st.expander("Other fields", expanded=False):
            st.json({k: task[k] for k in extra_keys})


def run_responses_viewer(data_root, default_run_name):
    tasks_root = os.path.join(data_root, "tasks")
    responses_root = os.path.join(data_root, "responses")
    runs = _list_jsonl_runs(responses_root)
    if not runs:
        st.error(f"No response JSONL files found in `{responses_root}`.")
        return

    default_index = runs.index(default_run_name) if default_run_name in runs else 0
    run_name = st.sidebar.selectbox("Run", runs, index=default_index)

    models = _list_jsonl_models(responses_root, run_name)
    if not models:
        st.error(f"No response models found for run `{run_name}`.")
        return
    model = st.sidebar.selectbox("Model", models)

    records = _latest_records(load_jsonl_records(responses_root, run_name, model))
    if not records:
        st.warning(f"No response records found for `{run_name}/{model}`.")
        return

    tasks = []
    task_path = os.path.join(tasks_root, f"{run_name}.json")
    if os.path.exists(task_path):
        tasks = load_run(tasks_root, run_name)

    record_idx = st.sidebar.selectbox(
        "Response",
        list(range(len(records))),
        format_func=lambda i: f"{i}: {records[i].get('dag_id', '')} [{_result_status(records[i])}]",
    )
    record = records[record_idx]
    task_idx = _task_index_from_record(record)
    task = tasks[task_idx] if task_idx is not None and 0 <= task_idx < len(tasks) else {}

    st.sidebar.markdown(f"**Responses:** `{len(records)}`")
    if tasks:
        st.sidebar.markdown(f"**Tasks in run:** `{len(tasks)}`")
    st.sidebar.markdown(f"**Response dir:** `{responses_root}`")

    title_bits = [f"Response `{record_idx}`", f"run `{run_name}`", f"model `{model}`"]
    if task_idx is not None:
        title_bits.append(f"task `{task_idx}`")
    st.markdown("### " + " — ".join(title_bits))
    status = record.get("status") or (record.get("metadata") or {}).get("status") or "completed"
    st.markdown(
        f"**name:** `{record.get('name', '')}`  \n"
        f"**dag id:** `{record.get('dag_id', '')}`  \n"
        f"**status:** `{status}`"
    )

    files = _parse_codebase(record.get("output"))
    response_src = files.get("solution.py") or record.get("output") or ""
    input_src = task.get("input", "")
    spaced_input_src = task.get("input_with_space") or input_src
    solution_src = task.get("solution", "")

    if record.get("error"):
        st.error(record["error"])
    if not record.get("output"):
        st.warning("This response has no parsed output.")

    tabs = st.tabs(["Compare", "Response", "Trace", "Input", "Solution", "Metadata"])
    with tabs[0]:
        task_view = st.radio(
            "Task view",
            ["Input with spacing", "Solution", "Input compact"],
            horizontal=True,
        )
        if task_view == "Solution":
            task_title = "Task: reference solution"
            task_src = solution_src
        elif task_view == "Input with spacing":
            task_title = "Task: input with spacing"
            task_src = spaced_input_src
        else:
            task_title = "Task: input compact"
            task_src = input_src

        left, right = st.columns(2)
        with left:
            _render_source_panel(task_title, task_src or "(missing task source)")
        with right:
            _render_source_panel("Model response: solution.py", response_src or "(missing response)")

        with st.expander("Task context", expanded=False):
            context_left, context_right = st.columns(2)
            with context_left:
                st.caption("Input with spacing")
                st.code(spaced_input_src or "(missing task input)", language="python")
            with context_right:
                st.caption("Reference solution")
                st.code(solution_src or "(missing reference solution)", language="python")
    with tabs[1]:
        if files:
            selected_file = st.selectbox("Response file", sorted(files), key="response_file")
            _render_source_panel(selected_file, files[selected_file])
        else:
            st.code(response_src or "(missing response)", language="text")
    with tabs[2]:
        _render_trace(record)
    with tabs[3]:
        st.code(input_src or "(missing task input)", language="python")
    with tabs[4]:
        st.code(solution_src or "(missing reference solution)", language="python")
    with tabs[5]:
        metadata = record.get("metadata") or {}
        compact_metadata = {k: v for k, v in metadata.items() if k not in ("stdout", "stderr")}
        st.json({
            "name": record.get("name"),
            "dag_id": record.get("dag_id"),
            "task_index": task_idx,
            "metadata": compact_metadata,
        })
        for stream_name in ("stdout", "stderr"):
            value = metadata.get(stream_name)
            if value:
                with st.expander(stream_name, expanded=False):
                    st.code(value, language="text")


def run_results_viewer(data_root, default_run_name):
    tasks_root = os.path.join(data_root, "tasks")
    responses_root = os.path.join(data_root, "responses")
    results_root = os.path.join(data_root, "results")

    runs = _list_jsonl_runs(results_root)
    if not runs:
        st.error(f"No result JSONL files found in `{results_root}`. Run `merge_code.score` first.")
        return

    default_index = runs.index(default_run_name) if default_run_name in runs else 0
    run_name = st.sidebar.selectbox("Run", runs, index=default_index)

    models = _list_jsonl_models(results_root, run_name)
    if not models:
        st.error(f"No scored models found for run `{run_name}`.")
        return
    model = st.sidebar.selectbox("Model", models)

    results = _latest_records(load_jsonl_records(results_root, run_name, model))
    if not results:
        st.warning(f"No result records found for `{run_name}/{model}`.")
        return

    tasks = []
    task_path = os.path.join(tasks_root, f"{run_name}.json")
    if os.path.exists(task_path):
        tasks = load_run(tasks_root, run_name)
    else:
        st.warning(f"No matching task file found at `{task_path}`.")

    response_by_dag_id = {}
    response_path = os.path.join(responses_root, run_name, *model.split("/")) + ".jsonl"
    if os.path.exists(response_path):
        response_by_dag_id = _records_by_dag_id(_latest_records(load_jsonl_records(responses_root, run_name, model)))
    else:
        st.warning(f"No matching response file found at `{response_path}`.")

    record_idx = st.sidebar.selectbox(
        "Record",
        list(range(len(results))),
        format_func=lambda i: f"{i}: {results[i].get('dag_id', '')} [{_result_status(results[i])}]",
    )
    result = results[record_idx]
    task_idx, task = _task_from_result(tasks, result)
    response = response_by_dag_id.get(result.get("dag_id"), {})

    st.sidebar.markdown(f"**Results:** `{results_root}`")
    st.sidebar.markdown(f"**Responses:** `{responses_root}`")
    if tasks:
        st.sidebar.markdown(f"**Tasks in run:** `{len(tasks)}`")

    title_bits = [f"Result `{record_idx}`", f"run `{run_name}`", f"model `{model}`"]
    if task_idx is not None:
        title_bits.append(f"task `{task_idx}`")
    st.markdown("### " + " — ".join(title_bits))
    st.markdown(
        f"**name:** `{result.get('name', '')}`  \n"
        f"**dag id:** `{result.get('dag_id', '')}`  \n"
        f"**parsed_ok:** `{result.get('parsed_ok', False)}`"
    )
    summary_text = _summary_markdown(result.get("summary"))
    if summary_text:
        st.markdown(summary_text)

    files = _parse_codebase(response.get("output"))
    response_src = files.get("solution.py") or response.get("output") or ""
    input_src = task.get("input", "")
    spaced_input_src = task.get("input_with_space") or input_src
    solution_src = task.get("solution", "")

    if response.get("error"):
        st.error(response["error"])
    if not response:
        st.warning("No response record was found for this scored result.")

    left, right = st.columns(2)
    with left:
        task_tabs = st.tabs(["Input with spacing", "Solution", "Input compact", "Prompt"])
        with task_tabs[0]:
            _render_source_panel("Task: input with spacing", spaced_input_src or "(missing task input)")
        with task_tabs[1]:
            _render_source_panel("Task: reference solution", solution_src or "(missing reference solution)")
        with task_tabs[2]:
            _render_source_panel("Task: input compact", input_src or "(missing task input)")
        with task_tabs[3]:
            st.markdown(task.get("prompt") or load_prompt_fallback() or "(missing prompt)")
    with right:
        response_tabs = st.tabs(["Model response", "Trace", "Raw response", "Metadata"])
        with response_tabs[0]:
            if files:
                selected_file = st.selectbox("Response file", sorted(files), key="result_response_file")
                _render_source_panel(selected_file, files[selected_file])
            else:
                st.code(response_src or "(missing response)", language="text")
        with response_tabs[1]:
            _render_trace(response)
        with response_tabs[2]:
            st.json(response or {"missing": True, "dag_id": result.get("dag_id")}, expanded=False)
        with response_tabs[3]:
            metadata = response.get("metadata") or {}
            compact_metadata = {k: v for k, v in metadata.items() if k not in ("stdout", "stderr")}
            st.json(compact_metadata, expanded=False)
            for stream_name in ("stdout", "stderr"):
                value = metadata.get(stream_name)
                if value:
                    with st.expander(stream_name, expanded=False):
                        st.code(value, language="text")

    st.markdown("### Score Details")
    score_results = result.get("results") or {}
    if not score_results:
        st.info("No score details found for this record.")
        return
    for kind, check_result in score_results.items():
        result_type = check_result.get("type", "?")
        with st.expander(f"{kind}: {result_type}", expanded=result_type != "pass"):
            st.json(check_result.get("metadata") or {}, expanded=False)


def main():
    args = parse_args()
    st.set_page_config(page_title="Merge Code Viewer", layout="wide")
    st.sidebar.title("Merge Code Viewer")

    view = st.sidebar.radio("View", ["tasks", "responses", "results"])
    st.sidebar.markdown(f"**Data root:** `{args.data_root}`")

    if view == "tasks":
        run_tasks_viewer(os.path.join(args.data_root, "tasks"), args.run_name)
    elif view == "responses":
        run_responses_viewer(args.data_root, args.run_name)
    else:
        run_results_viewer(args.data_root, args.run_name)


if __name__ == "__main__":
    main()
