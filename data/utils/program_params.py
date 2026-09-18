"""Special parameters for generating codebases"""

from dataclasses import dataclass

@dataclass
class ProgramParams:

    num_branches: int = 0
    if_type: str = "none" # could be: "none" | "runtime"
    if_num_hops: int = 0
    if_breadth_depth_ratio: float = 0.5

    # Constraints parameters
    num_constraints: int = 25
    num_params: int = 1  # number of generated values such as mult1, mult2, ... For instruction-following we increase num_params > 1 for diversity

    @classmethod
    def default(cls) -> "ProgramParams":
        return cls()

    @property
    def max_num_constraints(self) -> int:
        return self.num_constraints

    @classmethod
    def from_kwargs(cls, pairs: list[str]) -> "ProgramParams":
        params = cls.default()

        for p in pairs or []:
            if "=" not in p:
                raise ValueError(f"--program_args entries must be key=value, got: {p}")
            k, v = p.split("=", 1)
            if k == "num_branches":
                params.num_branches = int(v)
            elif k == "if_type":
                assert v in ("none", "runtime"), f"Invalid if_type: {v!r}. Valid values: none, runtime"
                params.if_type = v
            elif k == "if_num_hops":
                params.if_num_hops = int(v)
            elif k == "if_breadth_depth_ratio":
                params.if_breadth_depth_ratio = float(v)
                assert 0.0 <= params.if_breadth_depth_ratio <= 1.0, f"if_breadth_depth_ratio must be in [0, 1], got {v!r}"
            elif k == "num_constraints":
                params.num_constraints = int(v)
            elif k == "num_params":
                params.num_params = int(v)
            else:
                raise ValueError(
                    f"Unknown program_args key: {k!r}. Valid keys: num_branches, "
                    "if_type, if_num_hops, if_breadth_depth_ratio, num_constraints, num_params"
                )
        if params.num_constraints <= 0:
            raise ValueError(f"num_constraints must be > 0, got {params.num_constraints}")
        if params.num_params <= 0:
            raise ValueError(f"num_params must be > 0, got {params.num_params}")
        if params.if_num_hops < 0:
            raise ValueError(f"if_num_hops must be >= 0, got {params.if_num_hops}")
        if not 0.0 <= params.if_breadth_depth_ratio <= 1.0:
            raise ValueError(f"if_breadth_depth_ratio must be in [0, 1], got {params.if_breadth_depth_ratio}")
        return params