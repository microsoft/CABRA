"""Prompts for runtime resolution tasks."""

# =================================== Math Tasks ==================================

PROMPT_DEAD_CODE = """
Some functions are unused when the solution.py script is run. Remove any function that is not used to influence the output of main() and replace their values with `val`. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Ignore branches that do not run when deciding which functions influence the output. For this dead-code task, after removing an unused function, replace calls to that removed function with `val` wherever they remain so the original branch structure stays valid.

For example, if you were given the following code block:
<example>
import sys

def check():
    return True

def a(val: float) -> float:
    if check():
        b_val = b(val)
        return b_val
    else:
        c_val = c(val)
        return c_val

def b(val: float) -> float:
    return val

def c(val: float) -> float:
    return val + 10.0

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should remove the function `c()`, since it is only used in a branch that does not run (because `check()` returns True, the else branch never executes), and then replace all calls to `c()` with `val` (for backwards compatibility). Leave `a()` and `b()` as is:
<output>
import sys

def check():
    return True

def a(val: float) -> float:
    if check():
        b_val = b(val)
        return b_val
    else:
        c_val = val
        return c_val

def b(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names that you do not remove (do not rename them). Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------


PROMPT_ADD_PARAMETER = """
For any function in solution.py with the parameter mult, recursively propagate mult down the call graph by passing it to every function call used to compute the return expression. This will require adding mult to the parameter signatures of any called functions with a default value of `mult: float = default()`, and then recursively applying the same transformation to those functions. Continue propagating mult until reaching terminal functions whose return expressions directly compute a value `X` and do not call other functions in the file (apart from library functions). Only those terminal functions should apply the multiplier by returning mult * X; intermediate functions should NOT multiply their results by mult. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Apply this transformation only inside branches that actually run; if another branch contains the same calls or computation, preserve it unchanged.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import default

def check():
    return True

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float, mult: float = default()) -> float:
    if check():
        c_val = c(val)
        return 2.0 * c_val
    else:
        c_val = c(val)
        return 2.0 * c_val

def c(val: float) -> float:
    return val + 0.5

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that a() is unchanged, and b() passes the `mult` parameter to c() only in the branch that actually executes. Then, you should modify the call signature of c() to accept `mult` with a default value of default(). Since c() is a terminal function on the running branch, it will apply the multiplier to its original computation, returning `mult * (val + 0.5)`. Do not pass `mult` in the branch that does not run, even though it contains the same computation.
<output>
import sys
from mylibrary import default

def check():
    return True

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float, mult: float = default()) -> float:
    if check():
        c_val = c(val, mult=mult)
        return 2.0 * c_val
    else:
        c_val = c(val)
        return 2.0 * c_val

def c(val: float, mult: float = default()) -> float:
    return mult * (val + 0.5)

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Do NOT modify functions that are upstream of the function that already has the mult parameter. In the example above, a() is unchanged.

default() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. The code may change; do not assume that any default values will persist. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_RETURN_VALUE = """
In solution.py, external() previously returned a float, but mylibrary now defines it as returning tuple[float, str]. Update the code so the float preserves the original computation, while the str is propagated upward through the call chain. Any function that directly or indirectly uses the result of external() in a branch that actually executes should return tuple[float, str]: the original computed value as the first element, and the propagated string as the second. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Unpack and propagate the string only through branches that actually run; preserve non-running branches unchanged even if they contain the same calls.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import external

def check():
    return True

def a(val: float) -> float:
    if check():
        b_val = b(val)
        c_val = c(val)
        return b_val + c_val
    else:
        b_val = b(val)
        c_val = c(val)
        return b_val + c_val

def b(val: float) -> float:
    if check():
        return external(val)
    else:
        return val

def c(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that b() now returns the new tuple value from external(). The string should propagate up the call graph recursively through the branch that actually runs in a(), preserving the original float computation. c() and the inactive branches will remain unchanged.
<output>
import sys
from mylibrary import external

def check():
    return True

def a(val: float) -> tuple[float, str]:
    if check():
        b_val, key = b(val)
        c_val = c(val)
        return (b_val + c_val, key)
    else:
        b_val = b(val)
        c_val = c(val)
        return b_val + c_val

def b(val: float) -> tuple[float, str]:
    if check():
        return external(val)
    else:
        return val

def c(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that we did not return the key to any of the branches that do not actually influence the final output. Type hints may not describe inactive return branches; preserve inactive branches even if their return shape differs from the annotation.

If a function receives multiple propagated strings, it may return any one of them, since they are guaranteed to be identical. external() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_CACHE_FUNCTION_DIAMOND = """
In solution.py, some functions call slow(), which is expensive and deterministic, so it should be run as few times as possible. Refactor the code so that each repeated call to slow() that influences a running branch is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the result in a temporary variable called `temp`, then pass that value down as an additional argument to the functions that use it (e.g., a(val: float) -> a(val: float, temp: float)). Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Move slow(), pass `temp`, and replace slow() with `temp` only in branches that actually run; preserve non-running branches unchanged even if they contain the same slow() calls.

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import slow

