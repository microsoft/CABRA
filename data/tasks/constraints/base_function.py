"""
Base task for instruction-following: sampling rules/templates for different constraints that the model must follow
"""

import hashlib
import random

import networkx as nx
from networkx.readwrite import json_graph

from data.tasks.task import Task, TaskType
from data.tasks.function.ast import (
    build_starter_code,
    retrieve_multiplier_for_function,
    wrap_function_return_with_slow,
)
from data.tasks.constraints.ast import (
    ARITHMETIC_TEMPLATES,
    COMBINE_MULTIPLY,
    STRING_ADJUST_TEMPLATES,
    _render,
    add_return_values,
    apply_extract_constraints,
    apply_parameter_constraints,
    apply_return_value_constraints,
    index_helper_calls,
    index_slow_calls,
    move_multipliers_down_to_shared_node,
    move_slow_values_to_ancestor,
    seed_return_value_keys,
    seed_root_values,
    simplify_generated_slow_additions,
    simplify_generated_value_combinations,
)
from data.tasks.constraints import bank
from data.tasks.problem_statements.constraint_prompts import (
    PROMPT_CACHE_FUNCTION_CONSTRAINTS,
    PROMPT_EXTRACT_HELPER_CONSTRAINTS,
    PROMPT_MULT_CONSTRAINTS,
    PROMPT_RETURN_VALUE_CONSTRAINTS,
)
from data.tasks.test_cases import TestCaseSuite


def _template_value_kind(template_bank_key: str) -> str:
    return "str" if template_bank_key.endswith("_str") or template_bank_key == "return_value_str" else "float"


def _rand_candidates(template_key: str, value_kind: str) -> list:
    if template_key in ARITHMETIC_TEMPLATES:
        return [value for value in bank.rand_values if value != 0.0]
    if template_key == "assert_not":
        return list(bank.not_values_str if value_kind == "str" else bank.not_values)
    if template_key == "assert_lower_bound":
        return list(bank.lower_bound_values_str if value_kind == "str" else bank.lower_bound_values)
    if template_key == "assert_upper_bound":
        return list(bank.upper_bound_values_str if value_kind == "str" else bank.upper_bound_values)
    if template_key == "add_comment":
        return list(bank.comment_values)
    if template_key in STRING_ADJUST_TEMPLATES:
        return list(bank.rand_values_str)
    return []


def _sample_substitution(
    template_key: str,
    var_name: str,
    value_kind: str,
    rng: random.Random,
    used_rand_values: set | None = None,
) -> dict | None:
    sub = {
        "mult": var_name,
        "var": var_name,
        "rand": "",
        "rand2": "",
        "prefix": "",
        "suffix": "",
        "new_var": rng.choice(bank.temp_name_templates).format(var=var_name),
    }
    candidates = _rand_candidates(template_key, value_kind)
    if candidates:
        if used_rand_values is not None:
            candidates = [value for value in candidates if value not in used_rand_values]
        if not candidates:
            return None
        sub["rand"] = rng.choice(candidates)
        if template_key in {"replace_character", "sandwich"}:
            rand2_candidates = [value for value in bank.rand_values_str if value != sub["rand"]]
            sub["rand2"] = rng.choice(rand2_candidates)
    elif template_key == "print_prefix":
        sub["prefix"] = rng.choice(bank.print_prefixes)
    elif template_key == "print_suffix":
        sub["suffix"] = rng.choice(bank.print_suffixes)
    return sub


def _remap_name(name: str, name_mapping: dict[str, str]) -> str:
    return name_mapping.get(name, name)


def _remap_names(names, name_mapping: dict[str, str]):
    return {_remap_name(name, name_mapping) for name in names}


GENERIC_FUNCTION_CHECK_KEY = "all_functions"
GENERIC_FUNCTION_CHECK = [
    {
        "implementation": "lambda name: True",
        "descriptions": ["In every function,"],
    }
]
DISTRACTOR_CHECK_KEY = "distractor"


def _function_check_entry(check_key: str) -> list[dict]:
    if check_key == GENERIC_FUNCTION_CHECK_KEY:
        return GENERIC_FUNCTION_CHECK
    return bank.function_check[check_key]


