"""Test cases for task completion"""

from abc import ABC, abstractmethod
import contextlib
import importlib
import random
import io
import os
import re
import sys
import tempfile
import tokenize
from collections import Counter
from typing import Any, get_origin, get_args
import builtins
import typing
from enum import Enum
import ast
import copy
import inspect
import pytest
import signal
import time
import traceback
import numpy as np


CodePayload = str | dict[str, str]


def _normalize_numpy_alias_for_scoring(source: str) -> str:
    return source.replace("import numpy as np", "import numpy").replace("np.", "numpy.")


def _normalize_numpy_alias_payload(payload: CodePayload) -> CodePayload:
    if isinstance(payload, dict):
        return {
            path: _normalize_numpy_alias_for_scoring(source)
            for path, source in payload.items()
        }
    return _normalize_numpy_alias_for_scoring(payload)


def _compile_code_map(code_map: dict[str, str], label: str) -> None:
    for filename, source in code_map.items():
        compile(source, f"<{label}:{filename}>", "exec")


def _write_code_map(code_map: dict[str, str], root: str) -> set[str]:
    top_modules: set[str] = set()
    for filename, source in code_map.items():
        path = os.path.join(root, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(source)
        top_modules.add(filename.split("/", 1)[0].removesuffix(".py"))
    return top_modules


def _clear_modules(module_names: set[str]) -> None:
    for loaded_name in list(sys.modules):
        if any(
            loaded_name == module_name
            or loaded_name.startswith(f"{module_name}.")
            for module_name in module_names
        ):
            sys.modules.pop(loaded_name, None)


def _execute_code_map_main(code_map: dict[str, str], timeout_seconds: int = 2):
    with tempfile.TemporaryDirectory() as tmpdir:
        top_modules = _write_code_map(code_map, tmpdir)
        previous_path = list(sys.path)

        def _handle_timeout(signum, frame):
            raise TimeoutError(f"Execution exceeded {timeout_seconds}s")

        prev_handler = signal.signal(signal.SIGALRM, _handle_timeout)
        signal.alarm(timeout_seconds)
        try:
            sys.path.insert(0, tmpdir)
            importlib.invalidate_caches()
            _clear_modules(top_modules)
            main_module = importlib.import_module("main")
            main_function = getattr(main_module, "main")
            if not callable(main_function):
                raise AssertionError("main.py does not define callable main().")
            return main_function()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev_handler)
            _clear_modules(top_modules)
            sys.path[:] = previous_path
            importlib.invalidate_caches()


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> set[str]:
    def _norm(v: str | None) -> str | None:
        return None if v is None else v.rstrip("\n")
    paths = set(before) | set(after)
    return {path for path in paths if _norm(before.get(path)) != _norm(after.get(path))}


def _memoize_value_key(value):
    """Build a hashable key for a single argument value (handles ndarrays)."""
    if isinstance(value, np.ndarray):
        return ('ndarray', value.shape, value.dtype.str, value.tobytes())
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_memoize_value_key(v) for v in value))
    if isinstance(value, dict):
        return ('dict', tuple((k, _memoize_value_key(v)) for k, v in sorted(value.items())))
    return (type(value).__name__, value)


def _memoize_dag_functions(ns: dict, filename: str) -> None:
    """To speed up evaluation, we memoize function calls."""
    import functools

    for name, obj in list(ns.items()):
        code = getattr(obj, '__code__', None)
        if code is None or code.co_filename != filename:
            continue

        def _make(fn):
            cache: dict = {}

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                try:
                    cache_key = (
                        tuple(_memoize_value_key(a) for a in args),
                        tuple((k, _memoize_value_key(v)) for k, v in sorted(kwargs.items())),
                    )
                except Exception:
                    return fn(*args, **kwargs)
                if cache_key in cache:
                    return cache[cache_key]
                result = fn(*args, **kwargs)
                cache[cache_key] = result
                return result

            return wrapper

        ns[name] = _make(obj)

class TestCaseType(Enum):
    """Enum for test case result types."""
    PASS = 'pass'
    FAIL = 'fail'
    ERROR = 'error'

class TestCaseKind(Enum):
    """Discriminator used when (de)serializing test cases."""
    COMPILATION = 'compilation'
    FUNCTION_EXISTENCE = 'function_existence'
    BEHAVIORAL = 'behavioral'
    EDIT_PATH = 'edit_path'
    SEMANTIC_COMMENTS = 'semantic_comments'
    CONSTRAINT_STRUCTURE = 'constraint_structure'
    BRANCH_PLACEMENT = 'branch_placement'
    FUNCTION_COMMENTS = 'function_comments'

class TestCaseResult:
    """Result of a test case execution."""
    
    def __init__(self, test_case_type: TestCaseType, metadata: dict = None):
        self.test_case_type = test_case_type
        self.metadata = metadata or {}
        
    def score(self) -> float:
        """Calculate the score for the test case result."""
        if self.test_case_type == TestCaseType.PASS:
            return 1.0
        elif self.test_case_type == TestCaseType.FAIL:
            return 0.0
        else:
            return None

