"""Base prompts for function traversal/search tasks."""

# =================================== Math Tasks ==================================

PROMPT_DEAD_CODE = """
Some functions are unused when the solution.py script is run. Remove any function that is not reachable from main() through the call graph.

For example, if you were given the following code block:
<example>
import sys

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float) -> float:
    return val

def main(val: float):
    return b(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should remove the function `a()`, since it is not reached through `main()`, and leave `b()` as is:
<output>
import sys

def b(val: float) -> float:
    return val

def main(val: float):
    return b(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names that you do not remove (do not rename them). Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_PARAMETER = """
For any function in solution.py with the parameter mult, recursively propagate mult down the call graph by passing it to every function call used to compute the return expression. This will require adding mult to the parameter signatures of any called functions with a default value of `mult: float = default()`, and then recursively applying the same transformation to those functions. Continue propagating mult until reaching terminal functions whose return expressions directly compute a value `X` and do not call other functions in the file (apart from library functions). Only those terminal functions should apply the multiplier by returning mult * X; intermediate functions should NOT multiply their results by mult.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import default

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float, mult: float = default()) -> float:
    c_val = c(val)
    return 2.0 * c_val

def c(val: float) -> float:
    return val + 0.5

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that a() is unchanged, and b() passes the `mult` parameter to c(). Then, you should modify the call signature of c() to accept `mult` with a default value of default(). Since c() is a terminal function, it will apply the multiplier to its original computation, returning `mult * (val + 0.5)`.
<output>
import sys
from mylibrary import default

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float, mult: float = default()) -> float:
    c_val = c(val, mult=mult)
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

default() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function. The code may change; do not assume that any default values will persist.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_RETURN_VALUE = """
In solution.py, external() previously returned a float, but mylibrary now defines it as returning tuple[float, str]. Update the code so the float preserves the original computation, while the str is propagated upward through the call chain. Any function that directly or indirectly uses the result of external() should return tuple[float, str]: the original computed value as the first element, and the propagated string as the second.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import external

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    return external(val)

def c(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that b() now returns a tuple of type tuple[float, str] with the new values from external(). The string should propagate up the call graph recursively, modifying a() next, to preserve the original float computation. c() will remain unchanged.
<output>
import sys
from mylibrary import external

def a(val: float) -> tuple[float, str]:
    b_val, key = b(val)
    c_val = c(val)
    return b_val + c_val, key

def b(val: float) -> tuple[float, str]:
    return external(val)

def c(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

If a function receives multiple propagated strings, it may return any one of them, since they are guaranteed to be identical. external() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------

PROMPT_CACHE_FUNCTION_DIAMOND = """
In solution.py, some functions call slow(), which is expensive and deterministic, so it should be run as few times as possible. Refactor the code so that each repeated call to slow() is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the result in a temporary variable called `temp`, then pass that value down as an additional argument to the functions that use it (e.g., a(val: float) -> a(val: float, temp: float)). 

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
from mylibrary import slow

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float) -> float:
    c_val = c(val)
    d_val = d(val)
    return c_val + d_val

def c(val: float) -> float:
    return -4 * slow()

def d(val: float) -> float:
    e_val = e(val)
    return 2 * slow() + e_val

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that the calls to slow() in c() and d() are moved to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores the intermediate value of slow() and passes it down to the other functions:
<output>
import sys
from mylibrary import slow

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float) -> float:
    temp: float = slow()
    c_val = c(val, temp)
    d_val = d(val, temp)
    return c_val + d_val

def c(val: float, temp: float) -> float:
    return -4 * temp

def d(val: float, temp: float) -> float:
    e_val = e(val)
    return 2 * temp + e_val

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

Using global variables is BANNED. Adding them will cause your solution to be marked incorrect automatically, so you must follow our specified approach of moving the repeat computation to the right function and passing the result down to all necessary functions as an argument.

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have defined `temp` in the a() function, the correct answer is to define it in the b() function and pass it down to the other functions, as b() is the lowest common ancestor of c() and d(). The solution is NOT always to define the call to `slow()` in the functions called by `main()`. Further, note that the correct answer did not keep passing `temp` as an argument to the e() function, as the value is not used beyond c() and d().

All calls to slow() return the exact same value. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------