def _append_distractor_rules(
    specs: list[dict],
    num_distractors: int,
    template_bank: dict,
    value_kind: str,
    rng: random.Random,
) -> None:
    if num_distractors < 0:
        raise ValueError(f"num_distractors must be >= 0, got {num_distractors}")
    if num_distractors == 0:
        return

    template_keys = list(template_bank.keys())
    for _ in range(num_distractors):
        spec = rng.choice(specs)
        template_key = rng.choice(template_keys)
        template_entry = template_bank[template_key][0]
        sub = _sample_substitution(template_key, spec["var"], value_kind, rng)
        if sub is None:
            continue

        spec["rules"].append({
            "var": spec["var"],
            "mult": spec["var"],
            "check_key": DISTRACTOR_CHECK_KEY,
            "template_key": template_key,
            "predicate": lambda name: False,
            "check_desc": bank.sample_distractor(rng),
            "template_desc": _render(rng.choice(template_entry["descriptions"]), sub),
            "implementation": template_entry["implementation"],
            "sub": sub,
        })


def sample_rules(
    num_constraints: int,
    seed: int,
    dag_id: str | None = None,
    template_bank_key: str = "add_parameter_float",
    var_prefix: str = "mult",
    num_params: int = 1,
    num_distractors: int = 0,
) -> list[dict]:
    if num_constraints <= 0:
        raise ValueError(
            "math_mult_constraints requires num_constraints > 0; "
            "use math_function for the zero-requirement baseline"
        )
    if num_params <= 0:
        raise ValueError(f"num_params must be > 0, got {num_params}")

    template_bank = bank.template_banks[template_bank_key]
    value_kind = _template_value_kind(template_bank_key)
    seed_material = f"{seed}:rules:all-functions"
    if dag_id is not None:
        seed_material = f"{seed_material}:{hashlib.sha256(dag_id.encode('utf-8')).hexdigest()}"
    rng = random.Random(seed_material)

    template_keys = list(template_bank.keys())
    specs = []
    for index in range(1, num_params + 1):
        var_name = f"{var_prefix}{index}"
        specs.append({
            "var": var_name,
            "mult": var_name,
            "rules": [],
            "seen_rule_suffixes": set(),
            "seen_implementations": set(),
            "seen_arithmetic_adjustment": False,
            "seen_string_adjustment": False,
            "used_rand_values": set(),
        })

    check_key = GENERIC_FUNCTION_CHECK_KEY
    check_entry = _function_check_entry(check_key)[0]
    predicate = eval(check_entry["implementation"])  # noqa: S307 - trusted local data

    attempts = 0
    while sum(len(spec["rules"]) for spec in specs) < num_constraints and attempts < num_constraints * num_params * 60:
        attempts += 1
        spec = rng.choice(specs)
        var_name = spec["var"]
        template_key = rng.choice(template_keys)
        if template_key in ARITHMETIC_TEMPLATES and spec["seen_arithmetic_adjustment"]:
            continue
        if template_key in STRING_ADJUST_TEMPLATES and spec["seen_string_adjustment"]:
            continue

        template_entry = template_bank[template_key][0]
        sub = _sample_substitution(template_key, var_name, value_kind, rng, spec["used_rand_values"])
        if sub is None:
            continue

        template_desc = _render(rng.choice(template_entry["descriptions"]), sub)
        implementation = _render(template_entry["implementation"], sub)
        if template_desc in spec["seen_rule_suffixes"] or implementation in spec["seen_implementations"]:
            continue

        spec["seen_rule_suffixes"].add(template_desc)
        spec["seen_implementations"].add(implementation)
        if template_key in ARITHMETIC_TEMPLATES:
            spec["seen_arithmetic_adjustment"] = True
        if template_key in STRING_ADJUST_TEMPLATES:
            spec["seen_string_adjustment"] = True
        if sub["rand"] != "":
            spec["used_rand_values"].add(sub["rand"])

        check_desc = rng.choice(check_entry["descriptions"])
        rule = {
            "var": var_name,
            "mult": var_name,
            "check_key": check_key,
            "template_key": template_key,
            "predicate": predicate,
            "check_desc": check_desc,
            "template_desc": template_desc,
            "implementation": template_entry["implementation"],
            "sub": sub,
        }
        spec["rules"].append(rule)

    for spec in specs:
        for key in (
            "seen_rule_suffixes",
            "seen_implementations",
            "seen_arithmetic_adjustment",
            "seen_string_adjustment",
            "used_rand_values",
        ):
            del spec[key]
    _append_distractor_rules(specs, num_distractors, template_bank, value_kind, rng)
    return specs