class TestCaseSuite:
    """A collection of test cases."""
    
    def __init__(self, test_cases: list[TestCase] = None):
        self.test_cases = test_cases or []

    def run_all(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> list[TestCaseResult]:
        """Run all test cases in the suite."""
        return [test_case.run(code, starter_code, solution) for test_case in self.test_cases]
    
    def summary(self, results: list[TestCaseResult]) -> dict:
        """Summarize a list of TestCaseResult objects produced by run_all."""
        by_kind: dict[str, dict] = {}
        for tc, r in zip(self.test_cases, results):
            kind = tc.KIND.value
            bucket = by_kind.setdefault(kind, {'pass': 0, 'fail': 0, 'error': 0})
            bucket[r.test_case_type.value] += 1
        for kind, counts in by_kind.items():
            total = counts['pass'] + counts['fail'] + counts['error']
            counts['pass_rate'] = counts['pass'] / total if total else 0.0
        return by_kind
        
    @classmethod
    def create(cls, **kwargs) -> "TestCaseSuite":
        """Create a test case suite. Kwargs are routed to whichever subclass accepts them; unused keys are reported."""
        classes = [
            CompilationTestCase,
            FunctionExistenceTestCase,
            BehavioralTestCase,
            EditPathTestCase,
            ConstraintStructureTestCase,
            BranchPlacementTestCase,
        ]

        def accepted(c) -> set[str]:
            params = inspect.signature(c).parameters
            if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
                return set(kwargs)
            return set(params)

        all_accepted = set().union(*(accepted(c) for c in classes))
        unused = sorted(set(kwargs) - all_accepted)
        if unused:
            print(f"[TestCaseSuite.create] Dropping variables unused by all test cases: {unused}")

        return cls([
            c(**{k: v for k, v in kwargs.items() if k in accepted(c)})
            for c in classes
        ])
        
    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return [test_case.to_dict() for test_case in self.test_cases]
    
    def from_dict(cls, d: dict) -> "TestCaseSuite":
        """Create a test case suite from a JSON-safe dict."""
        return cls([
            TestCase.from_dict(test_case_dict) for test_case_dict in d['test_cases']
        ])

class TestCase(ABC):
    """Base class for test cases."""

    KIND: TestCaseKind

    @abstractmethod
    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        """Run the test case."""
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        ...

    @classmethod
    def from_dict(cls, d: dict) -> "TestCase":
        kind = TestCaseKind(d['kind'])
        return TEST_CASE_REGISTRY[kind]._from_dict(d)

    @classmethod
    @abstractmethod
    def _from_dict(cls, d: dict) -> "TestCase":
        ...
    
class CompilationTestCase(TestCase):
    """Evaluates whether the program compiles"""

    KIND = TestCaseKind.COMPILATION

    def to_dict(self) -> dict:
        return {'kind': self.KIND.value}

    @classmethod
    def _from_dict(cls, d: dict) -> "CompilationTestCase":
        return cls()

    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        """Run the test case."""
        try:
            if isinstance(code, dict):
                _compile_code_map(code, "candidate")
            else:
                compile(code, '<string>', 'exec')
            return TestCaseResult(TestCaseType.PASS)
        except Exception as e:
            return TestCaseResult(TestCaseType.ERROR, metadata={'error': str(e)})

class FunctionExistenceTestCase(TestCase):
    """
    Evaluates whether all of the required functions are in the solution
    This is used for the dead code tasks, as just behavioral testing would allow the model to pass by not deleting anything
    """

    KIND = TestCaseKind.FUNCTION_EXISTENCE

    def to_dict(self) -> dict:
        return {'kind': self.KIND.value}

    @classmethod
    def _from_dict(cls, d: dict) -> "FunctionExistenceTestCase":
        return cls()
    
    def _top_level_function_names(self, source: str) -> set[str]:
        return {
            node.name for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        """Run the test case."""
        try:
            if isinstance(code, dict) or isinstance(starter_code, dict) or isinstance(solution, dict):
                if not all(isinstance(payload, dict) for payload in (code, starter_code, solution)):
                    return TestCaseResult(
                        TestCaseType.ERROR,
                        metadata={
                            'error': 'candidate, starter, and solution must all be code maps',
                            'candidate_type': type(code).__name__,
                            'starter_type': type(starter_code).__name__,
                            'solution_type': type(solution).__name__,
                        },
                    )
                starter_paths = set(starter_code)
                solution_paths = set(solution)
                parsed_paths = set(code)
                must_have = solution_paths
                cannot_have = starter_paths - solution_paths
                missing = must_have - parsed_paths
                forbidden = cannot_have & parsed_paths
                extras = parsed_paths - must_have - cannot_have
                metadata = {
                    'must_have_paths': sorted(must_have),
                    'cannot_have_paths': sorted(cannot_have),
                    'parsed_paths': sorted(parsed_paths),
                }
                if missing or forbidden or extras:
                    metadata['missing_paths'] = sorted(missing)
                    metadata['forbidden_paths'] = sorted(forbidden)
                    metadata['extra_paths'] = sorted(extras)
                    return TestCaseResult(TestCaseType.FAIL, metadata=metadata)
                return TestCaseResult(TestCaseType.PASS, metadata=metadata)

            starter_fns = self._top_level_function_names(starter_code)
            solution_fns = self._top_level_function_names(solution)
            must_have = solution_fns
            cannot_have = starter_fns - solution_fns

            tree = ast.parse(code)
            parsed_functions = {
                node.name for node in tree.body if isinstance(node, ast.FunctionDef)
            }

            metadata = {
                'must_have_functions': sorted(must_have),
                'cannot_have_functions': sorted(cannot_have),
                'parsed_functions': sorted(parsed_functions),
            }

            missing = must_have - parsed_functions
            forbidden = cannot_have & parsed_functions
            extras = parsed_functions - must_have - cannot_have

            global_vars = []
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            global_vars.append(target.id)
                elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                    if isinstance(node.target, ast.Name):
                        global_vars.append(node.target.id)

            if missing or forbidden or extras:
                metadata['missing_functions'] = sorted(missing)
                metadata['forbidden_functions'] = sorted(forbidden)
                metadata['extra_functions'] = sorted(extras)
                return TestCaseResult(TestCaseType.FAIL, metadata=metadata)

            if global_vars:
                metadata['global_variables'] = global_vars
                return TestCaseResult(TestCaseType.FAIL, metadata=metadata)

            return TestCaseResult(TestCaseType.PASS, metadata=metadata)
        except Exception as e:
            return TestCaseResult(TestCaseType.ERROR, metadata={'error': str(e)})

class BehavioralTestCase(TestCase):
    """
    Evaluate whether the generated program matches the outputs of a ground truth program
    We check five random inputs for each function and use black-box testing
    All tasks use this metric
    """

    KIND = TestCaseKind.BEHAVIORAL

    SAFE_BUILTINS = {
        name: getattr(builtins, name) for name in (
            'abs', 'all', 'any', 'bin', 'bool', 'chr', 'dict', 'divmod',
            'enumerate', 'filter', 'float', 'hex', 'int', 'isinstance',
            'issubclass', 'len', 'list', 'map', 'max', 'min', 'oct', 'ord',
            'pow', 'print', 'range', 'repr', 'reversed', 'round', 'set',
            'slice', 'sorted', 'str', 'sum', 'tuple', 'type', 'zip',
            'True', 'False', 'None', 'Exception', 'ValueError', 'TypeError',
            'IndexError', 'KeyError', 'ZeroDivisionError',
        ) if hasattr(builtins, name)
    }

    def __init__(
        self,
        num_tests: int = 5,
        seed: int = 42,
        timeout_seconds: int = 2,
        prefix_blocks: list[str] = None,
        include_main: bool = False,
        max_failures: int | None = 5,
        semantic_categories: list[str] | None = None,
        semantic_target_category: str | None = None,
        semantic_target_docstring: str | dict[str, str] | None = None,
        memoize: bool = False,
    ):
        self.num_tests = num_tests
        self.seed = seed
        self.timeout_seconds = timeout_seconds
        self.prefix_blocks = prefix_blocks or []
        self.include_main = include_main
        self.max_failures = max_failures
        self.semantic_categories = semantic_categories or []
        self.semantic_target_category = semantic_target_category
        self.semantic_target_docstring = semantic_target_docstring
        self.memoize = memoize
        self.rng = random.Random(self.seed)

    def to_dict(self) -> dict:
        return {
            'kind': self.KIND.value,
            'num_tests': self.num_tests,
            'seed': self.seed,
            'timeout_seconds': self.timeout_seconds,
            'prefix_blocks': self.prefix_blocks,
            'include_main': self.include_main,
            'max_failures': self.max_failures,
            'semantic_categories': self.semantic_categories,
            'semantic_target_category': self.semantic_target_category,
            'semantic_target_docstring': self.semantic_target_docstring,
        }

    @classmethod
    def _from_dict(cls, d: dict) -> "BehavioralTestCase":
        return cls(
            num_tests=d['num_tests'],
            seed=d.get('seed', 42),
            timeout_seconds=d.get('timeout_seconds', 2),
            prefix_blocks=d.get('prefix_blocks', []),
            include_main=d.get('include_main', False),
            max_failures=d.get('max_failures', 5),
            semantic_categories=d.get('semantic_categories', []),
            semantic_target_category=d.get('semantic_target_category'),
            semantic_target_docstring=d.get('semantic_target_docstring'),
        )

    def compare_outputs(self, pred, true, rel_tol: float = 1e-6, abs_tol: float = 1e-9):
        if isinstance(pred, np.ndarray) or isinstance(true, np.ndarray):
            try:
                pred_arr = np.asarray(pred)
                true_arr = np.asarray(true)
            except Exception:
                return False
            if pred_arr.shape != true_arr.shape:
                return False
            return bool(np.allclose(pred_arr, true_arr, rtol=rel_tol, atol=abs_tol, equal_nan=True))
        if isinstance(pred, (tuple, list)) and isinstance(true, (tuple, list)):
            if type(pred) is not type(true) or len(pred) != len(true):
                return False
            return all(self.compare_outputs(p, t, rel_tol, abs_tol) for p, t in zip(pred, true))
        try:
            return pred == pytest.approx(true, rel=rel_tol, abs=abs_tol, nan_ok=True)
        except TypeError:
            return pred == true

    def random_input(self, tp):
        if tp is bool:
            return self.rng.choice([True, False])
        if tp is int:
            return self.rng.randint(1, 5)
        if tp is float:
            return self.rng.uniform(-1.0, 1.0)
        if tp is str:
            length = self.rng.randint(1, 10)
            return ''.join(self.rng.choice('0123456789') for _ in range(length))
        if tp is np.ndarray:
            length = self.rng.randint(1, 5)
            return np.array([self.rng.uniform(-1.0, 1.0) for _ in range(length)])

        origin = get_origin(tp)
        args = get_args(tp)

        if tp is list or origin is list:
            item_type = args[0] if args else int
            length = self.rng.randint(0, 5)
            return [self.random_input(item_type) for _ in range(length)]

        raise ValueError(f"Unsupported type: {tp}")

    def _prepare_program_globals(self, compiled_code, compiled_solution, code: str, solution: str, timeout_seconds: int | None = None):
        """Build a sandbox (optionally with a fresh prefix to define `mylibrary` functions) and exec the precompiled programs into it."""
        sandbox_globals: dict = {'__builtins__': self.SAFE_BUILTINS, 'np': np, 'numpy': np}
        chosen_prefix = ''
        if self.prefix_blocks:
            prefix_ns: dict = {'__builtins__': vars(builtins)}
            chosen_prefix = _normalize_numpy_alias_for_scoring(self.rng.choice(self.prefix_blocks))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exec(chosen_prefix, prefix_ns)
            for k, v in prefix_ns.items():
                if k != '__builtins__':
                    sandbox_globals[k] = v

        timeout_seconds = self.timeout_seconds if timeout_seconds is None else timeout_seconds

        def _handle_timeout(signum, frame):
            raise TimeoutError(f"Execution exceeded {timeout_seconds}s")

        prev_handler = signal.signal(signal.SIGALRM, _handle_timeout)
        signal.alarm(timeout_seconds)
        try:
            sol_globals = dict(sandbox_globals)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exec(compiled_solution, sol_globals)
            except Exception as exc:
                setattr(exc, 'exec_metadata', {
                    'phase': 'solution_exec',
                    'traceback': traceback.format_exc(),
                })
                raise

            cand_globals = dict(sandbox_globals)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exec(compiled_code, cand_globals)
            except Exception as exc:
                setattr(exc, 'exec_metadata', {
                    'phase': 'candidate_exec',
                    'traceback': traceback.format_exc(),
                })
                raise

            if self.memoize:
                _memoize_dag_functions(sol_globals, compiled_solution.co_filename)
                _memoize_dag_functions(cand_globals, compiled_code.co_filename)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev_handler)

        full_code = chosen_prefix + '\n' + code if chosen_prefix else code
        full_solution = chosen_prefix + '\n' + solution if chosen_prefix else solution
        return sol_globals, cand_globals, full_code, full_solution

    def compare_program_executions(self, sol_globals: dict, cand_globals: dict, function_name: str, inputs: dict, full_code: str, full_solution: str, timeout_seconds: int | None = None) -> Any:
        """Call the prepared solution and candidate functions with `inputs`."""
        timeout_seconds = self.timeout_seconds if timeout_seconds is None else timeout_seconds

        def _handle_timeout(signum, frame):
            raise TimeoutError(f"Execution exceeded {timeout_seconds}s")

        prev_handler = signal.signal(signal.SIGALRM, _handle_timeout)
        signal.alarm(timeout_seconds)
        try:
            sol_fn = sol_globals[function_name]
            sol_call = ', '.join(f"{name}={value!r}" for name, value in inputs.items())
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    true_output = sol_fn(**inputs)
            except Exception as exc:
                setattr(exc, 'exec_metadata', {
                    'phase': 'solution_call',
                    'function': function_name,
                    'inputs': inputs,
                    'call': f"{function_name}({sol_call})",
                    'traceback': traceback.format_exc(),
                })
                raise

            cand_fn = cand_globals[function_name]
            orderings: list[dict] = []
            last_pred = None
            kw_names = list(inputs.keys())
            kw_values = tuple(inputs.values())
            kw_call_expr = f"{function_name}({sol_call})"
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    pred = cand_fn(**inputs)
            except TypeError:
                pred = None
            except Exception as exc:
                err_tb = ''.join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
                orderings.append({
                    'inputs': {'ordering_names': kw_names, 'ordering_values': list(kw_values)},
                    'status': 'error',
                    'call': kw_call_expr,
                    'error': str(exc),
                    'traceback': err_tb,
                })
                pred = None
            else:
                last_pred = pred
                if self.compare_outputs(pred, true_output):
                    orderings.append({
                        'inputs': {'ordering_names': kw_names, 'ordering_values': list(kw_values)},
                        'status': 'pass',
                        'call': kw_call_expr,
                        'error': None,
                        'traceback': None,
                    })
                    return pred, true_output, True, full_code, full_solution, orderings
                orderings.append({
                    'inputs': {'ordering_names': kw_names, 'ordering_values': list(kw_values)},
                    'status': 'fail',
                    'call': kw_call_expr,
                    'error': None,
                    'traceback': None,
                })
                # kwargs matched but answer was wrong — no need to try permutations.
                return last_pred, true_output, False, full_code, full_solution, orderings

            values = list(inputs.values())
            value_names = list(inputs.keys())
            ordering = tuple(values)
            call = ', '.join(repr(v) for v in ordering)
            call_expr = f"{function_name}({call})"
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    pred = cand_fn(*ordering)
            except Exception as exc:
                err_tb = ''.join(
                    traceback.format_exception(
                        type(exc),
                        exc,
                        exc.__traceback__,
                    )
                )
                orderings.append({
                    'inputs': {
                        'ordering_names': value_names,
                        'ordering_values': list(ordering),
                    },
                    'status': 'error',
                    'call': call_expr,
                    'error': str(exc),
                    'traceback': err_tb,
                })
                setattr(exc, 'exec_metadata', {
                    'phase': 'candidate_eval',
                    'function': function_name,
                    'inputs': inputs,
                    'attempted_orderings': len(orderings),
                    'orderings': orderings,
                    'traceback': ''.join(
                        traceback.format_exception(
                            type(exc),
                            exc,
                            exc.__traceback__,
                        )
                    ),
                })
                raise exc
            last_pred = pred
            if self.compare_outputs(pred, true_output):
                orderings.append({
                    'inputs': {
                        'ordering_names': value_names,
                        'ordering_values': list(ordering),
                    },
                    'status': 'pass',
                    'call': call_expr,
                    'error': None,
                    'traceback': None,
                })
                return pred, true_output, True, full_code, full_solution, orderings

            orderings.append({
                'inputs': {
                    'ordering_names': value_names,
                    'ordering_values': list(ordering),
                },
                'status': 'fail',
                'call': call_expr,
                'error': None,
                'traceback': None,
            })
            return last_pred, true_output, False, full_code, full_solution, orderings
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev_handler)

    def _resolve_annotation(self, node: ast.expr):
        if node is None:
            raise ValueError("Missing annotation; cannot infer input type")
        src = ast.unparse(node)
        namespace = {**vars(builtins), **vars(typing), 'np': np, 'numpy': np}
        return eval(src, namespace)

    def _filter_to_fns(self, tree: ast.AST, allowed_names: set[str] | None = None) -> ast.AST:
        """Keep only FunctionDefs (optionally restricted to allowed_names); drop everything else."""
        new_tree = copy.deepcopy(tree)
        new_tree.body = [
            n for n in new_tree.body
            if isinstance(n, ast.FunctionDef)
            and (self.include_main or n.name != 'main')
            and (allowed_names is None or n.name in allowed_names)
        ]
        ast.fix_missing_locations(new_tree)
        return new_tree

    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        """Run the test case."""
        try:
            if isinstance(code, dict) or isinstance(solution, dict):
                if not isinstance(code, dict) or not isinstance(solution, dict):
                    return TestCaseResult(
                        TestCaseType.ERROR,
                        metadata={
                            'error': 'candidate and solution must both be code maps',
                            'candidate_type': type(code).__name__,
                            'solution_type': type(solution).__name__,
                        },
                    )
                code = _normalize_numpy_alias_payload(code)
                solution = _normalize_numpy_alias_payload(solution)
                effective_timeout_seconds = self.timeout_seconds
                _compile_code_map(code, "candidate")
                _compile_code_map(solution, "solution")
                pred = _execute_code_map_main(code, effective_timeout_seconds)
                true = _execute_code_map_main(solution, effective_timeout_seconds)
                passed = self.compare_outputs(pred, true)
                metadata = {
                    'expected': true,
                    'actual': pred,
                    'timeout_seconds': effective_timeout_seconds,
                    'candidate_paths': sorted(code),
                    'solution_paths': sorted(solution),
                }
                return TestCaseResult(
                    TestCaseType.PASS if passed else TestCaseType.FAIL,
                    metadata=metadata,
                )

            solution_tree = self._filter_to_fns(ast.parse(solution))
            solution_fns = {
                n.name: n for n in solution_tree.body
                if isinstance(n, ast.FunctionDef)
            }
            effective_timeout_seconds = self.timeout_seconds
            code_tree = self._filter_to_fns(ast.parse(code), set(solution_fns))
            fn_specs: list[tuple[str, list]] = []
            for node in code_tree.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                if self.semantic_categories and self.semantic_target_category and re.search(r"\d+$", node.name):
                    continue
                sol_fn = solution_fns.get(node.name)
                if sol_fn is None:
                    return TestCaseResult(
                        TestCaseType.ERROR,
                        metadata={'error': f'No matching solution function: {node.name}'},
                    )
                try:
                    arg_specs_for_fn = [
                        (a.arg, self._resolve_annotation(a.annotation))
                        for a in sol_fn.args.args
                    ]
                except ValueError as e:
                    bad = [a.arg for a in sol_fn.args.args if a.annotation is None]
                    return TestCaseResult(
                        TestCaseType.ERROR,
                        metadata={
                            'error': str(e),
                            'function': node.name,
                            'unannotated_args': bad,
                        },
                    )
                fn_specs.append((node.name, arg_specs_for_fn))

            timings = {'random_input': 0.0, 'execute': 0.0}
            passed_trials: list[dict] = []
            failed_trials: list[dict] = []
            errored_trials: list[dict] = []
            num_passed = 0
            num_failed = 0
            num_errored = 0
            stopped_early = False
            first_failure: dict | None = None
            unparsed_code = ast.unparse(code_tree)
            unparsed_solution = ast.unparse(solution_tree)
            unparsed_code = _normalize_numpy_alias_for_scoring(unparsed_code)
            unparsed_solution = _normalize_numpy_alias_for_scoring(unparsed_solution)
            compiled_code = compile(unparsed_code, '<candidate>', 'exec')
            compiled_solution = compile(unparsed_solution, '<solution>', 'exec')
            cached_globals = None
            if not self.prefix_blocks:
                cached_globals = self._prepare_program_globals(
                    compiled_code, compiled_solution, unparsed_code, unparsed_solution,
                    timeout_seconds=effective_timeout_seconds,
                )
            for trial_idx in range(self.num_tests):
                if cached_globals is not None:
                    sol_globals, cand_globals, full_code, full_solution = cached_globals
                else:
                    sol_globals, cand_globals, full_code, full_solution = self._prepare_program_globals(
                        compiled_code, compiled_solution, unparsed_code, unparsed_solution,
                        timeout_seconds=effective_timeout_seconds,
                    )
                for fn_name, arg_specs_for_fn in fn_specs:
                    t2 = time.perf_counter()
                    random_inputs = {name: self.random_input(t) for name, t in arg_specs_for_fn}
                    t3 = time.perf_counter()
                    trial: dict = {
                        'trial': trial_idx,
                        'function': fn_name,
                        'inputs': random_inputs,
                        'orderings': [],
                    }
                    try:
                        pred_output, true_output, comparison_result, exec_code, exec_solution, orderings = self.compare_program_executions(
                            sol_globals, cand_globals, fn_name, random_inputs, full_code, full_solution,
                            timeout_seconds=effective_timeout_seconds,
                        )
                        trial.update({
                            'expected': true_output,
                            'actual': pred_output,
                            'status': 'pass' if comparison_result else 'fail',
                            'orderings': orderings,
                        })
                        if comparison_result:
                            num_passed += 1
                            passed_trials.append(trial)
                        else:
                            num_failed += 1
                            failed_trials.append(trial)
                            if first_failure is None:
                                first_failure = {
                                    'function': fn_name,
                                    'inputs': random_inputs,
                                    'expected': true_output,
                                    'actual': pred_output,
                                    'code': exec_code,
                                    'solution': exec_solution,
                                    'orderings': orderings,
                                }
                    except Exception as exc:
                        num_errored += 1
                        trial['status'] = 'error'
                        trial['error'] = str(exc)
                        trial['error_type'] = type(exc).__name__
                        trial['error_repr'] = repr(exc)
                        trial['traceback'] = traceback.format_exc()
                        exec_metadata = getattr(exc, 'exec_metadata', None)
                        if exec_metadata:
                            trial['exec_error'] = exec_metadata
                            if 'orderings' in exec_metadata:
                                trial['orderings'] = exec_metadata['orderings']
                        errored_trials.append(trial)
                        if first_failure is None:
                            first_failure = {
                                'trial': trial_idx,
                                'function': fn_name,
                                'inputs': random_inputs,
                                'error': str(exc),
                                'error_type': type(exc).__name__,
                                'error_repr': repr(exc),
                                'traceback': traceback.format_exc(),
                            }
                            if exec_metadata:
                                first_failure['exec_error'] = exec_metadata
                    t4 = time.perf_counter()
                    timings['random_input'] += t3 - t2
                    timings['execute'] += t4 - t3
                    if self.max_failures is not None and num_failed + num_errored >= self.max_failures:
                        stopped_early = True
                        break
                if stopped_early:
                    break

            total = num_passed + num_failed + num_errored
            metadata = {
                'total': total,
                'passed': num_passed,
                'failed': num_failed,
                'errored': num_errored,
                'pass_rate': (num_passed / total) if total else 0.0,
                'timeout_seconds': effective_timeout_seconds,
                'stopped_early': stopped_early,
                'max_failures': self.max_failures,
                'passed_trials': passed_trials,
                'failed_trials': failed_trials,
                'errored_trials': errored_trials,
            }
            if num_failed == 0 and num_errored == 0:
                return TestCaseResult(TestCaseType.PASS, metadata=metadata)
            if first_failure is not None:
                metadata['first_failure'] = first_failure
            kind = TestCaseType.ERROR if num_passed == 0 and num_errored > 0 else TestCaseType.FAIL
            return TestCaseResult(kind, metadata=metadata)
        except Exception as e:
            return TestCaseResult(
                TestCaseType.ERROR,
                metadata={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'error_repr': repr(e),
                    'traceback': traceback.format_exc(),
                },
            )

class EditPathTestCase(TestCase):
    """
    Evaluates whether the model edited the right files/functions that we expected
    A useful debugging metric, but not used as a primary evaluation metric
    """

    KIND = TestCaseKind.EDIT_PATH

    def to_dict(self) -> dict:
        return {'kind': self.KIND.value}

    @classmethod
    def _from_dict(cls, d: dict) -> "EditPathTestCase":
        return cls()

    @staticmethod
    def _function_sources(source: str) -> dict[str, str]:
        """Map top-level function name -> normalized source via ast.unparse."""
        return {
            node.name: ast.unparse(node)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    @classmethod
    def _changed_functions(cls, before: str, after: str) -> set[str]:
        b = cls._function_sources(before)
        a = cls._function_sources(after)
        names = set(b) | set(a)
        return {n for n in names if b.get(n) != a.get(n)}

    @staticmethod
    def _function_signatures(source: str) -> dict[str, list[str]]:
        """Map top-level function name -> ordered list of parameter names."""
        out = {}
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef):
                params = [a.arg for a in node.args.args]
                params += [a.arg for a in node.args.kwonlyargs]
                if node.args.vararg:
                    params.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg:
                    params.append(f"**{node.args.kwarg.arg}")
                out[node.name] = params
        return out

    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        """Compare which functions changed in the candidate vs the solution, plus check that shared functions have matching parameter signatures."""
        try:
            if isinstance(code, dict) or isinstance(starter_code, dict) or isinstance(solution, dict):
                if not all(isinstance(payload, dict) for payload in (code, starter_code, solution)):
                    return TestCaseResult(
                        TestCaseType.ERROR,
                        metadata={
                            'error': 'candidate, starter, and solution must all be code maps',
                            'candidate_type': type(code).__name__,
                            'starter_type': type(starter_code).__name__,
                            'solution_type': type(solution).__name__,
                        },
                    )
                expected = _changed_paths(starter_code, solution)
                actual = _changed_paths(starter_code, code)
                metadata = {
                    'expected_edits': sorted(expected),
                    'actual_edits': sorted(actual),
                }
                if expected != actual:
                    metadata['missing_edits'] = sorted(expected - actual)
                    metadata['unexpected_edits'] = sorted(actual - expected)
                    return TestCaseResult(TestCaseType.FAIL, metadata=metadata)
                return TestCaseResult(TestCaseType.PASS, metadata=metadata)

            expected = self._changed_functions(starter_code, solution)
            actual = self._changed_functions(starter_code, code)

            cand_sigs = self._function_signatures(code)
            sol_sigs = self._function_signatures(solution)
            shared = set(cand_sigs) & set(sol_sigs)
            signature_mismatches = {
                name: {'candidate': cand_sigs[name], 'solution': sol_sigs[name]}
                for name in shared if cand_sigs[name] != sol_sigs[name]
            }

            metadata = {
                'expected_edits': sorted(expected),
                'actual_edits': sorted(actual),
            }

            failed = False
            if expected != actual:
                metadata['missing_edits'] = sorted(expected - actual)
                metadata['unexpected_edits'] = sorted(actual - expected)
                failed = True
            if signature_mismatches:
                metadata['signature_mismatches'] = signature_mismatches

            return TestCaseResult(TestCaseType.FAIL if failed else TestCaseType.PASS, metadata=metadata)
        except Exception as e:
            return TestCaseResult(TestCaseType.ERROR, metadata={'error': str(e)})
        