def check():
    return True

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float) -> float:
    if check():
        c_val = c(val)
        d_val = d(val)
        return c_val + d_val
    else:
        c_val = c(val)
        d_val = d(val)
        return c_val + d_val

def c(val: float) -> float:
    if check():
        return -4 * slow()
    else:
        return -4 * slow()

def d(val: float) -> float:
    if check():
        return 2 * slow()
    else:
        return 2 * slow()

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that the calls to slow() in the running branches of c() and d() are moved to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores the intermediate value of slow() and passes it down to the other functions only on the running branch:
<output>
import sys
from mylibrary import slow

def check():
    return True

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float) -> float:
    if check():
        temp: float = slow()
        c_val = c(val, temp)
        d_val = d(val, temp)
        return c_val + d_val
    else:
        c_val = c(val)
        d_val = d(val)
        return c_val + d_val

def c(val: float, temp: float) -> float:
    if check():
        return -4 * temp
    else:
        return -4 * slow()

def d(val: float, temp: float) -> float:
    if check():
        return 2 * temp
    else:
        return 2 * slow()

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

Using global variables is BANNED. Adding them will cause your solution to be marked incorrect automatically, so you must follow our specified approach of moving the repeat computation to the right function and passing the result down to all necessary functions as an argument.

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have defined `temp` in the a() function, the correct answer is to define it in the b() function and pass it down to the other functions, as b() is the lowest common ancestor of c() and d(). The solution is NOT always to define the call to `slow()` in the functions called by `main()`.

All calls to slow() return the exact same value. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------


PROMPT_EXTRACT_HELPER_DIAMOND = """
In solution.py, multiple functions independently use a multiplier from get_multiplier(val), which returns a multiplier for a given value. To reduce this duplication, refactor the code so the multiplier is defined once at the earliest shared downstream function reached by following calls from each of those functions, then return that multiplier back up to the functions that need it on the return path where the condition is satisfied. Do not move the multiplier computation into a caller/ancestor of the duplicated functions. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Move get_multiplier(val), return the helper value, and replace original helper calls only in branches that actually run; preserve non-running branches unchanged even if they contain the same helper computation.

A function `f()` is the nearest shared downstream function of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, `g_i()` calls `f()` directly or indirectly through one or more intermediate functions.
2. There is no other function `h()` such that:
   * every `g_i()` calls `h()` directly or indirectly, and
   * `h()` calls `f()` directly or indirectly.
In other words, `f()` is the earliest function reached in common when tracing calls downward from all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import get_multiplier

def check():
    return True

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    if check():
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * (d_val + 1.0)
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * (d_val + 1.0)

def c(val: float) -> float:
    if check():
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * d_val
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * d_val

def d(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

First, you should identify that b() and c() both compute get_multiplier(val) in their running branches. Then, trace their calls downward toward their callees. The first shared downstream function is d(), so move get_multiplier(val) into d()'s running branch, return it along with d()'s original result only on the return path where the condition is satisfied, and reuse that returned multiplier in the running branches of b() and c(). Leave non-running branches using their original branch-local get_multiplier(val) calls.
<output>
import sys
from mylibrary import get_multiplier

def check():
    return True

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    if check():
        d_val, mult = d(val)
        return mult * (d_val + 1.0)
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * (d_val + 1.0)

def c(val: float) -> float:
    if check():
        d_val, mult = d(val)
        return mult * d_val
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * d_val

def d(val: float) -> tuple[float, float]:
    if check():
        mult: float = get_multiplier(val)
        return val, mult
    else:
        return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

The correct answer is to move get_multiplier(val) to the running branch of d(), as it is the earliest shared downstream function on the running branches. Further, note that the correct answer did not return the multiplier value beyond functions b() and c() (i.e., not to a()), as a() does not need the multiplier in its computation. Finally, see that we did not add an extra return value to the branch of d() that did not execute, and we left the non-running branches of b() and c() using their original get_multiplier(val) calls. Type hints may not describe inactive return branches; preserve inactive branches even if their return shape differs from the annotation.

get_multiplier() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# =========================== String Function =================================

PROMPT_DEAD_CODE_STRING = """
Some functions are unused when the solution.py script is run. Remove any function that is not used to influence the output of main() and replace their values with `val`. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Ignore branches that do not run when deciding which functions influence the output. For this dead-code task, after removing an unused function, replace calls to that removed function with `val` wherever they remain so the original branch structure stays valid.