def build_prompt(base_prompt: str, specs: list[dict], value_label: str) -> str:
    has_distractors = any(
        rule["check_key"] == DISTRACTOR_CHECK_KEY
        for spec in specs
        for rule in spec["rules"]
    )
    if not has_distractors:
        base_prompt = base_prompt.replace(
            "triggered by the NAME of the function they are applied in",
            "applied in every eligible function",
        )
        base_prompt = base_prompt.replace(
            "For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function",
            "For each such function, apply every requirement",
        )
        base_prompt = base_prompt.replace(
            ", or inside functions whose names do not match that requirement's condition",
            "",
        )
    value_names = [spec["var"] for spec in specs]
    requirements = [(spec["var"], rule) for spec in specs for rule in spec["rules"]]
    shuffle_material = repr([
        (
            value_name,
            rule["check_key"],
            rule["template_key"],
            rule["check_desc"],
            rule["template_desc"],
            sorted(rule["sub"].items()),
        )
        for value_name, rule in requirements
    ])
    rng = random.Random(f"{hashlib.sha256(shuffle_material.encode('utf-8')).hexdigest()}:prompt_requirements")
    rng.shuffle(requirements)

    if len(value_names) == 1:
        value_list = value_names[0]
    else:
        value_list = ", ".join(value_names[:-1]) + f", and {value_names[-1]}"

    entity_note = "These requirements apply to every eligible function."

    lines = [
        base_prompt,
        "",
        f"Here are the {len(requirements)} requirements for the {value_label} ({value_list}). {entity_note}",
        "",
    ]
    for index, (value_name, rule) in enumerate(requirements, start=1):
        lines.append(f"{index}. For {value_name}: {rule['check_desc']} {rule['template_desc']}")
    return "\n".join(lines).rstrip()


def _rules_metadata(specs: list[dict]) -> list[dict]:
    return [
        {
            "var": spec["var"],
            "mult": spec["var"],
            "rules": [
                {
                    "check_key": rule["check_key"],
                    "template_key": rule["template_key"],
                    "check_desc": rule["check_desc"],
                    "template_desc": rule["template_desc"],
                    "values": {key: value for key, value in rule["sub"].items() if key not in {"mult", "var"}},
                }
                for rule in spec["rules"]
            ],
        }
        for spec in specs
    ]


class BaseConstraintsTask(Task):
    PREFIX_BLOCKS: list[str] = []
    NUM_CONSTRAINTS: int = 6
    TASK_TYPE_NAME: str = "math"
    TASK_TYPE: TaskType
    TEMPLATE_BANK_KEY: str
    VAR_PREFIX: str
    VALUE_LABEL: str
    PROMPT_TEMPLATE: str

    @classmethod
    def _constraint_params(cls, seed: int | None, program_params) -> tuple[int, int, int]:
        actual_seed = 0 if seed is None else seed
        num_constraints = getattr(program_params, "num_constraints", cls.NUM_CONSTRAINTS)
        num_params = getattr(program_params, "num_params", 1)
        if num_constraints <= 0:
            raise ValueError(f"num_constraints must be > 0, got {num_constraints}")
        if num_params <= 0:
            raise ValueError(f"num_params must be > 0, got {num_params}")
        return actual_seed, num_constraints, num_params

    @classmethod
    def _sample_specs(cls, dag_id: str, seed: int, num_constraints: int, num_params: int) -> list[dict]:
        return sample_rules(
            num_constraints,
            seed,
            dag_id=dag_id,
            template_bank_key=cls.TEMPLATE_BANK_KEY,
            var_prefix=cls.VAR_PREFIX,
            num_params=num_params,
        )

    @classmethod
    def _make_task(cls, dag_id: str, prompt: str, starter_code: str, solution_code: str, specs: list[dict], num_constraints: int | None = None):
        num_constraint_rules = sum(
            1
            for spec in specs
            for rule in spec["rules"]
            if rule["check_key"] != DISTRACTOR_CHECK_KEY
        )
        metadata = {
            "num_values": len(specs),
            "num_constraint_rules": num_constraint_rules,
            "constraint_rules": _rules_metadata(specs),
        }
        if num_constraints is not None:
            metadata["num_constraints"] = num_constraints
        return cls(
            dag_id=dag_id,
            name="",
            prompt=prompt,
            starter_code=starter_code,
            solution_code=solution_code,
            metadata=metadata,
        )

    def generate_test_cases(self) -> TestCaseSuite:
        suite = TestCaseSuite.create(prefix_blocks=self.__class__.PREFIX_BLOCKS)
        if self.metadata.get("edit_only"):
            from data.tasks.test_cases import ConstraintStructureTestCase, FunctionCommentsTestCase

            suite.test_cases = [
                test_case
                for test_case in suite.test_cases
                if not isinstance(test_case, ConstraintStructureTestCase)
            ]

            suite.test_cases.append(
                FunctionCommentsTestCase(self.metadata["edit_only_comment"])
            )
        return suite


class BaseMultConstraintsTask(BaseConstraintsTask):
    TASK_TYPE = TaskType.ADD_PARAMETER
    TEMPLATE_BANK_KEY = "add_parameter_float"
    VAR_PREFIX = "mult"
    VALUE_LABEL = "mult parameters"
    PROMPT_TEMPLATE = PROMPT_MULT_CONSTRAINTS
    PARAMETER_ANNOTATION = "float"
    TERMINAL_COMBINE_OP = COMBINE_MULTIPLY
    VALUE_KIND = "float"

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int = None, program_params=None) -> "BaseMultConstraintsTask":
        seed, num_constraints, num_params = cls._constraint_params(seed, program_params)
        num_target = dag_data["num_target"]
        main_dags = list(dag_data["main_code_with_add_parameter_dags"]) + list(dag_data["main_code_dags"][num_target:])
        base_code = build_starter_code(main_dags, seed, task_type=cls.TASK_TYPE_NAME)
        name_mapping: dict[str, str] = {}
        specs = cls._sample_specs(dag_id, seed, num_constraints, num_params)

        root_names = _remap_names((dag_data["add_parameter_root_ids"][target] for target in range(num_target)), name_mapping)
        function_names = set(root_names)
        for target in range(num_target):
            function_names.update(_remap_names((node["id"] for node in dag_data["add_parameter_dags"][target]["nodes"]), name_mapping))

        starter_code = "from mylibrary import default\n" + seed_root_values(base_code, root_names, specs, parameter_annotation=cls.PARAMETER_ANNOTATION)
        solution_code = "from mylibrary import default\n" + apply_parameter_constraints(
            base_code,
            specs,
            function_names,
            add_signatures=True,
            terminal_product=True,
            parameter_annotation=cls.PARAMETER_ANNOTATION,
            terminal_combine_op=cls.TERMINAL_COMBINE_OP,
            value_kind=cls.VALUE_KIND,
        )
        prompt = build_prompt(cls.PROMPT_TEMPLATE, specs, cls.VALUE_LABEL)
        return cls._make_task(dag_id, prompt, starter_code, solution_code, specs, num_constraints=num_constraints)


class BaseReturnValueConstraintsTask(BaseConstraintsTask):
    TASK_TYPE = TaskType.ADD_RETURN_VALUE
    TEMPLATE_BANK_KEY = "return_value_str"
    VAR_PREFIX = "key"
    VALUE_LABEL = "return value keys"
    PROMPT_TEMPLATE = PROMPT_RETURN_VALUE_CONSTRAINTS

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int = None, program_params=None) -> "BaseReturnValueConstraintsTask":
        seed, num_constraints, num_params = cls._constraint_params(seed, program_params)
        num_target = dag_data["num_target"]
        main_dags = list(dag_data["main_code_with_add_return_value_dags"]) + list(dag_data["main_code_dags"][num_target:])
        base_code = "from mylibrary import external\n" + build_starter_code(main_dags, seed, task_type=cls.TASK_TYPE_NAME, if_mode="backward")
        name_mapping: dict[str, str] = {}
        specs = cls._sample_specs(dag_id, seed, num_constraints, num_params)
        key_names = [spec["var"] for spec in specs]

        source_functions = _remap_names((dag_data["add_return_value_sink_ids"][target] for target in range(num_target)), name_mapping)
        function_names = set()
        for target in range(num_target):
            graph = json_graph.node_link_graph(dag_data["add_return_value_dags"][target])
            function_names.update(_remap_names(graph.nodes(), name_mapping))

        starter_code = seed_return_value_keys(base_code, source_functions, key_names)
        solution_body = add_return_values(base_code, source_functions, function_names, key_names)
        solution_code = apply_return_value_constraints(solution_body, specs, function_names)
        prompt = build_prompt(cls.PROMPT_TEMPLATE, specs, cls.VALUE_LABEL)
        return cls._make_task(dag_id, prompt, starter_code, solution_code, specs, num_constraints=num_constraints)


class BaseCacheFunctionConstraintsTask(BaseConstraintsTask):
    TASK_TYPE = TaskType.CACHE_FUNCTION
    TEMPLATE_BANK_KEY = "cache_slow_float"
    VAR_PREFIX = "slow"
    VALUE_LABEL = "cached slow values"
    PROMPT_TEMPLATE = PROMPT_CACHE_FUNCTION_CONSTRAINTS
    VALUE_TYPE = "float"
    DEFAULT_VALUE = 0.0
    VALUE_KIND = "float"

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int = None, program_params=None) -> "BaseCacheFunctionConstraintsTask":
        seed, num_constraints, num_params = cls._constraint_params(seed, program_params)
        num_target = dag_data["num_target"]
        main_dags = list(dag_data["main_code_with_cache_function_dags"]) + list(dag_data["main_code_dags"][num_target:])
        base_body = build_starter_code(main_dags, seed, task_type=cls.TASK_TYPE_NAME, if_mode="backward")
        name_mapping: dict[str, str] = {}
        specs = cls._sample_specs(dag_id, seed, num_constraints, num_params)
        slow_names = [spec["var"] for spec in specs]

        starter_body = base_body
        solution_body = base_body
        function_names = set()
        all_target_nodes = set()
        for target in range(num_target):
            graph = json_graph.node_link_graph(dag_data["cache_function_dags"][target])
            target_nodes = [_remap_name(node, name_mapping) for node in graph.nodes() if graph.out_degree(node) == 0]
            all_target_nodes.update(target_nodes)
            for target_node in target_nodes:
                for _spec in specs:
                    starter_body = wrap_function_return_with_slow(starter_body, target_node)
                    solution_body = wrap_function_return_with_slow(solution_body, target_node)
        starter_body = index_slow_calls(starter_body, all_target_nodes, len(specs))
        solution_body = index_slow_calls(solution_body, all_target_nodes, len(specs))

        for target in range(num_target):
            graph = json_graph.node_link_graph(dag_data["cache_function_dags"][target])
            ancestor_node = _remap_name(dag_data["cache_function_root_ids"][target], name_mapping)
            target_nodes = [_remap_name(node, name_mapping) for node in graph.nodes() if graph.out_degree(node) == 0]
            affected_nodes = {_remap_name(node, name_mapping) for node in graph.nodes() if node != dag_data["cache_function_root_ids"][target] and graph.out_degree(node) > 0}
            function_names.update(_remap_names(graph.nodes(), name_mapping))
            solution_body = move_slow_values_to_ancestor(
                solution_body,
                ancestor_node=ancestor_node,
                target_nodes=target_nodes,
                affected_nodes=affected_nodes,
                slow_names=slow_names,
                value_type=cls.VALUE_TYPE,
                default_value=cls.DEFAULT_VALUE,
            )

        starter_body = simplify_generated_slow_additions(starter_body)
        solution_body = simplify_generated_slow_additions(solution_body)
        solution_body = apply_parameter_constraints(solution_body, specs, function_names, call_target_names=function_names, value_kind=cls.VALUE_KIND)
        starter_code = "from mylibrary import slow\n" + starter_body
        solution_code = "from mylibrary import slow\n" + solution_body
        prompt = build_prompt(cls.PROMPT_TEMPLATE, specs, cls.VALUE_LABEL)
        return cls._make_task(dag_id, prompt, starter_code, solution_code, specs, num_constraints=num_constraints)


