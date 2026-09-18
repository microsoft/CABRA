from enum import Enum
import ast
import random

import networkx as nx
from networkx.readwrite import json_graph

from data.tasks.test_cases import TestCaseSuite
from data.tasks import Task
from data.tasks.function.ast import (
    build_starter_code,
    remove_functions,
    add_return_value,
    seed_return_value,
    add_default_parameter_to_functions,
    wrap_functions_with_mult_only_terminal,
    wrap_function_return_with_slow,
    retrieve_multiplier_for_function,
    move_multiplier_down_to_shared_node,
    move_slow_to_ancestor,
)
from data.utils.program_params import ProgramParams


class FunctionTaskType(Enum):
    MATH = 'math'
    STRING = 'string'
    ARRAY = 'array'


DOMAIN_CONFIG = {
    FunctionTaskType.MATH: {
        'return_type': 'float',
        'helper_type': 'float',
        'parameter': 'mult',
        'function_name': 'get_multiplier',
    },
    FunctionTaskType.STRING: {
        'return_type': 'str',
        'helper_type': 'str',
        'parameter': 'prefix',
        'function_name': 'get_key',
    },
    FunctionTaskType.ARRAY: {
        'return_type': 'np.ndarray',
        'helper_type': 'float',
        'parameter': 'mult',
        'function_name': 'get_multiplier',
    },
}

RUNTIME_IF_TYPES = ("runtime",)


def _runtime_active_state_by_function(
    seed: int,
    program_params: ProgramParams,
    all_function_names: list[str],
    if_start_nodes: set[str],
) -> dict[str, int] | None:
    if program_params.if_type not in RUNTIME_IF_TYPES:
        return None

    num_vars = 2
    active_state_by_function = {
        name: random.Random(f"{seed}:state:{name}").randrange(num_vars)
        for name in all_function_names
    }
    for name in if_start_nodes:
        active_state_by_function[name] = random.Random(
            f"{seed}:start_state:{name}"
        ).randrange(num_vars)
    return active_state_by_function


def _prompt_for_program_params(cls: type, program_params: ProgramParams) -> str:
    if program_params.if_type == "none":
        prompt_key = "none"
    else:
        prompt_key = "runtime_simple"
    return cls.PROMPTS[prompt_key]

class _BaseFunctionTask(Task):
    """Shared behaviour for the generated function-refactoring task types."""

    def _has_runtime_branches(self) -> bool:
        """True when the task carries runtime if-statement branches.

        Only the runtime if-types emit ``if``/``else`` blocks inside the
        generated functions; the ``none`` if-type produces straight-line bodies.
        This gates the branch-placement check to the runtime tasks.
        """
        source = self.starter_code
        if not isinstance(source, str):
            return False
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        return any(isinstance(node, ast.If) for node in ast.walk(tree))

    def generate_test_cases(self) -> TestCaseSuite:
        return TestCaseSuite.create(
            prefix_blocks=self.__class__.PREFIX_BLOCKS,
            runtime_branches=self._has_runtime_branches(),
        )


class BaseFunctionTaskDeadCode(_BaseFunctionTask):

    FUNCTION_TASK_TYPE: FunctionTaskType
    PREFIX_BLOCKS: list[str]
    PROMPTS: dict[str, str]

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int, program_params: ProgramParams = None) -> "BaseFunctionTaskDeadCode":
        task_type = cls.FUNCTION_TASK_TYPE.value

        if program_params is None:
            program_params = ProgramParams()
        num_target = dag_data["num_target"]

        # Compute if_start_nodes and if_subgraph_nodes for dead_code
        if_start_nodes = set()
        if_subgraph_nodes = set()
        dead_code_entrypoints = set()
        if program_params.if_type in RUNTIME_IF_TYPES:
            for t in range(num_target):
                D = json_graph.node_link_graph(dag_data["dead_code_dags"][t])
                # Start nodes = roots of dead code (in_degree==0)
                roots = {n for n in D.nodes() if D.in_degree(n) == 0}
                dead_code_entrypoints.update(roots)
                if_start_nodes.update(roots)
                if_subgraph_nodes.update(D.nodes())
        else:
            for t in range(num_target):
                D = json_graph.node_link_graph(dag_data["dead_code_dags"][t])
                dead_code_entrypoints.update(n for n in D.nodes() if D.in_degree(n) == 0)

        # Build once with dead code included so all function bodies are consistent
        starter_code = build_starter_code(
            dag_data["main_code_with_dead_code_dags"] + dag_data["main_code_dags"][num_target:], seed, program_params=program_params, task_type=task_type,
            if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="forward",
            excluded_entry_points=dead_code_entrypoints,
            cross_graph_distractors=(program_params.if_type in RUNTIME_IF_TYPES),
            identical_runtime_simple_branches=False,
        )

        # Collect dead code function names to remove for the solution
        dead_code_function_names = set()
        for t in range(num_target):
            D = json_graph.node_link_graph(dag_data["dead_code_dags"][t])
            dead_code_function_names.update(D.nodes())

        solution_code = remove_functions(starter_code, dead_code_function_names)

        return cls(
            dag_id=dag_id,
            name="",
            prompt=_prompt_for_program_params(cls, program_params),
            starter_code=starter_code,
            solution_code=solution_code,
            metadata={},
        )