For example, if you were given the following code block:
<example>
import sys
import strops

def check():
    return True

def a(val: str) -> str:
    if check():
        b_val = b(val)
        return b_val
    else:
        c_val = c(val)
        return c_val

def b(val: str) -> str:
    return val

def c(val: str) -> str:
    return strops.reverse(val)

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should remove the function `c()`, since it is only used in a branch that does not run (because `check()` returns True, the else branch never executes), and then replace all calls to `c()` with `val` (for backwards compatibility). Leave `a()` and `b()` as is:
<output>
import sys
import strops

def check():
    return True

def a(val: str) -> str:
    if check():
        b_val = b(val)
        return b_val
    else:
        c_val = val
        return c_val

def b(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

strops is undefined and will be defined later; do not try to define it. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names that you do not remove (do not rename them). Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_PARAMETER_STRING = """
For any function in solution.py with the parameter prefix, recursively propagate prefix down the call graph by passing it to every function call used to compute the return expression. This will require adding prefix to the parameter signatures of any called functions with a default value of `prefix: str = default()`, and then recursively applying the same transformation to those functions. Continue propagating prefix until reaching terminal functions whose return expressions directly compute a value `X` and do not call other functions in the file (apart from library functions). Only those terminal functions should add the prefix by returning prefix + X; intermediate functions should NOT append the prefix to their results. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Apply this transformation only inside branches that actually run; if another branch contains the same calls or computation, preserve it unchanged.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import default

def check():
    return True

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str, prefix: str = default()) -> str:
    if check():
        c_val = c(val)
        return strops.reverse(c_val)
    else:
        c_val = c(val)
        return strops.reverse(c_val)

def c(val: str) -> str:
    return strops.interleave(val, "abc")

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that a() is unchanged, and b() passes the `prefix` parameter to c() only in the branch that actually executes. Then, you should modify the call signature of c() to accept `prefix` with a default value of default(). Since c() is a terminal function on the running branch, it will apply the prefix to its original computation, returning `prefix + strops.interleave(val, "abc")`. Do not pass `prefix` in the branch that does not run, even though it contains the same computation.
<output>
import sys
import strops
from mylibrary import default

def check():
    return True

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str, prefix: str = default()) -> str:
    if check():
        c_val = c(val, prefix=prefix)
        return strops.reverse(c_val)
    else:
        c_val = c(val)
        return strops.reverse(c_val)

def c(val: str, prefix: str = default()) -> str:
    return prefix + strops.interleave(val, "abc")

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Do NOT modify functions that are upstream of the function that already has the prefix parameter. In the example above, a() is unchanged.

strops, default(), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. The code may change; do not assume that any default values will persist. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_RETURN_VALUE_STRING = """
In solution.py, external() previously returned a str, but mylibrary now defines it as returning tuple[str, str]. Update the code so the first str preserves the original computation, while the second str is propagated upward through the call chain. Any function that directly or indirectly uses the result of external() in a branch that actually executes should return tuple[str, str]: the original computed value as the first element, and the propagated string as the second. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Unpack and propagate the string only through branches that actually run; preserve non-running branches unchanged even if they contain the same calls.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import external

def check():
    return True

def a(val: str) -> str:
    if check():
        b_val = b(val)
        c_val = c(val)
        return strops.interleave(b_val, c_val)
    else:
        b_val = b(val)
        c_val = c(val)
        return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    if check():
        return external(val)
    else:
        return val

def c(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that b() now returns the new tuple value from external(). The string should propagate up the call graph recursively through the branch that actually runs in a(), preserving the original string computation. c() and the inactive branches will remain unchanged.
<output>
import sys
import strops
from mylibrary import external

def check():
    return True

def a(val: str) -> tuple[str, str]:
    if check():
        b_val, key = b(val)
        c_val = c(val)
        return (strops.interleave(b_val, c_val), key)
    else:
        b_val = b(val)
        c_val = c(val)
        return strops.interleave(b_val, c_val)

def b(val: str) -> tuple[str, str]:
    if check():
        return external(val)
    else:
        return val

def c(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that we did not return the key to any of the branches that do not actually influence the final output. Type hints may not describe inactive return branches; preserve inactive branches even if their return shape differs from the annotation.

If a function receives multiple propagated strings, it may return any one of them, since they are guaranteed to be identical. external() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_CACHE_FUNCTION_DIAMOND_STRING = """
In solution.py, some functions call slow(), which is expensive and deterministic, so it should be run as few times as possible. Refactor the code so that each repeated call to slow() that influences a running branch is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the result in a temporary variable called `temp`, then pass that value down as an additional argument to the functions that use it (e.g., a(val: str) -> a(val: str, temp: str)). Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Move slow(), pass `temp`, and replace slow() with `temp` only in branches that actually run; preserve non-running branches unchanged even if they contain the same slow() calls.

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import slow

def check():
    return True

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str) -> str:
    if check():
        c_val = c(val)
        d_val = d(val)
        return strops.interleave(c_val, d_val)
    else:
        c_val = c(val)
        d_val = d(val)
        return strops.interleave(c_val, d_val)

def c(val: str) -> str:
    if check():
        return strops.reverse(slow())
    else:
        return strops.reverse(slow())

def d(val: str) -> str:
    if check():
        return slow() + val
    else:
        return slow() + val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that the calls to slow() in the running branches of c() and d() are moved to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores the intermediate value of slow() and passes it down to the other functions only on the running branch:
<output>
import sys
import strops
from mylibrary import slow

def check():
    return True

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str) -> str:
    if check():
        temp: str = slow()
        c_val = c(val, temp)
        d_val = d(val, temp)
        return strops.interleave(c_val, d_val)
    else:
        c_val = c(val)
        d_val = d(val)
        return strops.interleave(c_val, d_val)

def c(val: str, temp: str) -> str:
    if check():
        return strops.reverse(temp)
    else:
        return strops.reverse(slow())

def d(val: str, temp: str) -> str:
    if check():
        return temp + val
    else:
        return slow() + val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

Using global variables is BANNED. Adding them will cause your solution to be marked incorrect automatically, so you must follow our specified approach of moving the repeat computation to the right function and passing the result down to all necessary functions as an argument.

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have defined `temp` in the a() function, the correct answer is to define it in the b() function and pass it down to the other functions, as b() is the lowest common ancestor of c() and d(). The solution is NOT always to define the call to `slow()` in the functions called by `main()`.

All calls to slow() return the exact same value. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------


PROMPT_EXTRACT_HELPER_DIAMOND_STRING = """
In solution.py, multiple functions independently use a key from get_key(val), which returns a key for a given value. To reduce this duplication, refactor the code so the key is defined once at the earliest shared downstream function reached by following calls from each of those functions, then return that key back up to the functions that need it on the return path where the condition is satisfied. Do not move the key computation into a caller/ancestor of the duplicated functions. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Move get_key(val), return the helper value, and replace original helper calls only in branches that actually run; preserve non-running branches unchanged even if they contain the same helper computation.

A function `f()` is the nearest shared downstream function of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, `g_i()` calls `f()` directly or indirectly through one or more intermediate functions.
2. There is no other function `h()` such that:
   * every `g_i()` calls `h()` directly or indirectly, and
   * `h()` calls `f()` directly or indirectly.
In other words, `f()` is the earliest function reached in common when tracing calls downward from all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import get_key

def check():
    return True

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    if check():
        key: str = get_key(val)
        d_val = d(val)
        return key + d_val
    else:
        key: str = get_key(val)
        d_val = d(val)
        return key + d_val

def c(val: str) -> str:
    if check():
        key: str = get_key(val)
        d_val = d(val)
        return strops.swap_halves(key, d_val)
    else:
        key: str = get_key(val)
        d_val = d(val)
        return strops.swap_halves(key, d_val)

def d(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

First, you should identify that b() and c() both compute get_key(val) in their running branches. Then, trace their calls downward toward their callees. The first shared downstream function is d(), so move get_key(val) into d()'s running branch, return it along with d()'s original result only on the return path where the condition is satisfied, and reuse that returned key in the running branches of b() and c(). Leave non-running branches using their original branch-local get_key(val) calls.
<output>
import sys
import strops
from mylibrary import get_key

def check():
    return True

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    if check():
        d_val, key = d(val)
        return key + d_val
    else:
        key: str = get_key(val)
        d_val = d(val)
        return key + d_val

def c(val: str) -> str:
    if check():
        d_val, key = d(val)
        return strops.swap_halves(key, d_val)
    else:
        key: str = get_key(val)
        d_val = d(val)
        return strops.swap_halves(key, d_val)

def d(val: str) -> tuple[str, str]:
    if check():
        key: str = get_key(val)
        return val, key
    else:
        return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

The correct answer is to move get_key(val) to the running branch of d(), as it is the earliest shared downstream function on the running branches. Further, note that the correct answer did not return the key value beyond functions b() and c() (i.e., not to a()), as a() does not need the key in its computation. Finally, see that we did not add an extra return value to the branch of d() that did not execute, and we left the non-running branches of b() and c() using their original get_key(val) calls. Type hints may not describe inactive return branches; preserve inactive branches even if their return shape differs from the annotation.

strops, get_key(), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# =========================== Array Function =================================

PROMPT_DEAD_CODE_ARRAY = """
Some functions are unused when the solution.py script is run. Remove any function that is not used to influence the output of main() and replace their values with `val`. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Ignore branches that do not run when deciding which functions influence the output. For this dead-code task, after removing an unused function, replace calls to that removed function with `val` wherever they remain so the original branch structure stays valid.

For example, if you were given the following code block:
<example>
import sys
import numpy as np

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    if check():
        b_val = b(val)
        return b_val
    else:
        c_val = c(val)
        return c_val

def b(val: np.ndarray) -> np.ndarray:
    return val

def c(val: np.ndarray) -> np.ndarray:
    return val + 10.0

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should remove the function `c()`, since it is only used in a branch that does not run (because `check()` returns True, the else branch never executes), and then replace all calls to `c()` with `val` (for backwards compatibility). Leave `a()` and `b()` as is:
<output>
import sys
import numpy as np

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    if check():
        b_val = b(val)
        return b_val
    else:
        c_val = val
        return c_val

def b(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names that you do not remove (do not rename them). Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_PARAMETER_ARRAY = """
For any function in solution.py with the parameter mult, recursively propagate mult down the call graph by passing it to every function call used to compute the return expression. This will require adding mult to the parameter signatures of any called functions with a default value of `mult: float = default()`, and then recursively applying the same transformation to those functions. Continue propagating mult until reaching terminal functions whose return expressions directly compute a value `X` and do not call other functions in the file (apart from library functions). Only those terminal functions should apply the multiplier by returning mult * X; intermediate functions should NOT multiply their results by mult. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Apply this transformation only inside branches that actually run; if another branch contains the same calls or computation, preserve it unchanged.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import default

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray, mult: float = default()) -> np.ndarray:
    if check():
        c_val = c(val)
        return 2.0 * c_val
    else:
        c_val = c(val)
        return 2.0 * c_val

def c(val: np.ndarray) -> np.ndarray:
    return val + 0.5

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that a() is unchanged, and b() passes the `mult` parameter to c() only in the branch that actually executes. Then, you should modify the call signature of c() to accept `mult` with a default value of default(). Since c() is a terminal function on the running branch, it will apply the multiplier to its original computation, returning `mult * (val + 0.5)`. Do not pass `mult` in the branch that does not run, even though it contains the same computation.
<output>
import sys
import numpy as np
from mylibrary import default

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray, mult: float = default()) -> np.ndarray:
    if check():
        c_val = c(val, mult=mult)
        return 2.0 * c_val
    else:
        c_val = c(val)
        return 2.0 * c_val

def c(val: np.ndarray, mult: float = default()) -> np.ndarray:
    return mult * (val + 0.5)

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Do NOT modify functions that are upstream of the function that already has the mult parameter. In the example above, a() is unchanged.

default() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. The code may change; do not assume that any default values will persist. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_RETURN_VALUE_ARRAY = """
In solution.py, external() previously returned a numpy array, but mylibrary now defines it as returning tuple[np.ndarray, str]. Update the code so the numpy array preserves the original computation, while the str is propagated upward through the call chain. Any function that directly or indirectly uses the result of external() in a branch that actually executes should return tuple[np.ndarray, str]: the original computed value as the first element, and the propagated string as the second. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Unpack and propagate the string only through branches that actually run; preserve non-running branches unchanged even if they contain the same calls.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import external

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    if check():
        b_val = b(val)
        c_val = c(val)
        return b_val + c_val
    else:
        b_val = b(val)
        c_val = c(val)
        return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    if check():
        return external(val)
    else:
        return val

def c(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that b() now returns the new tuple value from external(). The string should propagate up the call graph recursively through the branch that actually runs in a(), preserving the original numpy array computation. c() and the inactive branches will remain unchanged.
<output>
import sys
import numpy as np
from mylibrary import external

def check():
    return True

def a(val: np.ndarray) -> tuple[np.ndarray, str]:
    if check():
        b_val, key = b(val)
        c_val = c(val)
        return (b_val + c_val, key)
    else:
        b_val = b(val)
        c_val = c(val)
        return b_val + c_val

def b(val: np.ndarray) -> tuple[np.ndarray, str]:
    if check():
        return external(val)
    else:
        return val

def c(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that we did not return the key to any of the branches that do not actually influence the final output. Type hints may not describe inactive return branches; preserve inactive branches even if their return shape differs from the annotation.

If a function receives multiple propagated strings, it may return any one of them, since they are guaranteed to be identical. external() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------

PROMPT_CACHE_FUNCTION_DIAMOND_ARRAY = """
In solution.py, some functions call slow(), which is expensive and deterministic, so it should be run as few times as possible. Refactor the code so that each repeated call to slow() that influences a running branch is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the result in a temporary variable called `temp`, then pass that value down as an additional argument to the functions that use it (e.g., a(val: np.ndarray) -> a(val: np.ndarray, temp: float)). Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Move slow(), pass `temp`, and replace slow() with `temp` only in branches that actually run; preserve non-running branches unchanged even if they contain the same slow() calls.

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import slow

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray) -> np.ndarray:
    if check():
        c_val = c(val)
        d_val = d(val)
        return c_val + d_val
    else:
        c_val = c(val)
        d_val = d(val)
        return c_val + d_val

def c(val: np.ndarray) -> np.ndarray:
    if check():
        return -4 * slow() + val
    else:
        return -4 * slow() + val

def d(val: np.ndarray) -> np.ndarray:
    if check():
        return 2 * slow() + val
    else:
        return 2 * slow() + val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that the calls to slow() in the running branches of c() and d() are moved to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores the intermediate value of slow() and passes it down to the other functions only on the running branch:
<output>
import sys
import numpy as np
from mylibrary import slow

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray) -> np.ndarray:
    if check():
        temp: float = slow()
        c_val = c(val, temp)
        d_val = d(val, temp)
        return c_val + d_val
    else:
        c_val = c(val)
        d_val = d(val)
        return c_val + d_val