class BaseExtractHelperConstraintsTask(BaseConstraintsTask):
    TASK_TYPE = TaskType.EXTRACT_HELPER
    TEMPLATE_BANK_KEY = "extract_helper_mult"
    VAR_PREFIX = "mult"
    VALUE_LABEL = "extracted multipliers"
    PROMPT_TEMPLATE = PROMPT_EXTRACT_HELPER_CONSTRAINTS
    HELPER_FUNCTION_NAME = "get_multiplier"
    HELPER_TYPE = "float"
    COMBINE_OP = COMBINE_MULTIPLY
    VALUE_KIND = "float"

    @classmethod
    def _from_dag(cls, dag_id: str, dag_data: dict, seed: int = None, program_params=None) -> "BaseExtractHelperConstraintsTask":
        seed, num_constraints, num_params = cls._constraint_params(seed, program_params)
        num_target = dag_data["num_target"]
        main_dags = list(dag_data["main_code_with_extract_helper_dags"]) + list(dag_data["main_code_dags"][num_target:])
        base_body = build_starter_code(main_dags, seed, task_type=cls.TASK_TYPE_NAME, if_mode="forward")
        name_mapping: dict[str, str] = {}
        specs = cls._sample_specs(dag_id, seed, num_constraints, num_params)
        mult_names = [spec["var"] for spec in specs]

        starter_body = base_body
        solution_body = base_body
        function_names = set()
        for target in range(num_target):
            graph = json_graph.node_link_graph(dag_data["extract_helper_dags"][target])
            original_ancestor_nodes = [node for node in graph.nodes() if graph.in_degree(node) == 0]
            original_shared_node = dag_data["extract_helper_sink_ids"][target]
            ancestor_nodes = [_remap_name(node, name_mapping) for node in original_ancestor_nodes]
            shared_node = _remap_name(original_shared_node, name_mapping)
            affected_nodes = {
                _remap_name(node, name_mapping)
                for ancestor in original_ancestor_nodes
                for node in nx.descendants(graph, ancestor)
                if node != original_shared_node and nx.has_path(graph, node, original_shared_node)
            }
            function_names.update(_remap_names(graph.nodes(), name_mapping))
            for ancestor_node in ancestor_nodes:
                for spec in specs:
                    starter_body = retrieve_multiplier_for_function(
                        starter_body,
                        ancestor_node,
                        cls.HELPER_FUNCTION_NAME,
                        cls.HELPER_TYPE,
                        spec["var"],
                    )
            starter_body = index_helper_calls(starter_body, cls.HELPER_FUNCTION_NAME, mult_names)
            starter_body = simplify_generated_value_combinations(starter_body, mult_names, cls.COMBINE_OP)
            solution_body = move_multipliers_down_to_shared_node(
                solution_body,
                ancestor_nodes=ancestor_nodes,
                shared_node=shared_node,
                affected_nodes=affected_nodes,
                top_nodes=set(ancestor_nodes),
                mult_names=mult_names,
                helper_func_name=cls.HELPER_FUNCTION_NAME,
                helper_type=cls.HELPER_TYPE,
                combine_op=cls.COMBINE_OP,
            )

        solution_body = simplify_generated_value_combinations(solution_body, mult_names, cls.COMBINE_OP)
        solution_body = apply_extract_constraints(solution_body, specs, function_names, value_kind=cls.VALUE_KIND)
        starter_code = f"from mylibrary import {cls.HELPER_FUNCTION_NAME}\n" + starter_body
        solution_code = f"from mylibrary import {cls.HELPER_FUNCTION_NAME}\n" + solution_body
        prompt = build_prompt(cls.PROMPT_TEMPLATE, specs, cls.VALUE_LABEL)
        return cls._make_task(dag_id, prompt, starter_code, solution_code, specs, num_constraints=num_constraints)