PROMPT_EXTRACT_HELPER_DIAMOND = """
In solution.py, multiple functions independently call get_multiplier(val), which returns a multiplier for a given value. To reduce this duplication, refactor the code so the multiplier is defined once at the earliest shared downstream function reached by following calls from each of those functions, then return that multiplier back up to the functions that need it. Do not move the multiplier computation into a caller/ancestor of the duplicated functions.

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

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    d_val = d(val)
    e_val = e(val)
    return get_multiplier(val) * (d_val + e_val)

def c(val: float) -> float:
    d_val = d(val)
    return get_multiplier(val) * d_val

def d(val: float) -> float:
    e_val = e(val)
    return e_val

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

First, you should identify that b() and c() both call get_multiplier(val). Then, trace their calls downward toward their callees. The first shared downstream function is d(), so move get_multiplier(val) into d(), return it along with d()'s original result, and reuse that returned multiplier in b() and c().
<output>
import sys
from mylibrary import get_multiplier

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    d_val, mult = d(val)
    e_val = e(val)
    return mult * (d_val + e_val)

def c(val: float) -> float:
    d_val, mult = d(val)
    return mult * d_val

def d(val: float) -> tuple[float, float]:
    e_val = e(val)
    return e_val, get_multiplier(val)

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have moved the get_multiplier(val) call to the e() function, the correct answer is to move it to the d() function, as it is earlier in the call graph. Further, note that the correct answer did not return the multiplier value beyond functions b() and c() (i.e., not to a()), as a() does not need the multiplier in its computation.

get_multiplier() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# =========================== String Function =================================

PROMPT_DEAD_CODE_STRING = """
Some functions are unused when the solution.py script is run. Remove any function that is not reachable from main() through the call graph.

For example, if you were given the following code block:
<example>
import sys
import strops

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str) -> str:
    return val