def c(val: np.ndarray, temp: float) -> np.ndarray:
    if check():
        return -4 * temp + val
    else:
        return -4 * slow() + val

def d(val: np.ndarray, temp: float) -> np.ndarray:
    if check():
        return 2 * temp + val
    else:
        return 2 * slow() + val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

Using global variables is BANNED. Adding them will cause your solution to be marked incorrect automatically, so you must follow our specified approach of moving the repeat computation to the right function and passing the result down to all necessary functions as an argument.

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have defined `temp` in the a() function, the correct answer is to define it in the b() function and pass it down to the other functions, as b() is the lowest common ancestor of c() and d(). The solution is NOT always to define the call to `slow()` in the functions called by `main()`.

All calls to slow() return the exact same value. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()

# -----------------------------------------------------------


PROMPT_EXTRACT_HELPER_DIAMOND_ARRAY = """
In solution.py, multiple functions independently use a multiplier from get_multiplier(val), which returns a multiplier for a given value. To reduce this duplication, refactor the code so the multiplier is defined once at the earliest shared downstream function reached by following calls from each of those functions, then return that multiplier back up to the functions that need it on the return path where the condition is satisfied. Do not move the multiplier computation into a caller/ancestor of the duplicated functions. Some code may be guarded by conditional expressions; only the if/else branch that actually executes influences the output. Move get_multiplier(val), return the helper value, and replace original helper calls only in branches that actually run; preserve non-running branches unchanged even if they contain the same helper computation.

A function `f()` is the nearest shared downstream function of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, `g_i()` calls `f()` directly or indirectly through one or more intermediate functions.
2. There is no other function `h()` such that:
   * every `g_i()` calls `h()` directly or indirectly, and
   * `h()` calls `f()` directly or indirectly.
In other words, `f()` is the earliest function reached in common when tracing calls downward from all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import get_multiplier

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    if check():
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * (d_val + 1.0)
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * (d_val + 1.0)

def c(val: np.ndarray) -> np.ndarray:
    if check():
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * d_val
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * d_val

def d(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

First, you should identify that b() and c() both compute get_multiplier(val) in their running branches. Then, trace their calls downward toward their callees. The first shared downstream function is d(), so move get_multiplier(val) into d()'s running branch, return it along with d()'s original result only on the return path where the condition is satisfied, and reuse that returned multiplier in the running branches of b() and c(). Leave non-running branches using their original branch-local get_multiplier(val) calls.
<output>
import sys
import numpy as np
from mylibrary import get_multiplier

def check():
    return True

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    if check():
        d_val, mult = d(val)
        return mult * (d_val + 1.0)
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * (d_val + 1.0)

def c(val: np.ndarray) -> np.ndarray:
    if check():
        d_val, mult = d(val)
        return mult * d_val
    else:
        mult: float = get_multiplier(val)
        d_val = d(val)
        return mult * d_val

def d(val: np.ndarray) -> tuple[np.ndarray, float]:
    if check():
        mult: float = get_multiplier(val)
        return val, mult
    else:
        return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

The correct answer is to move get_multiplier(val) to the running branch of d(), as it is the earliest shared downstream function on the running branches. Further, note that the correct answer did not return the multiplier value beyond functions b() and c() (i.e., not to a()), as a() does not need the multiplier in its computation. Finally, see that we did not add an extra return value to the branch of d() that did not execute, and we left the non-running branches of b() and c() using their original get_multiplier(val) calls. Type hints may not describe inactive return branches; preserve inactive branches even if their return shape differs from the annotation.

get_multiplier() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block, main() function, or any of the conditional expressions. Do not remove, simplify, or restructure any existing if/else blocks, control flow, or state logic in any function. All branches and conditional structures must be preserved exactly as written, even if they appear redundant or unreachable.
""".strip()