class BaseFunctionTaskAddParameter(_BaseFunctionTask):

    FUNCTION_TASK_TYPE: FunctionTaskType
    PREFIX_BLOCKS: list[str]
    PROMPTS: dict[str, str]

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int, program_params: ProgramParams = None) -> "BaseFunctionTaskAddParameter":
        task_type = cls.FUNCTION_TASK_TYPE.value
        cfg = DOMAIN_CONFIG[cls.FUNCTION_TASK_TYPE]
        return_type = cfg['return_type']
        helper_type = cfg['helper_type']
        parameter = cfg['parameter']

        if program_params is None:
            program_params = ProgramParams()
        num_target = dag_data["num_target"]

        # Compute if_start_nodes and if_subgraph_nodes for add_parameter
        if_start_nodes = set()
        if_subgraph_nodes = set()
        if program_params.if_type in RUNTIME_IF_TYPES:
            for t in range(num_target):
                root_id = dag_data["add_parameter_root_ids"][t]
                if_start_nodes.add(root_id)
                D = json_graph.node_link_graph(dag_data["add_parameter_dags"][t])
                if_subgraph_nodes.update(D.nodes())

        solution_main_dags = (
            list(dag_data["main_code_with_add_parameter_dags"])
            + list(dag_data["main_code_dags"][num_target:])
        )
        all_function_names = sorted({
            node["id"]
            for dag in solution_main_dags
            for node in dag["nodes"]
        })
        active_state_by_function = _runtime_active_state_by_function(
            seed,
            program_params,
            all_function_names,
            if_start_nodes,
        )

        starter = build_starter_code(solution_main_dags, seed, program_params=program_params, task_type=task_type,
                                     if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="forward")
        solution = build_starter_code(solution_main_dags, seed, program_params=program_params, task_type=task_type,
                                      if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="forward")

        functions_to_edit = []
        terminal_wrap_functions = set()
        for t in range(num_target):
            target_node = dag_data["add_parameter_root_ids"][t]
            G_spliced = json_graph.node_link_graph(dag_data["add_parameter_dags"][t])
            functions_to_edit.extend(list(G_spliced.nodes()) + [target_node])
            terminal_wrap_functions.update(
                node for node in G_spliced.nodes()
                if G_spliced.out_degree(node) == 0
            )

        starter = add_default_parameter_to_functions(
            starter,
            {dag_data["add_parameter_root_ids"][t] for t in range(num_target)},
            parameter=parameter,
            helper_type=helper_type,
        )
        solution = add_default_parameter_to_functions(
            solution,
            set(functions_to_edit),
            parameter=parameter,
            helper_type=helper_type,
        )

        solution = wrap_functions_with_mult_only_terminal(
            solution,
            set(functions_to_edit),
            return_type=return_type,
            parameter=parameter,
            helper_type=helper_type,
            active_state_by_function=active_state_by_function,
            terminal_wrap_function_names=terminal_wrap_functions,
        )

        starter = "from mylibrary import default\n" + starter
        solution = "from mylibrary import default\n" + solution

        return cls(
            dag_id=dag_id,
            name="",
            prompt=_prompt_for_program_params(cls, program_params),
            starter_code=starter,
            solution_code=solution,
            metadata={},
        )