def main(val: str):
    return b(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should remove the function `a()`, since it is not reached through `main()`, and leave `b()` as is:
<output>
import sys
import strops

def b(val: str) -> str:
    return val

def main(val: str):
    return b(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

strops is undefined and will be defined later; do not try to define it. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names that you do not remove (do not rename them). Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_PARAMETER_STRING = """
For any function in solution.py with the parameter prefix, recursively propagate prefix down the call graph by passing it to every function call used to compute the return expression. This will require adding prefix to the parameter signatures of any called functions with a default value of `prefix: str = default()`, and then recursively applying the same transformation to those functions. Continue propagating prefix until reaching terminal functions whose return expressions directly compute a value `X` and do not call other functions in the file (apart from library functions). Only those terminal functions should add the prefix by returning prefix + X; intermediate functions should NOT append the prefix to their results.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import default

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str, prefix: str = default()) -> str:
    c_val = c(val)
    return strops.reverse(c_val)

def c(val: str) -> str:
    return strops.interleave(val, "abc")

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that a() is unchanged, and b() passes the `prefix` parameter to c(). Then, you should modify the call signature of c() to accept `prefix` with a default value of default(). Since c() is a terminal function, it will apply the prefix to its original computation, returning `prefix + strops.interleave(val, "abc")`.
<output>
import sys
import strops
from mylibrary import default

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str, prefix: str = default()) -> str:
    c_val = c(val, prefix=prefix)
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

strops, default(), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function. The code may change; do not assume that any default values will persist.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_RETURN_VALUE_STRING = """
In solution.py, external() previously returned a str, but mylibrary now defines it as returning tuple[str, str]. Update the code so the first str preserves the original computation, while the second str is propagated upward through the call chain. Any function that directly or indirectly uses the result of external() should return tuple[str, str]: the original computed value as the first element, and the propagated string as the second.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import external

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    return external(val)

def c(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that b() now returns a tuple of type tuple[str, str] with the new values from external(). The string should propagate up the call graph recursively, modifying a() next, to preserve the original string computation. c() will remain unchanged.
<output>
import sys
import strops
from mylibrary import external

def a(val: str) -> tuple[str, str]:
    b_val, key = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val), key

def b(val: str) -> tuple[str, str]:
    return external(val)

def c(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

If a function receives multiple propagated strings, it may return any one of them, since they are guaranteed to be identical. external() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------

PROMPT_CACHE_FUNCTION_DIAMOND_STRING = """
In solution.py, some functions call slow(), which is expensive and deterministic, so it should be run as few times as possible. Refactor the code so that each repeated call to slow() is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the result in a temporary variable called `temp`, then pass that value down as an additional argument to the functions that use it (e.g., a(val: str) -> a(val: str, temp: str)). 

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
import strops
from mylibrary import slow

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str) -> str:
    c_val = c(val)
    d_val = d(val)
    return strops.interleave(c_val, d_val)

def c(val: str) -> str:
    return strops.reverse(slow())

def d(val: str) -> str:
    e_val = e(val)
    return slow() + e_val

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that the calls to slow() in c() and d() are moved to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores the intermediate value of slow() and passes it down to the other functions:
<output>
import sys
import strops
from mylibrary import slow

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str) -> str:
    temp: str = slow()
    c_val = c(val, temp)
    d_val = d(val, temp)
    return strops.interleave(c_val, d_val)

def c(val: str, temp: str) -> str:
    return strops.reverse(temp)

def d(val: str, temp: str) -> str:
    e_val = e(val)
    return temp + e_val

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

Using global variables is BANNED. Adding them will cause your solution to be marked incorrect automatically, so you must follow our specified approach of moving the repeat computation to the right function and passing the result down to all necessary functions as an argument.

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have defined `temp` in the a() function, the correct answer is to define it in the b() function and pass it down to the other functions, as b() is the lowest common ancestor of c() and d(). The solution is NOT always to define the call to `slow()` in the functions called by `main()`. Further, note that the correct answer did not keep passing `temp` as an argument to the e() function, as the value is not used beyond c() and d().

All calls to slow() return the exact same value. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------


PROMPT_EXTRACT_HELPER_DIAMOND_STRING = """
In solution.py, multiple functions independently call get_key(val), which returns a key for a given value. To reduce this duplication, refactor the code so the key is defined once at the earliest shared downstream function reached by following calls from each of those functions, then return that key back up to the functions that need it. Do not move the key computation into a caller/ancestor of the duplicated functions.

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

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    d_val = d(val)
    e_val = e(val)
    return get_key(val) + strops.zip_chars(d_val, e_val)

def c(val: str) -> str:
    d_val = d(val)
    return strops.swap_halves(get_key(val), d_val)

def d(val: str) -> str:
    e_val = e(val)
    return e_val

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

First, you should identify that b() and c() both call get_key(val). Then, trace their calls downward toward their callees. The first shared downstream function is d(), so move get_key(val) into d(), return it along with d()'s original result, and reuse that returned key in b() and c().
<output>
import sys
import strops
from mylibrary import get_key

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    d_val, key = d(val)
    e_val = e(val)
    return key + strops.zip_chars(d_val, e_val)

def c(val: str) -> str:
    d_val, key = d(val)
    return strops.swap_halves(key, d_val)

def d(val: str) -> tuple[str, str]:
    e_val = e(val)
    return e_val, get_key(val)

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have moved the get_key(val) call to the e() function, the correct answer is to move it to the d() function, as it is earlier in the call graph. Further, note that the correct answer did not return the key value beyond functions b() and c() (i.e., not to a()), as a() does not need the key in its computation.

strops, get_key(), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# =========================== Array Function =================================

PROMPT_DEAD_CODE_ARRAY = """
Some functions are unused when the solution.py script is run. Remove any function that is not reachable from main() through the call graph.

For example, if you were given the following code block:
<example>
import sys
import numpy as np

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return b(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should remove the function `a()`, since it is not reached through `main()`, and leave `b()` as is:
<output>
import sys
import numpy as np

def b(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return b(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names that you do not remove (do not rename them). Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_PARAMETER_ARRAY = """
For any function in solution.py with the parameter mult, recursively propagate mult down the call graph by passing it to every function call used to compute the return expression. This will require adding mult to the parameter signatures of any called functions with a default value of `mult: float = default()`, and then recursively applying the same transformation to those functions. Continue propagating mult until reaching terminal functions whose return expressions directly compute a value `X` and do not call other functions in the file (apart from library functions). Only those terminal functions should apply the multiplier by returning mult * X; intermediate functions should NOT multiply their results by mult.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import default

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray, mult: float = default()) -> np.ndarray:
    c_val = c(val)
    return 2.0 * c_val

def c(val: np.ndarray) -> np.ndarray:
    return val + 0.5

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that a() is unchanged, and b() passes the `mult` parameter to c(). Then, you should modify the call signature of c() to accept `mult` with a default value of default(). Since c() is a terminal function, it will apply the multiplier to its original computation, returning `mult * (val + 0.5)`.
<output>
import sys
import numpy as np
from mylibrary import default

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray, mult: float = default()) -> np.ndarray:
    c_val = c(val, mult=mult)
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

default() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function. The code may change; do not assume that any default values will persist.
""".strip()

# -----------------------------------------------------------

PROMPT_ADD_RETURN_VALUE_ARRAY = """
In solution.py, external() previously returned a numpy array, but mylibrary now defines it as returning tuple[np.ndarray, str]. Update the code so the numpy array preserves the original computation, while the str is propagated upward through the call chain. Any function that directly or indirectly uses the result of external() should return tuple[np.ndarray, str]: the original computed value as the first element, and the propagated string as the second.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import external

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    return external(val)

def c(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)
    
if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that b() now returns a tuple of type tuple[np.ndarray, str] with the new values from external(). The string should propagate up the call graph recursively, modifying a() next, to preserve the original numpy array computation. c() will remain unchanged.
<output>
import sys
import numpy as np
from mylibrary import external

def a(val: np.ndarray) -> tuple[np.ndarray, str]:
    b_val, key = b(val)
    c_val = c(val)
    return b_val + c_val, key

def b(val: np.ndarray) -> tuple[np.ndarray, str]:
    return external(val)

def c(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

If a function receives multiple propagated strings, it may return any one of them, since they are guaranteed to be identical. external() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------

PROMPT_CACHE_FUNCTION_DIAMOND_ARRAY = """
In solution.py, some functions call slow(), which is expensive and deterministic, so it should be run as few times as possible. Refactor the code so that each repeated call to slow() is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the result in a temporary variable called `temp`, then pass that value down as an additional argument to the functions that use it (e.g., a(val: np.ndarray) -> a(val: np.ndarray, temp: float)). 

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block:
<example>
import sys
import numpy as np
from mylibrary import slow

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray) -> np.ndarray:
    c_val = c(val)
    d_val = d(val)
    return c_val + d_val

def c(val: np.ndarray) -> np.ndarray:
    return -4 * slow() + val

def d(val: np.ndarray) -> np.ndarray:
    e_val = e(val)
    return 2 * slow() + e_val

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that the calls to slow() in c() and d() are moved to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores the intermediate value of slow() and passes it down to the other functions:
<output>
import sys
import numpy as np
from mylibrary import slow

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray) -> np.ndarray:
    temp: float = slow()
    c_val = c(val, temp)
    d_val = d(val, temp)
    return c_val + d_val

def c(val: np.ndarray, temp: float) -> np.ndarray:
    return -4 * temp

def d(val: np.ndarray, temp: float) -> np.ndarray:
    e_val = e(val)
    return 2 * temp + e_val

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

Using global variables is BANNED. Adding them will cause your solution to be marked incorrect automatically, so you must follow our specified approach of moving the repeat computation to the right function and passing the result down to all necessary functions as an argument.

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have defined `temp` in the a() function, the correct answer is to define it in the b() function and pass it down to the other functions, as b() is the lowest common ancestor of c() and d(). The solution is NOT always to define the call to `slow()` in the functions called by `main()`. Further, note that the correct answer did not keep passing `temp` as an argument to the e() function, as the value is not used beyond c() and d().

All calls to slow() return the exact same value. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()

# -----------------------------------------------------------


PROMPT_EXTRACT_HELPER_DIAMOND_ARRAY = """
In solution.py, multiple functions independently call get_multiplier(val), which returns a multiplier for a given value. To reduce this duplication, refactor the code so the multiplier is defined once at the earliest shared downstream function reached by following calls from each of those functions, then return that multiplier back up to the functions that need it. Do not move the multiplier computation into a caller/ancestor of the duplicated functions.

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

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    d_val = d(val)
    e_val = e(val)
    return get_multiplier(val) * (d_val + e_val)

def c(val: np.ndarray) -> np.ndarray:
    d_val = d(val)
    return get_multiplier(val) * d_val

def d(val: np.ndarray) -> np.ndarray:
    e_val = e(val)
    return e_val

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

First, you should identify that b() and c() both call get_multiplier(val). Then, trace their calls downward toward their callees. The first shared downstream function is d(), so move get_multiplier(val) into d(), return it along with d()'s original result, and reuse that returned multiplier in b() and c().
<output>
import sys
import numpy as np
from mylibrary import get_multiplier

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    d_val, mult = d(val)
    e_val = e(val)
    return mult * (d_val + e_val)

def c(val: np.ndarray) -> np.ndarray:
    d_val, mult = d(val)
    return mult * d_val

def d(val: np.ndarray) -> tuple[np.ndarray, float]:
    e_val = e(val)
    return e_val, get_multiplier(val)

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

You must follow this procedure exactly; adding function parameters or returning values that diverge from what we specify will cause your solution to be marked incorrect automatically.

Note that while another valid solution could have moved the get_multiplier(val) call to the e() function, the correct answer is to move it to the d() function, as it is earlier in the call graph. Further, note that the correct answer did not return the multiplier value beyond functions b() and c() (i.e., not to a()), as a() does not need the multiplier in its computation.

get_multiplier() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip()