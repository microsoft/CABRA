"""Prompts used to classify coding-agent tool calls."""

from __future__ import annotations


_FORMAT = """
<format>
Return only a single word with your classification, which must be one of:
read, search, understand, edit, test, summary, plan, other.

Do not generate anything else.
</format>
""".strip()


CABRA_PROMPT = f"""
<task>
Classify why a coding agent made the tool call below while solving a synthetic
CABRA programming task.

- Read: View or list files, folders, or exact source text without additional analysis.
- Search: Look for an exact symbol, parameter, function, file, or snippet.
- Understand: Analyze code beyond reading/searching, including dependency, call-graph,
  AST, or runtime-value analysis.
- Edit: Change solution code, directly or through a generated editing script.
- Test: Validate syntax or behavior, reproduce a failure, or create/run test code.
- Summary: Finish the task without another tool call (normally task_complete).
- Plan: Create explicit steps or TODOs.
- Other: Any intent not covered above, such as web research, package installation,
  or file removal.

For generated files or scripts, classify their intended use rather than the mechanism
used to create them. In CABRA tasks, edits to solution.py are Edit; auxiliary files
created to validate the solution are Test.
</task>

<tool_call_information>
{{tool_call}}
</tool_call_information>

{_FORMAT}
""".strip()


SWEBENCH_PROMPT = f"""
<task>
Classify why a coding agent made the tool call below while solving a SWE-bench task.

- Read: View or list files, folders, or exact source text without additional analysis.
- Search: Look for an exact symbol, parameter, function, file, or snippet.
- Understand: Analyze code beyond reading/searching, including dependency, call-graph,
  AST, or runtime-value analysis.
- Edit: Change repository code, directly or through a generated editing script.
- Test: Validate syntax or behavior, reproduce a failure, or create/run test code.
- Summary: Finish the task without another tool call (normally task_complete).
- Plan: Create explicit steps or TODOs.
- Other: Any intent not covered above, such as web research, package installation,
  or file removal.

For generated files or scripts, classify their intended use rather than the mechanism
used to create them.
</task>

<tool_call_information>
{{tool_call}}
</tool_call_information>

{_FORMAT}
""".strip()


PROMPTS = {
    "cabra": CABRA_PROMPT,
    "swebench": SWEBENCH_PROMPT,
}