class BaseFunctionTaskAddReturnValue(_BaseFunctionTask):

    FUNCTION_TASK_TYPE: FunctionTaskType
    PREFIX_BLOCKS: list[str]
    PROMPTS: dict[str, str]

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int, program_params: ProgramParams = None) -> "BaseFunctionTaskAddReturnValue":
        task_type = cls.FUNCTION_TASK_TYPE.value
        cfg = DOMAIN_CONFIG[cls.FUNCTION_TASK_TYPE]
        return_type = cfg['return_type']

        if program_params is None:
            program_params = ProgramParams()
        num_target = dag_data["num_target"]

        # Compute if_start_nodes and if_subgraph_nodes for add_return_value
        if_start_nodes = set()
        if_subgraph_nodes = set()

        solution_main_dags_up = (
            list(dag_data["main_code_with_add_return_value_dags"])
            + list(dag_data["main_code_dags"][num_target:])
        )
        all_function_names = sorted({
            node["id"]
            for dag in solution_main_dags_up
            for node in dag["nodes"]
        })
        active_state_by_function = _runtime_active_state_by_function(
            seed,
            program_params,
            all_function_names,
            if_start_nodes,
        )
        starter = "from mylibrary import external\n" + build_starter_code(
            solution_main_dags_up, seed, program_params=program_params, task_type=task_type,
            if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="backward",
            backward_return_state_mode="branch",
        )
        solution = "from mylibrary import external\n" + build_starter_code(
            solution_main_dags_up, seed, program_params=program_params, task_type=task_type,
            if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="backward",
            backward_return_state_mode="branch",
        )

        functions_to_add_key = []
        all_functions = []
        all_targets = []
        for t in range(num_target):
            target_node = dag_data["add_return_value_sink_ids"][t]
            G_up = json_graph.node_link_graph(dag_data["add_return_value_dags"][t])
            ancestors = [n for n in G_up.nodes() if n != target_node]
            functions_to_add_key.extend(ancestors + [target_node])
            all_functions.extend(list(G_up.nodes()))
            all_targets.append(target_node)
        all_targets = set(all_targets)

        starter = seed_return_value(
            starter,
            source_functions=all_targets,
            active_state_by_function=active_state_by_function,
        )
        solution = add_return_value(
            solution,
            source_functions=all_targets,
            functions_to_modify=set(functions_to_add_key),
            return_type=return_type,
            active_state_by_function=active_state_by_function,
        )

        return cls(
            dag_id=dag_id,
            name="",
            prompt=_prompt_for_program_params(cls, program_params),
            starter_code=starter,
            solution_code=solution,
            metadata={},
        )


class BaseFunctionTaskCacheFunction(_BaseFunctionTask):

    FUNCTION_TASK_TYPE: FunctionTaskType
    PREFIX_BLOCKS: list[str]
    PROMPTS: dict[str, str]

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int, program_params: ProgramParams = None) -> "BaseFunctionTaskCacheFunction":
        task_type = cls.FUNCTION_TASK_TYPE.value

        if program_params is None:
            program_params = ProgramParams()
        num_target = dag_data["num_target"]

        # Compute if_start_nodes and if_subgraph_nodes for cache_function
        if_start_nodes = set()
        if_subgraph_nodes = set()

        cache_function_main_dags = (
            list(dag_data["main_code_with_cache_function_dags"])
            + list(dag_data["main_code_dags"][num_target:])
        )
        all_function_names = sorted({
            node["id"]
            for dag in cache_function_main_dags
            for node in dag["nodes"]
        })
        active_state_by_function = _runtime_active_state_by_function(
            seed,
            program_params,
            all_function_names,
            if_start_nodes,
        )
        starter = build_starter_code(cache_function_main_dags, seed, program_params=program_params, task_type=task_type,
                                     if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="backward",
                                     backward_return_state_mode="branch")
        solution = build_starter_code(cache_function_main_dags, seed, program_params=program_params, task_type=task_type,
                                      if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="backward",
                                      backward_return_state_mode="branch")

        cache_edit_functions = set()
        for t in range(num_target):
            D = json_graph.node_link_graph(dag_data["cache_function_dags"][t])
            ancestor_node = dag_data["cache_function_root_ids"][t]
            target_nodes = [n for n in D.nodes() if D.out_degree(n) == 0]
            affected_nodes = [n for n in D.nodes() if n != ancestor_node and D.out_degree(n) > 0]
            cache_edit_functions.update(D.nodes())

            for target_node in target_nodes:
                starter = wrap_function_return_with_slow(
                    starter,
                    target_node,
                    active_state_by_function=active_state_by_function,
                    active_only=(program_params.if_type not in RUNTIME_IF_TYPES),
                )
                solution = wrap_function_return_with_slow(
                    solution,
                    target_node,
                    active_state_by_function=active_state_by_function,
                    active_only=(program_params.if_type not in RUNTIME_IF_TYPES),
                )
            solution = move_slow_to_ancestor(
                source_code=solution,
                ancestor_node=ancestor_node,
                target_nodes=target_nodes,
                affected_nodes=affected_nodes,
                param_type=task_type,
                active_state_by_function=active_state_by_function,
                branch_local=(program_params.if_type in RUNTIME_IF_TYPES),
            )
        starter = "from mylibrary import slow\n" + starter
        solution = "from mylibrary import slow\n" + solution

        return cls(
            dag_id=dag_id,
            name="",
            prompt=_prompt_for_program_params(cls, program_params),
            starter_code=starter,
            solution_code=solution,
            metadata={},
        )