class FunctionCommentsTestCase(TestCase):
    """Verify that reference-marked functions contain the requested comment."""

    KIND = TestCaseKind.FUNCTION_COMMENTS

    def __init__(self, expected_comment: str):
        self.expected_comment = expected_comment

    def to_dict(self) -> dict:
        return {
            'kind': self.KIND.value,
            'expected_comment': self.expected_comment,
        }

    @classmethod
    def _from_dict(cls, d: dict) -> "FunctionCommentsTestCase":
        return cls(expected_comment=d['expected_comment'])

    @staticmethod
    def _function_comments(source: str) -> dict[str, list[str]]:
        tree = ast.parse(source)
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        comments: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            end_lineno = getattr(node, 'end_lineno', None)
            if end_lineno is None:
                continue
            comments[node.name] = [
                token.string
                for token in tokens
                if token.type == tokenize.COMMENT
                and node.lineno < token.start[0] <= end_lineno
                and token.start[1] > node.col_offset
            ]
        return comments

    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        if not all(isinstance(payload, str) for payload in (code, starter_code, solution)):
            return TestCaseResult(
                TestCaseType.ERROR,
                metadata={'error': 'function comment tasks require string code payloads'},
            )
        try:
            function_comments = self._function_comments(code)
            solution_comments = self._function_comments(solution)
            expected_functions = {
                name
                for name, comments in solution_comments.items()
                if self.expected_comment in comments
            }
            missing = sorted(
                name
                for name in expected_functions
                if self.expected_comment not in function_comments.get(name, [])
            )
            metadata = {
                'expected_comment': self.expected_comment,
                'checked_functions': sorted(expected_functions),
                'missing_comment_functions': missing,
            }
            return TestCaseResult(
                TestCaseType.FAIL if missing else TestCaseType.PASS,
                metadata=metadata,
            )
        except Exception as e:
            return TestCaseResult(TestCaseType.ERROR, metadata={'error': str(e)})


