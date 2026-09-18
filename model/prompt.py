"""Prompts for full codebase and diff generation."""

RETURN_CODE_PROMPT = """
<instructions>
You are a helpful assistant that solves programming tasks.

You will be given an initial code repository and a problem statement. Your goal is to modify the repository to solve the problem.

Your response must contain exactly ONE <solution> code block with your solution to the problem.
Include a <thought> section before your <solution> where you explain your reasoning process.
Format your response as shown in <format_example>.

<format_example>
<thought>
Your reasoning and analysis here. Explain why you came up with this solution
</thought>

<solution>
Your solution to the problem. Return the entire modified repository in full in the format below:

# === solution.py (any file name) ===
...[insert code]...

This would correspond to writing all of `solution.py`.

</solution>
</format_example>

Failure to follow these rules will cause your response to be rejected.
</instructions>

Here is the initial code repository you must modify:
<code repository>
{code_repository}
</code repository>

Here is the problem statement you must satisfy:
<problem statement>
{problem_statement}
</problem statement>
""".strip()


RETURN_DIFF_PROMPT = """
<instructions>
You are a helpful assistant that solves programming tasks.

You will be given an initial code repository and a problem statement. Your goal is to modify the repository to solve the problem.

Your response must contain exactly ONE <solution> code block with your solution to the problem.
Include a <thought> section before your <solution> where you explain your reasoning process.
Format your response as shown in <format_example>.

<format_example>

<thought>
Your reasoning and analysis here. Explain why you came up with this solution
</thought>

<solution>
Your solution to the problem. For each file that needs to be changed, write out the changes similar to a unified diff like `diff -U0` would produce. Start each hunk of changes with a `@@ ... @@` line. Don't include line numbers like `diff -U0` does.

Return your modifications in the diff format shown below:

```diff
--- app.py
+++ app.py
@@ ... @@
-class MathWeb:
+import sympy
+
+class MathWeb:
@@ ... @@
-def is_prime(x):
-    if x < 2:
-        return False
-    for i in range(2, int(math.sqrt(x)) + 1):
-        if x % i == 0:
-            return False
-    return True
@@ ... @@
-@app.route('/prime/<int:n>')
-def nth_prime(n):
-    count = 0
-    num = 1
-    while count < n:
-        num += 1
-        if is_prime(num):
-            count += 1
-    return str(num)
+@app.route('/prime/<int:n>')
+def nth_prime(n):
+    count = 0
+    num = 1
+    while count < n:
+        num += 1
+        if sympy.isprime(num):
+            count += 1
+    return str(num)
```

This would correspond to replacing the function call to `is_prime` with a call to sympy in a file called app.py
</solution>

Overall, remember to format your solution as:
<thought>
...
</thought>
<solution>
...
</solution>

</format_example>

Failure to follow these rules will cause your response to be rejected.
</instructions>

Here is the initial code repository you must modify:
<code repository>
{code_repository}
</code repository>

Here is the problem statement you must satisfy:
<problem statement>
{problem_statement}
</problem statement>
""".strip()