class BaseFunctionTaskExtractHelper(_BaseFunctionTask):

    FUNCTION_TASK_TYPE: FunctionTaskType
    PREFIX_BLOCKS: list[str]
    PROMPTS: dict[str, str]

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int, program_params: ProgramParams = None) -> "BaseFunctionTaskExtractHelper":
        task_type = cls.FUNCTION_TASK_TYPE.value
        cfg = DOMAIN_CONFIG[cls.FUNCTION_TASK_TYPE]
        return_type = cfg['return_type']
        helper_type = cfg['helper_type']
        function_name = cfg['function_name']
        var_name = cfg['parameter']

        if program_params is None:
            program_params = ProgramParams()
        num_target = dag_data["num_target"]

        # Compute if_start_nodes and if_subgraph_nodes for extract_helper
        if_start_nodes = set()
        if_subgraph_nodes = set()
        if program_params.if_type in RUNTIME_IF_TYPES:
            for t in range(num_target):
                D = json_graph.node_link_graph(dag_data["extract_helper_dags"][t])
                # Start nodes = root nodes (in_degree==0, where get_multiplier() is)
                roots = {n for n in D.nodes() if D.in_degree(n) == 0}
                if_start_nodes.update(roots)
                if_subgraph_nodes.update(D.nodes())

        extract_helper_main_dags = (
            list(dag_data["main_code_with_extract_helper_dags"])
            + list(dag_data["main_code_dags"][num_target:])
        )
        all_function_names = sorted({
            node["id"]
            for dag in extract_helper_main_dags
            for node in dag["nodes"]
        })
        active_state_by_function = _runtime_active_state_by_function(
            seed,
            program_params,
            all_function_names,
            if_start_nodes,
        )

        starter = build_starter_code(extract_helper_main_dags, seed, program_params=program_params, task_type=task_type,
                                     if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="forward")
        solution = build_starter_code(extract_helper_main_dags, seed, program_params=program_params, task_type=task_type,
                                      if_start_nodes=if_start_nodes, if_subgraph_nodes=if_subgraph_nodes, if_mode="forward")

        extract_edit_functions = set()
        for t in range(num_target):
            D = json_graph.node_link_graph(dag_data["extract_helper_dags"][t])
            ancestor_nodes = [n for n in D.nodes() if D.in_degree(n) == 0]
            shared_node = dag_data["extract_helper_sink_ids"][t]
            affected_nodes = list(set(
                n
                for anc in ancestor_nodes
                for n in nx.descendants(D, anc)
                if n != shared_node and nx.has_path(D, n, shared_node)
            ))
            extract_edit_functions.update(D.nodes())
            for ancestor_node in ancestor_nodes:
                starter = retrieve_multiplier_for_function(
                    starter,
                    ancestor_node,
                    function_name,
                    helper_type,
                    var_name,
                    active_state_by_function=active_state_by_function,
                    active_only=(program_params.if_type not in RUNTIME_IF_TYPES),
                    branch_local=(program_params.if_type in RUNTIME_IF_TYPES),
                )
                if program_params.if_type in RUNTIME_IF_TYPES:
                    solution = retrieve_multiplier_for_function(
                        solution,
                        ancestor_node,
                        function_name,
                        helper_type,
                        var_name,
                        active_state_by_function=active_state_by_function,
                        active_only=False,
                        branch_local=True,
                    )
            try:
                solution = move_multiplier_down_to_shared_node(
                    source_code=solution,
                    ancestor_nodes=ancestor_nodes,
                    shared_node=shared_node,
                    affected_nodes=set(affected_nodes),
                    top_nodes=set(ancestor_nodes),
                    value_temp_name="temp",
                    mult_name=var_name,
                    get_multiplier_func=function_name,
                    return_type=return_type,
                    helper_type=helper_type,
                    active_state_by_function=active_state_by_function,
                    branch_local=(program_params.if_type in RUNTIME_IF_TYPES),
                )
            except ValueError as e:
                raise ValueError(
                    f"[dag_id={dag_id!r}, extract_helper target {t}] {e}"
                ) from e

        starter = f"from mylibrary import {function_name}\n" + starter
        solution = f"from mylibrary import {function_name}\n" + solution

        return cls(
            dag_id=dag_id,
            name="",
            prompt=_prompt_for_program_params(cls, program_params),
            starter_code=starter,
            solution_code=solution,
            metadata={},
        )