class ConstraintStructureTestCase(TestCase):
    """
    Verify the inert, instruction-following constraints that the behavioral test cannot observe.
    This is compatible with all tasks except remove dead code, as in remove dead code, the model can only delete functions
    """

    KIND = TestCaseKind.CONSTRAINT_STRUCTURE

    _MULT_RE = re.compile(r"^(mult|prefix|key|slow)\d+$")
    _MULT_TOKEN_RE = re.compile(r"\b(?:mult|prefix|key|slow)\d+\b")
    _CATEGORIES = ('asserts', 'prints', 'temps', 'updates', 'comments')
    _CATEGORY_RANK = {'comment': 0, 'assert': 1, 'print': 2, 'temp': 3, 'update': 4}
    _CMP_OPS = {
        ast.Eq: '==', ast.NotEq: '!=',
        ast.Lt: '<', ast.LtE: '<=', ast.Gt: '>', ast.GtE: '>=',
    }
    # Operator after flipping a comparison left<->right.
    _CMP_FLIP = {'==': '==', '!=': '!=', '<': '>', '<=': '>=', '>': '<', '>=': '<='}
    _MULT_SENTINEL = '\x00'

    def to_dict(self) -> dict:
        return {'kind': self.KIND.value}

    @classmethod
    def _from_dict(cls, d: dict) -> "ConstraintStructureTestCase":
        return cls()

    @classmethod
    def _mult_names(cls, *sources: str) -> set[str]:
        """Collect every generated constraint value name across the sources."""
        names: set[str] = set()
        for source in sources:
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.arg) and cls._MULT_RE.match(node.arg):
                    names.add(node.arg)
                elif isinstance(node, ast.Name) and cls._MULT_RE.match(node.id):
                    names.add(node.id)
        return names

    @staticmethod
    def _functions(source: str) -> dict[str, ast.FunctionDef]:
        return {
            node.name: node
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    @staticmethod
    def _literal(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(round(value, 10))
        if isinstance(value, str):
            return value
        return None

    @classmethod
    def _flatten_parts(cls, node: ast.expr) -> list[tuple[str, Any]]:
        """
        Flatten a string expression into ('lit', str) / ('expr', node) parts.
        Handles ``+`` concatenation and f-strings so both render identically.
        """
        
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return cls._flatten_parts(node.left) + cls._flatten_parts(node.right)
        if isinstance(node, ast.JoinedStr):
            parts: list[tuple[str, Any]] = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(('lit', str(v.value)))
                elif isinstance(v, ast.FormattedValue):
                    parts.append(('expr', v.value))
                else:
                    parts.append(('expr', v))
            return parts
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [('lit', node.value)]
        return [('expr', node)]

    @classmethod
    def _normalize_print(cls, call: ast.Call, mult_names: set[str]):
        """Canonicalize ``print(...)`` into ('print', mult, template) or None."""
        
        if not (isinstance(call.func, ast.Name) and call.func.id == 'print' and len(call.args) == 1):
            return None
        mult_ref = None
        buf: list[str] = []
        for kind, val in cls._flatten_parts(call.args[0]):
            if kind == 'lit':
                buf.append(val)
                continue
            expr = val
            if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
                    and expr.func.id in ('str', 'repr', 'format') and expr.args):
                expr = expr.args[0]
            if isinstance(expr, ast.Name) and expr.id in mult_names:
                if mult_ref is not None and mult_ref != expr.id:
                    return None
                mult_ref = expr.id
                buf.append(cls._MULT_SENTINEL)
            else:
                buf.append('\x01' + ast.unparse(expr))
        if mult_ref is None:
            return None
        return ('print', mult_ref, ''.join(buf))

    @classmethod
    def _normalize_assert(cls, node: ast.Assert, mult_names: set[str]):
        """Normalize an assert into a key, or None if it references no mult."""
        
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            left, right = test.left, test.comparators[0]
            op = cls._CMP_OPS.get(type(test.ops[0]))
            if op is not None:
                left_mult = isinstance(left, ast.Name) and left.id in mult_names
                right_mult = isinstance(right, ast.Name) and right.id in mult_names
                if left_mult and not right_mult:
                    val = cls._literal(getattr(right, 'value', None))
                    if val is not None:
                        return ('assert_cmp', left.id, op, val)
                elif right_mult and not left_mult:
                    val = cls._literal(getattr(left, 'value', None))
                    if val is not None:
                        return ('assert_cmp', right.id, cls._CMP_FLIP[op], val)
        if (isinstance(test, ast.Call) and isinstance(test.func, ast.Name)
                and test.func.id == 'isinstance' and len(test.args) == 2):
            target = test.args[0]
            if isinstance(target, ast.Name) and target.id in mult_names:
                types_node = test.args[1]
                type_names = (
                    [t.id for t in types_node.elts if isinstance(t, ast.Name)]
                    if isinstance(types_node, ast.Tuple)
                    else [types_node.id] if isinstance(types_node, ast.Name) else []
                )
                return ('assert_isinstance', target.id, frozenset(type_names))
        # An assert that mentions a mult but in an unrecognized shape: keep it,
        # comparing on normalized source so wrong forms still differ.
        if any(isinstance(n, ast.Name) and n.id in mult_names for n in ast.walk(test)):
            return ('assert_other', ast.unparse(test))
        return None

    @classmethod
    def _normalize_temp(cls, node: ast.Assign, mult_names: set[str]):
        """Normalize temporary assignments derived from one generated value."""
        
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            return None
        target = node.targets[0].id
        if target in mult_names:
            return None
        referenced = {
            child.id
            for child in ast.walk(node.value)
            if isinstance(child, ast.Name) and child.id in mult_names
        }
        if len(referenced) != 1:
            return None
        value = node.value
        is_generated_derivation = (
            isinstance(value, ast.Name)
            or isinstance(value, ast.BinOp)
            or (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == 'replace'
            )
        )
        if is_generated_derivation:
            return ('temp', target, next(iter(referenced)), ast.dump(value, include_attributes=False))
        return None

    @classmethod
    def _update_rhs_key(cls, target: str, value_node: ast.expr) -> str:
        """Standardize an update RHS so ``x = x + 1`` matches ``x += 1``."""
        if isinstance(value_node, ast.BinOp) and isinstance(value_node.left, ast.Name) and value_node.left.id == target:
            return 'aug:' + type(value_node.op).__name__ + ':' + ast.unparse(value_node.right)
        return 'raw:' + ast.dump(value_node, include_attributes=False)

    @classmethod
    def _normalize_update(cls, node, mult_names: set[str]):
        """Standardize ``mult = mult +/- eps`` / ``mult += eps`` / ``key = 'x' + key`` updates."""
        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                return None
            target = node.target.id
            if target not in mult_names:
                return None
            rhs_key = 'aug:' + type(node.op).__name__ + ':' + ast.unparse(node.value)
            return ('update', target, rhs_key)
        if isinstance(node, ast.Assign):
            if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
                return None
            target = node.targets[0].id
            if target not in mult_names:
                return None
            if not any(isinstance(n, ast.Name) and n.id == target for n in ast.walk(node.value)):
                return None
            if isinstance(node.value, ast.Name) and node.value.id == target:
                return None
            return ('update', target, cls._update_rhs_key(target, node.value))
        return None

    @classmethod
    def _normalize_comment(cls, text: str, mult_names: set[str]):
        """Standardize an injected source comment."""
        stripped = text.strip()
        matched_names = [
            name for name in mult_names
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", stripped)
        ]
        if not matched_names:
            return None
        return ('comment', tuple(sorted(matched_names)), stripped)

    @staticmethod
    def _function_comments(source: str, func: ast.FunctionDef) -> list[tuple[int, int, str]]:
        """Return COMMENT tokens inside a function body as (line, column, text)."""
        end_lineno = getattr(func, 'end_lineno', None)
        if end_lineno is None:
            return []
        out = []
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            for token in tokens:
                if token.type != tokenize.COMMENT:
                    continue
                row, col = token.start
                if func.lineno < row <= end_lineno and col > func.col_offset:
                    out.append((row, col, token.string))
        except tokenize.TokenError:
            return []
        return out

    @classmethod
    def _collect(cls, func: ast.FunctionDef, mult_names: set[str], source: str = '') -> dict:
        """Gather normalized constraint keys (per category) plus their body order."""
        asserts: Counter = Counter()
        prints: Counter = Counter()
        temps: Counter = Counter()
        updates: Counter = Counter()
        comments: Counter = Counter()
        order_items: list[tuple[int, int, str]] = []
        for stmt in func.body:
            if isinstance(stmt, ast.Assert):
                key = cls._normalize_assert(stmt, mult_names)
                if key is not None:
                    asserts[key] += 1
                    order_items.append((stmt.lineno, stmt.col_offset, 'assert'))
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                key = cls._normalize_print(stmt.value, mult_names)
                if key is not None:
                    prints[key] += 1
                    order_items.append((stmt.lineno, stmt.col_offset, 'print'))
            elif isinstance(stmt, ast.Assign):
                update_key = cls._normalize_update(stmt, mult_names)
                if update_key is not None:
                    updates[update_key] += 1
                    order_items.append((stmt.lineno, stmt.col_offset, 'update'))
                else:
                    key = cls._normalize_temp(stmt, mult_names)
                    if key is not None:
                        temps[key] += 1
                        order_items.append((stmt.lineno, stmt.col_offset, 'temp'))
            elif isinstance(stmt, ast.AugAssign):
                update_key = cls._normalize_update(stmt, mult_names)
                if update_key is not None:
                    updates[update_key] += 1
                    order_items.append((stmt.lineno, stmt.col_offset, 'update'))
        if source:
            for row, col, text in cls._function_comments(source, func):
                key = cls._normalize_comment(text, mult_names)
                if key is not None:
                    comments[key] += 1
                    order_items.append((row, col, 'comment'))
        order = [category for _row, _col, category in sorted(order_items)]
        return {
            'asserts': asserts,
            'prints': prints,
            'temps': temps,
            'updates': updates,
            'comments': comments,
            'order': order,
        }

    @staticmethod
    def _is_ordered(order: list[str]) -> bool:
        ranks = [ConstraintStructureTestCase._CATEGORY_RANK[c] for c in order]
        return all(a <= b for a, b in zip(ranks, ranks[1:]))

    @staticmethod
    def _diff(expected: Counter, actual: Counter) -> tuple[list[str], list[str]]:
        missing = expected - actual
        extra = actual - expected
        return (
            sorted(str(k) for k in missing.elements()),
            sorted(str(k) for k in extra.elements()),
        )

    @classmethod
    def _constraint_count(cls, collected: dict) -> int:
        return sum(sum(collected[cat].values()) for cat in cls._CATEGORIES)

    @classmethod
    def _constraint_param_names(cls, key) -> tuple[str, ...]:
        return tuple(sorted(set(cls._MULT_TOKEN_RE.findall(str(key)))))

    @classmethod
    def _paramless_key(cls, key) -> str:
        return cls._MULT_TOKEN_RE.sub('<generated_value>', str(key))

    @classmethod
    def _expanded_items(cls, collected: dict) -> list[dict]:
        items = []
        for category in cls._CATEGORIES:
            for key, count in collected[category].items():
                for _ in range(count):
                    items.append({
                        'category': category,
                        'key': key,
                        'key_text': str(key),
                        'params': cls._constraint_param_names(key),
                        'paramless_key': cls._paramless_key(key),
                    })
        return items

    @classmethod
    def _classify_constraint_mismatches(cls, expected: dict, actual: dict) -> dict:
        """Get statistics on whether there were too many constraints, not enough constraints, or misinterpreted"""
        
        missing = []
        extra = []
        for category in cls._CATEGORIES:
            missing.extend(cls._expanded_items({**{cat: Counter() for cat in cls._CATEGORIES}, category: expected[category] - actual[category]}))
            extra.extend(cls._expanded_items({**{cat: Counter() for cat in cls._CATEGORIES}, category: actual[category] - expected[category]}))

        unmatched_extra = list(range(len(extra)))
        unmatched_missing = list(range(len(missing)))
        classified: list[dict] = []

        def pair_matches(missing_item: dict, extra_item: dict, predicate) -> bool:
            return missing_item['category'] == extra_item['category'] and predicate(missing_item, extra_item)

        pair_rules = [
            (
                'wrong_param',
                lambda miss, ext: (
                    miss['paramless_key'] == ext['paramless_key']
                    and miss['params'] != ext['params']
                ),
            ),
            (
                'wrong_value_or_action',
                lambda miss, ext: (
                    miss['params'] == ext['params']
                    and miss['paramless_key'] != ext['paramless_key']
                ),
            ),
        ]
        for error_type, predicate in pair_rules:
            for missing_index in list(unmatched_missing):
                match_index = next(
                    (
                        extra_index
                        for extra_index in unmatched_extra
                        if pair_matches(missing[missing_index], extra[extra_index], predicate)
                    ),
                    None,
                )
                if match_index is None:
                    continue
                classified.append({
                    'type': error_type,
                    'category': missing[missing_index]['category'],
                    'expected': missing[missing_index]['key_text'],
                    'actual': extra[match_index]['key_text'],
                })
                unmatched_missing.remove(missing_index)
                unmatched_extra.remove(match_index)

        for missing_index in unmatched_missing:
            classified.append({
                'type': 'missing_constraint',
                'category': missing[missing_index]['category'],
                'expected': missing[missing_index]['key_text'],
            })
        for extra_index in unmatched_extra:
            classified.append({
                'type': 'hallucinated_constraint',
                'category': extra[extra_index]['category'],
                'actual': extra[extra_index]['key_text'],
            })

        return {
            'missing_constraint_count': len(missing),
            'extra_constraint_count': len(extra),
            'classified_errors': classified,
        }

    def run(self, code: str, starter_code: str, solution: str) -> TestCaseResult:
        try:
            if not isinstance(code, str) or not isinstance(solution, str):
                return TestCaseResult(TestCaseType.PASS, metadata={'skipped': True})

            mult_names = self._mult_names(solution)
            if not mult_names:
                return TestCaseResult(TestCaseType.PASS, metadata={'skipped': True})

            sol_fns = self._functions(solution)
            cand_fns = self._functions(code)

            function_reports: dict[str, dict] = {}
            diagnostics: dict[str, dict] = {}
            order_warnings: dict[str, dict] = {}
            failed = False

            checked_functions: set[str] = set()
            empty_counters = {c: Counter() for c in self._CATEGORIES}

            for name, sol_fn in sol_fns.items():
                expected = self._collect(sol_fn, mult_names, solution)
                cand_fn = cand_fns.get(name)
                if cand_fn is None:
                    expected_count = self._constraint_count(expected)
                    
                    # first, check the expected counts
                    if expected_count:
                        failed = True
                        function_reports[name] = {'error': 'function missing in candidate'}
                        diagnostics[name] = {
                            'expected_count': expected_count,
                            'actual_count': 0,
                            'wrong_number_of_constraints': True,
                            'missing_constraint_count': expected_count,
                            'extra_constraint_count': 0,
                            'classified_errors': [
                                {
                                    'type': 'missing_constraint',
                                    'category': item['category'],
                                    'expected': item['key_text'],
                                }
                                for item in self._expanded_items(expected)
                            ],
                        }
                        checked_functions.add(name)
                    continue
                
                actual = self._collect(cand_fn, mult_names, code)
                expected_count = self._constraint_count(expected)
                actual_count = self._constraint_count(actual)
                if not expected_count and not actual_count:
                    continue
                checked_functions.add(name)

                report: dict = {}
                fn_failed = False
                for cat in self._CATEGORIES:
                    # then check for actual differences
                    missing, extra = self._diff(expected[cat], actual[cat])
                    if missing or extra:
                        fn_failed = True
                        report[cat] = {'missing': missing, 'extra': extra}
                        
                # attempt to classify what went wrong
                mismatch_diagnostics = self._classify_constraint_mismatches(expected, actual)
                diagnostics[name] = {
                    'expected_count': expected_count,
                    'actual_count': actual_count,
                    'wrong_number_of_constraints': expected_count != actual_count,
                    **mismatch_diagnostics,
                }
                
                # we also can check if the order of constraints is correct, but we do not penalize models if it is out of order (just a warning)
                if not self._is_ordered(actual['order']):
                    order_warnings[name] = {
                        'expected': 'comment -> assert -> print -> temp -> update',
                        'actual': actual['order'],
                    }
                if fn_failed:
                    failed = True
                    function_reports[name] = report

            # functions that were NOT edited should not have any constraints
            for name, cand_fn in cand_fns.items():
                if name in sol_fns:
                    continue
                actual = self._collect(cand_fn, mult_names, code)
                if not any(actual[c] for c in self._CATEGORIES):
                    continue
                checked_functions.add(name)
                report = {'error': 'function not in solution; constraints should not be injected'}
                for cat in self._CATEGORIES:
                    missing, extra = self._diff(empty_counters[cat], actual[cat])
                    if extra:
                        report[cat] = {'missing': missing, 'extra': extra}
                actual_count = self._constraint_count(actual)
                diagnostics[name] = {
                    'expected_count': 0,
                    'actual_count': actual_count,
                    'wrong_number_of_constraints': actual_count != 0,
                    'missing_constraint_count': 0,
                    'extra_constraint_count': actual_count,
                    'classified_errors': [
                        {
                            'type': 'hallucinated_constraint',
                            'category': item['category'],
                            'actual': item['key_text'],
                        }
                        for item in self._expanded_items(actual)
                    ],
                }
                failed = True
                function_reports[name] = report

            metadata = {
                'mult_names': sorted(mult_names),
                'checked_functions': sorted(checked_functions),
            }
            if diagnostics:
                metadata['diagnostics'] = diagnostics
            if function_reports:
                metadata['mismatches'] = function_reports
            if order_warnings:
                metadata['order_warnings'] = order_warnings
            return TestCaseResult(TestCaseType.FAIL if failed else TestCaseType.PASS, metadata=metadata)
        except Exception as e:
            return TestCaseResult(TestCaseType.ERROR, metadata={'error': str(e), 'traceback': traceback.format_exc()})


class BranchPlacementTestCase(TestCase):
    """
    Evaluates whether the candidate code has modified the same if-branch blocks as the solution, relative to the starter code.
    This is used in the runtime resolution task only
    """

    KIND = TestCaseKind.BRANCH_PLACEMENT

    def __init__(self, runtime_branches: bool = False):
        self.runtime_branches = runtime_branches

    def to_dict(self) -> dict:
        return {'kind': self.KIND.value, 'runtime_branches': self.runtime_branches}

    @classmethod
    def _from_dict(cls, d: dict) -> "BranchPlacementTestCase":
        return cls(runtime_branches=d.get('runtime_branches', False))

    @staticmethod
    def _top_level_functions(source: str) -> dict[str, ast.FunctionDef]:
        return {
            node.name: node
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
        }

    @classmethod
    def _branch_contents(cls, func_node: ast.FunctionDef) -> dict[str, str]:
        """Collect the direct source contents of each function and if-branch block"""
        out: dict[str, str] = {}

        def visit(stmts: list[ast.stmt], prefix: str) -> None:
            own: list[str] = []
            if_index = 0
            for stmt in stmts:
                if isinstance(stmt, ast.If):
                    path = f"{prefix}/if{if_index}"
                    own.append(f"<if:{ast.unparse(stmt.test)}>")
                    visit(stmt.body, f"{path}/body")
                    visit(stmt.orelse, f"{path}/else")
                    if_index += 1
                else:
                    own.append(ast.unparse(stmt))
            out[prefix] = "\n".join(own)

        visit(func_node.body, "")
        return out

    @classmethod
    def _changed_branches(cls, before: ast.FunctionDef, after: ast.FunctionDef) -> set[str]:
        b = cls._branch_contents(before)
        a = cls._branch_contents(after)
        return {path for path in set(b) | set(a) if b.get(path) != a.get(path)}

    def run(self, code: CodePayload, starter_code: CodePayload, solution: CodePayload) -> TestCaseResult:
        if not self.runtime_branches:
            return TestCaseResult(TestCaseType.PASS, metadata={'skipped': 'not a runtime if-statement task'})
        try:
            if isinstance(code, dict) or isinstance(starter_code, dict) or isinstance(solution, dict):
                return TestCaseResult(TestCaseType.PASS, metadata={'skipped': 'multi-file task'})

            try:
                starter_fns = self._top_level_functions(starter_code)
                solution_fns = self._top_level_functions(solution)
                candidate_fns = self._top_level_functions(code)
            except SyntaxError as e:
                return TestCaseResult(TestCaseType.ERROR, metadata={'error': f'parse failure: {e}'})

            # Only functions present in all three can be compared branch-by-branch
            shared = set(starter_fns) & set(solution_fns) & set(candidate_fns)

            wrong_branch_edits: dict[str, list[str]] = {}
            missing_branch_edits: dict[str, list[str]] = {}
            for name in sorted(shared):
                # check which branches were changed, and see if they are equivalent
                changed_sol = self._changed_branches(starter_fns[name], solution_fns[name])
                changed_cand = self._changed_branches(starter_fns[name], candidate_fns[name])
                extra = changed_cand - changed_sol
                missing = changed_sol - changed_cand
                if extra:
                    wrong_branch_edits[name] = sorted(extra)
                if missing:
                    missing_branch_edits[name] = sorted(missing)

            metadata: dict[str, Any] = {'checked_functions': sorted(shared)}
            if wrong_branch_edits or missing_branch_edits:
                if wrong_branch_edits:
                    metadata['wrong_branch_edits'] = wrong_branch_edits
                if missing_branch_edits:
                    metadata['missing_branch_edits'] = missing_branch_edits
                return TestCaseResult(TestCaseType.FAIL, metadata=metadata)
            return TestCaseResult(TestCaseType.PASS, metadata=metadata)
        except Exception as e:
            return TestCaseResult(TestCaseType.ERROR, metadata={'error': str(e), 'traceback': traceback.format_exc()})


TEST_CASE_REGISTRY: dict[TestCaseKind, type[TestCase]] = {
    TestCaseKind.COMPILATION: CompilationTestCase,
    TestCaseKind.FUNCTION_EXISTENCE: FunctionExistenceTestCase,
    TestCaseKind.BEHAVIORAL: BehavioralTestCase,
    TestCaseKind.EDIT_PATH: EditPathTestCase,
    TestCaseKind.CONSTRAINT_STRUCTURE: ConstraintStructureTestCase,
    TestCaseKind.BRANCH_PLACEMENT: BranchPlacementTestCase,
    TestCaseKind.FUNCTION_COMMENTS: FunctionCommentsTestCase,
}