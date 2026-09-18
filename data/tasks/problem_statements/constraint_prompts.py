"""Prompts for constraint-based instruction-following tasks."""


ADD_PARAMETER_CONSTRAINTS_SECTION = """
In addition to the propagation above, each generated parameter carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all generated parameters are listed together in the "requirements" section below and may be shuffled rather than grouped by parameter. Apply these constraints inside every function that must take the named parameter as part of the propagation. For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the parameter named in that requirement. Do not apply a requirement inside main(), inside functions that do not take the named parameter, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the function has received the named parameter and before the named parameter is passed to another function or used in a terminal return computation. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named generated value. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named parameter and store it in the exact temporary variable named by the requirement. They do not update the parameter itself. For example, if a requirement says to set `mult1_temp` to `mult1 + 0.2`, write `mult1_temp = mult1 + 0.2`; continue passing and using `mult1`, not `mult1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


STRING_ADD_PARAMETER_CONSTRAINTS_SECTION = """
In addition to the propagation above, each prefix parameter carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all prefix parameters are listed together in the "requirements" section below and may be shuffled rather than grouped by parameter. Apply these constraints inside every function that must take the named prefix parameter as part of the propagation. For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the prefix parameter named in that requirement. Do not apply a requirement inside main(), inside functions that do not take the named prefix parameter, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the function has received the named prefix parameter and before the named prefix parameter is passed to another function or used in a terminal return computation. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named prefix parameter. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named prefix parameter and store it in the exact temporary variable named by the requirement. They do not update the prefix parameter itself. For example, if a requirement says to set `prefix1_temp` to `'a' + prefix1`, write `prefix1_temp = 'a' + prefix1`; continue passing and using `prefix1`, not `prefix1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


RETURN_VALUE_CONSTRAINTS_SECTION = """
In addition to the refactoring above, each generated return value key from external(N) carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all generated keys are listed together in the "requirements" section below and may be shuffled rather than grouped by key. Apply these constraints inside every function that must return the named key as part of the upward propagation except main(). For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the key named in that requirement. Do not apply a requirement inside main(), inside functions that do not return the named key, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the named key has been received or computed in the function and before the named key is returned in the tuple. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named generated key. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named key and store it in the exact temporary variable named by the requirement. They do not update the key itself. For example, if a requirement says to set `key1_temp` to `'a' + key1`, write `key1_temp = 'a' + key1`; continue returning `key1`, not `key1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


CACHE_FUNCTION_CONSTRAINTS_SECTION = """
In addition to the refactoring above, each generated cached value from slow(idx) carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all generated cached values are listed together in the "requirements" section below and may be shuffled rather than grouped by value. Apply these constraints inside every function that must define the named cached value or take it as a parameter as part of the refactoring. For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the cached value named in that requirement. Do not apply a requirement inside main(), inside functions that do not define or take the named cached value, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the named cached value has been received or computed in the function and before the named cached value is passed to another function or used in the function's computation. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named generated cached value. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named cached value and store it in the exact temporary variable named by the requirement. They do not update the cached value itself. For example, if a requirement says to set `slow1_temp` to `slow1 - 0.2`, write `slow1_temp = slow1 - 0.2`; continue passing and using `slow1`, not `slow1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


STRING_CACHE_FUNCTION_CONSTRAINTS_SECTION = """
In addition to the refactoring above, each generated cached string value from slow(idx) carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all generated cached string values are listed together in the "requirements" section below and may be shuffled rather than grouped by value. Apply these constraints inside every function that must define the named cached value or take it as a parameter as part of the refactoring. For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the cached value named in that requirement. Do not apply a requirement inside main(), inside functions that do not define or take the named cached value, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the named cached value has been received or computed in the function and before the named cached value is passed to another function or used in the function's computation. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named generated cached value. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named cached value and store it in the exact temporary variable named by the requirement. They do not update the cached value itself. For example, if a requirement says to set `slow1_temp` to `'a' + slow1`, write `slow1_temp = 'a' + slow1`; continue passing and using `slow1`, not `slow1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


EXTRACT_HELPER_CONSTRAINTS_SECTION = """
In addition to the refactoring above, each generated extracted multiplier from get_multiplier() carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all generated multipliers are listed together in the "requirements" section below and may be shuffled rather than grouped by multiplier. Apply these constraints inside every function that uses the named multiplier in its computation or returns it as part of the refactoring. For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the multiplier named in that requirement. Do not apply a requirement inside main(), inside functions that do not use or return the named multiplier, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the named multiplier has been received or computed in the function and before the named multiplier is used in a computation or returned upward in a tuple. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named generated multiplier. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named multiplier and store it in the exact temporary variable named by the requirement. They do not update the multiplier itself. For example, if a requirement says to set `mult1_temp` to `mult1 * 0.2`, write `mult1_temp = mult1 * 0.2`; continue using and returning `mult1`, not `mult1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


STRING_EXTRACT_HELPER_CONSTRAINTS_SECTION = """
In addition to the refactoring above, each generated extracted prefix from get_key() carries a set of CONSTRAINTS that are triggered by the NAME of the function they are applied in. The constraints for all generated prefixes are listed together in the "requirements" section below and may be shuffled rather than grouped by prefix. Apply these constraints inside every function that uses the named prefix in its computation or returns it as part of the refactoring. For each such function, check its name against every requirement; each requirement whose condition matches the function's name applies inside that function for the prefix named in that requirement. Do not apply a requirement inside main(), inside functions that do not use or return the named prefix, or inside functions whose names do not match that requirement's condition.

When several requirements match the same function, apply them in this fixed order within the function body:
    1. comments
    2. assert statements
    3. print statements
    4. temporary-variable assignments

Insert these constraint lines after the named prefix has been received or computed in the function and before the named prefix is used in a computation or returned upward in a tuple. Comment requirements should be written as real `#` comments on their own lines, exactly as specified, including the named generated prefix. Assert, print, and temporary-variable assignment requirements should be written as separate Python statements on their own lines.

Temporary-variable assignment requirements compute a value from the named prefix and store it in the exact temporary variable named by the requirement. They do not update the prefix itself. For example, if a requirement says to set `prefix1_temp` to `'a' + prefix1`, write `prefix1_temp = 'a' + prefix1`; continue using and returning `prefix1`, not `prefix1_temp`. If there are multiple matching requirements of the same kind, write each one as a separate line.
""".strip()


PROMPT_MULT_CONSTRAINTS = """
For any function in solution.py with the parameters mult1, mult2, ..., multN, recursively propagate these parameters down the call graph by passing them to every function call used to compute the return expression. This will require adding each parameter to the parameter signatures of any called functions with a default value of `default(idx)` based on the index idx of the parameter multIDX (for example `mult1: float = default(1)`), and then recursively applying the same transformation to those functions. Continue propagating the parameters until reaching terminal functions whose return expressions directly compute a numeric value `X` and do not call other functions in the file apart from library functions. Only those terminal functions should apply the multipliers by returning `mult1 * mult2 * ... * X`; intermediate functions should NOT multiply their results. The index identifies the default value of each mult variable, so preserve those indexes exactly when calling default(idx); do not replace indexed calls with unindexed calls, and do not swap the indexes between default() calls to mult parameters.

For example, if you were given the following code block (with two parameters mult1 and mult2):
<example>
import sys
from mylibrary import default

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float, mult1: float = default(1), mult2: float = default(2)) -> float:
    c_val = c(val)
    return 2.0 * c_val

def c(val: float) -> float:
    return val + 0.5

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify the code such that a() is unchanged, and b() passes mult1 and mult2 to c(). Then, modify c() to accept mult1 and mult2 with default values of default(1) and default(2). Since c() is a terminal function, it applies the multipliers to its original computation.
<output>
import sys
from mylibrary import default

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float, mult1: float = default(1), mult2: float = default(2)) -> float:
    c_val = c(val, mult1=mult1, mult2=mult2)
    return 2.0 * c_val

def c(val: float, mult1: float = default(1), mult2: float = default(2)) -> float:
    return mult1 * mult2 * (val + 0.5)

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

Do NOT modify functions that are upstream of the function that already has the mult parameters. In the example above, a() is unchanged.

default(idx) and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + ADD_PARAMETER_CONSTRAINTS_SECTION


PROMPT_ARRAY_MULT_CONSTRAINTS = """
For any function in solution.py with the parameters mult1, mult2, ..., multN, recursively propagate these parameters down the call graph by passing them to every function call used to compute the return expression. This will require adding each parameter to the parameter signatures of any called functions with a default value of `default(idx)` based on the index idx of the parameter multIDX (for example `mult1: float = default(1)`), and then recursively applying the same transformation to those functions. Continue propagating the parameters until reaching terminal functions whose return expressions directly compute a numpy array value `X` and do not call other functions in the file apart from library functions. Only those terminal functions should apply the multipliers by returning `mult1 * mult2 * ... * X`; intermediate functions should NOT multiply their results. The index identifies the default value of each mult variable, so preserve those indexes exactly when calling default(idx); do not replace indexed calls with unindexed calls, and do not swap the indexes between default() calls to mult parameters.

For example, if you were given the following code block (with two parameters mult1 and mult2):
<example>
import sys
import numpy as np
from mylibrary import default

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray, mult1: float = default(1), mult2: float = default(2)) -> np.ndarray:
    c_val = c(val)
    return 2.0 * c_val

def c(val: np.ndarray) -> np.ndarray:
    return val + 0.5

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify the code such that a() is unchanged, and b() passes mult1 and mult2 to c(). Then, modify c() to accept mult1 and mult2 with default values of default(1) and default(2). Since c() is a terminal function, it applies the multipliers to its original array computation.
<output>
import sys
import numpy as np
from mylibrary import default

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray, mult1: float = default(1), mult2: float = default(2)) -> np.ndarray:
    c_val = c(val, mult1=mult1, mult2=mult2)
    return 2.0 * c_val

def c(val: np.ndarray, mult1: float = default(1), mult2: float = default(2)) -> np.ndarray:
    return mult1 * mult2 * (val + 0.5)

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

Do NOT modify functions that are upstream of the function that already has the mult parameters. In the example above, a() is unchanged.

default(idx) and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + ADD_PARAMETER_CONSTRAINTS_SECTION


PROMPT_STRING_MULT_CONSTRAINTS = """
For any function in solution.py with the parameters prefix1, prefix2, ..., prefixN, recursively propagate these parameters down the call graph by passing them to every function call used to compute the return expression. This will require adding each parameter to the parameter signatures of any called functions with a default value of `default(idx)` based on the index idx of the parameter prefixIDX (for example `prefix1: str = default(1)`), and then recursively applying the same transformation to those functions. Continue propagating the parameters until reaching terminal functions whose return expressions directly compute a string value `X` and do not call other functions in the file apart from library functions. Only those terminal functions should apply the prefixes by returning `prefix1 + prefix2 + ... + X`; intermediate functions should NOT add prefixes to their results. The index identifies the default value of each prefix variable, so preserve those indexes exactly when calling default(idx); do not replace indexed calls with unindexed calls, and do not swap the indexes between default() calls to prefix parameters.

For example, if you were given the following code block (with two parameters prefix1 and prefix2):
<example>
import sys
import strops
from mylibrary import default

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str, prefix1: str = default(1), prefix2: str = default(2)) -> str:
    c_val = c(val)
    return strops.reverse(c_val)

def c(val: str) -> str:
    return strops.interleave(val, "abc")

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify the code such that a() is unchanged, and b() passes prefix1 and prefix2 to c(). Then, modify c() to accept prefix1 and prefix2 with default values of default(1) and default(2). Since c() is a terminal function, it applies the prefixes to its original string computation.
<output>
import sys
import strops
from mylibrary import default

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str, prefix1: str = default(1), prefix2: str = default(2)) -> str:
    c_val = c(val, prefix1=prefix1, prefix2=prefix2)
    return strops.reverse(c_val)

def c(val: str, prefix1: str = default(1), prefix2: str = default(2)) -> str:
    return prefix1 + prefix2 + strops.interleave(val, "abc")

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

Do NOT modify functions that are upstream of the function that already has the prefix parameters. In the example above, a() is unchanged.

strops, default(idx), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + STRING_ADD_PARAMETER_CONSTRAINTS_SECTION


PROMPT_RETURN_VALUE_CONSTRAINTS = """
In solution.py, some functions compute generated string keys inline by calling external(N), where external(N) returns N generated string keys. Those functions currently keep returning only their original float result. Update the code so the original float computation is preserved, while the generated string keys key1, key2, ..., keyN are returned by the functions that compute them and propagated upward through the call chain. Any function that directly or indirectly uses generated keys from external(N) should return a tuple whose first element is the original computed float value, followed by all generated keys in order: tuple[float, str, str, ...].

For example, if you were given the following code block (where external(2) returns two keys key1 and key2):
<example>
import sys
from mylibrary import external

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    key1, key2 = external(2)
    return val

def c(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should modify b() to return tuple[float, str, str], then propagate that tuple shape up through a() while preserving a()'s original float computation. c() remains unchanged.
<output>
import sys
from mylibrary import external

def a(val: float) -> tuple[float, str, str]:
    b_val, key1, key2 = b(val)
    c_val = c(val)
    return b_val + c_val, key1, key2

def b(val: float) -> tuple[float, str, str]:
    key1, key2 = external(2)
    return val, key1, key2

def c(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

If a function receives propagated key sets from multiple child calls, keep the keys from the FIRST such call and discard the keys from every subsequent child call by unpacking them into `_`. Do not mix keys across child calls and do not keep the keys from a later call.

external(N) and mylibrary are undefined and will be defined later; do not try to define them or change the call signature of external(N). You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + RETURN_VALUE_CONSTRAINTS_SECTION


PROMPT_ARRAY_RETURN_VALUE_CONSTRAINTS = """
In solution.py, some functions compute generated string keys inline by calling external(N), where external(N) returns N generated string keys. Those functions currently keep returning only their original numpy array result. Update the code so the original numpy array computation is preserved, while the generated string keys key1, key2, ..., keyN are returned by the functions that compute them and propagated upward through the call chain. Any function that directly or indirectly uses generated keys from external(N) should return a tuple whose first element is the original computed numpy array value, followed by all generated keys in order: tuple[np.ndarray, str, str, ...].

For example, if you were given the following code block (where external(2) returns two keys key1 and key2):
<example>
import sys
import numpy as np
from mylibrary import external

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    key1, key2 = external(2)
    return val

def c(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should modify b() to return tuple[np.ndarray, str, str], then propagate that tuple shape up through a() while preserving a()'s original array computation. c() remains unchanged.
<output>
import sys
import numpy as np
from mylibrary import external

def a(val: np.ndarray) -> tuple[np.ndarray, str, str]:
    b_val, key1, key2 = b(val)
    c_val = c(val)
    return b_val + c_val, key1, key2

def b(val: np.ndarray) -> tuple[np.ndarray, str, str]:
    key1, key2 = external(2)
    return val, key1, key2

def c(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

If a function receives propagated key sets from multiple child calls, keep the keys from the FIRST such call and discard the keys from every subsequent child call by unpacking them into `_`. Do not mix keys across child calls and do not keep the keys from a later call.

external(N) and mylibrary are undefined and will be defined later; do not try to define them or change the call signature of external(N). You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + RETURN_VALUE_CONSTRAINTS_SECTION


PROMPT_STRING_RETURN_VALUE_CONSTRAINTS = """
In solution.py, some functions compute generated string keys inline by calling external(N), where external(N) returns N generated string keys. Those functions currently keep returning only their original string result. Update the code so the original string computation is preserved, while the generated string keys key1, key2, ..., keyN are returned by the functions that compute them and propagated upward through the call chain. Any function that directly or indirectly uses generated keys from external(N) should return a tuple whose first element is the original computed string value, followed by all generated keys in order: tuple[str, str, str, ...].

For example, if you were given the following code block (where external(2) returns two keys key1 and key2):
<example>
import sys
import strops
from mylibrary import external

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    key1, key2 = external(2)
    return val

def c(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should modify b() to return tuple[str, str, str], then propagate that tuple shape up through a() while preserving a()'s original string computation. c() remains unchanged.
<output>
import sys
import strops
from mylibrary import external

def a(val: str) -> tuple[str, str, str]:
    b_val, key1, key2 = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val), key1, key2

def b(val: str) -> tuple[str, str, str]:
    key1, key2 = external(2)
    return val, key1, key2

def c(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

If a function receives propagated key sets from multiple child calls, keep the keys from the FIRST such call and discard the keys from every subsequent child call by unpacking them into `_`. Do not mix keys across child calls and do not keep the keys from a later call.

strops, external(N), and mylibrary are undefined and will be defined later; do not try to define them or change the call signature of external(N). You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + RETURN_VALUE_CONSTRAINTS_SECTION


PROMPT_CACHE_FUNCTION_CONSTRAINTS = """
In solution.py, some functions call slow(1), slow(2), ..., slow(N), which are expensive and deterministic numeric computations, so each indexed call should be run as few times as possible. Refactor the code so that each repeated indexed call is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the results in generated numeric values named slow1, slow2, ..., slowN, then pass those values down as additional arguments to the functions that use them. The index identifies which generated slow value is being computed, so preserve those indexes exactly when moving or reusing slow() results; do not replace indexed calls with unindexed calls, and do not swap the indexes between generated slow values.

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block (with two generated slow values slow1 and slow2):
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
    return -4 * slow(1) + slow(2)

def d(val: float) -> float:
    e_val = e(val)
    return 2 * slow(1) + slow(2) + e_val

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</example>

You should move the calls to slow(1) and slow(2) in c() and d() to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores slow1 and slow2 and passes them down to the functions that use them.
<output>
import sys
from mylibrary import slow

def a(val: float) -> float:
    b_val = b(val)
    return b_val

def b(val: float) -> float:
    slow1: float = slow(1)
    slow2: float = slow(2)
    c_val = c(val, slow1=slow1, slow2=slow2)
    d_val = d(val, slow1=slow1, slow2=slow2)
    return c_val + d_val

def c(val: float, slow1: float = 0.0, slow2: float = 0.0) -> float:
    return -4 * slow1 + slow2

def d(val: float, slow1: float = 0.0, slow2: float = 0.0) -> float:
    e_val = e(val)
    return 2 * slow1 + slow2 + e_val

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

Using global variables is BANNED. Note that while another valid solution could have defined slow1 and slow2 in a(), the correct answer in the example is b(), the lowest common ancestor. Do not keep passing slow values to functions that do not use them.

All calls to slow(idx) are deterministic for a given index idx. slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + CACHE_FUNCTION_CONSTRAINTS_SECTION


PROMPT_ARRAY_CACHE_FUNCTION_CONSTRAINTS = """
In solution.py, some functions call slow(1), slow(2), ..., slow(N), which are expensive and deterministic numeric computations, so each indexed call should be run as few times as possible. Refactor the code so that each repeated indexed call is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the results in generated numeric values named slow1, slow2, ..., slowN, then pass those values down as additional arguments to the functions that use them. The index identifies which generated slow value is being computed, so preserve those indexes exactly when moving or reusing slow() results; do not replace indexed calls with unindexed calls, and do not swap the indexes between generated slow values.

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block (with two generated slow values slow1 and slow2):
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
    return -4 * slow(1) * val + slow(2)

def d(val: np.ndarray) -> np.ndarray:
    e_val = e(val)
    return 2 * slow(1) * val + slow(2) + e_val

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</example>

You should move the calls to slow(1) and slow(2) in c() and d() to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores slow1 and slow2 and passes them down to the functions that use them.
<output>
import sys
import numpy as np
from mylibrary import slow

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    return b_val

def b(val: np.ndarray) -> np.ndarray:
    slow1: float = slow(1)
    slow2: float = slow(2)
    c_val = c(val, slow1=slow1, slow2=slow2)
    d_val = d(val, slow1=slow1, slow2=slow2)
    return c_val + d_val

def c(val: np.ndarray, slow1: float = 0.0, slow2: float = 0.0) -> np.ndarray:
    return -4 * slow1 * val + slow2

def d(val: np.ndarray, slow1: float = 0.0, slow2: float = 0.0) -> np.ndarray:
    e_val = e(val)
    return 2 * slow1 * val + slow2 + e_val

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

Using global variables is BANNED. Note that while another valid solution could have defined slow1 and slow2 in a(), the correct answer in the example is b(), the lowest common ancestor. Do not keep passing slow values to functions that do not use them.

slow() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + CACHE_FUNCTION_CONSTRAINTS_SECTION


PROMPT_STRING_CACHE_FUNCTION_CONSTRAINTS = """
In solution.py, some functions call slow(1), slow(2), ..., slow(N), which are expensive and deterministic string computations, so each indexed call should be run as few times as possible. Refactor the code so that each repeated indexed call is performed exactly once at the lowest shared caller (i.e., lowest common ancestor) of the functions that need it. Store the results in generated string values named slow1, slow2, ..., slowN, then pass those values down as additional arguments to the functions that use them. The index identifies which generated slow value is being computed, so preserve those indexes exactly when moving or reusing slow() results; do not replace indexed calls with unindexed calls, and do not swap the indexes between generated slow values.

A function `f()` is the lowest common ancestor of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, either `f()` is `g_i()`, or `f()` calls `g_i()` directly or indirectly through one or more intermediate functions.
2. There is no function `h()` such that `f()` calls `h()` directly or indirectly, and `h()` also calls every `g_i()` directly or indirectly.
In other words, `f()` is the deepest function that still contains, beneath it, all of `g_1(), ..., g_n()`.

For example, if you were given the following code block (with two generated slow values slow1 and slow2):
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
    return strops.reverse(slow(1)) + slow(2)

def d(val: str) -> str:
    e_val = e(val)
    return slow(1) + slow(2) + e_val

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</example>

You should move the calls to slow(1) and slow(2) in c() and d() to b(), as b() is the lowest common ancestor of c() and d(). Then, b() stores slow1 and slow2 and passes them down to the functions that use them.
<output>
import sys
import strops
from mylibrary import slow

def a(val: str) -> str:
    b_val = b(val)
    return b_val

def b(val: str) -> str:
    slow1: str = slow(1)
    slow2: str = slow(2)
    c_val = c(val, slow1=slow1, slow2=slow2)
    d_val = d(val, slow1=slow1, slow2=slow2)
    return strops.interleave(c_val, d_val)

def c(val: str, slow1: str = "", slow2: str = "") -> str:
    return strops.reverse(slow1) + slow2

def d(val: str, slow1: str = "", slow2: str = "") -> str:
    e_val = e(val)
    return slow1 + slow2 + e_val

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

Using global variables is BANNED. Note that while another valid solution could have defined slow1 and slow2 in a(), the correct answer in the example is b(), the lowest common ancestor. Do not keep passing slow values to functions that do not use them.

strops, slow(), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + STRING_CACHE_FUNCTION_CONSTRAINTS_SECTION


PROMPT_EXTRACT_HELPER_CONSTRAINTS = """
In solution.py, multiple functions independently call get_multiplier(val, 1), get_multiplier(val, 2), ..., get_multiplier(val, N), which return multipliers for a given value val and index idx. To reduce this duplication, refactor the code so the generated multipliers mult1, mult2, ..., multN are defined once at the earliest shared downstream function reached by following calls from each of those functions, then return those multipliers back up to the functions that need them. Do not move the multiplier computations into a caller/ancestor of the duplicated functions. The index identifies which generated multiplier is being computed, so preserve those indexes exactly when moving or reusing get_multiplier() results; do not replace indexed calls with unindexed calls, and do not swap the indexes between generated multipliers.

A function `f()` is the nearest shared downstream function of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, `g_i()` calls `f()` directly or indirectly through one or more intermediate functions.
2. There is no other function `h()` such that every `g_i()` calls `h()` directly or indirectly, and `h()` calls `f()` directly or indirectly.
In other words, `f()` is the earliest function reached in common when tracing calls downward from all of `g_1(), ..., g_n()`.

For example, if you were given the following code block (with two generated multipliers mult1 and mult2):
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
    mult1 = get_multiplier(val, 1)
    mult2 = get_multiplier(val, 2)
    return mult1 * mult2 * (d_val + e_val)

def c(val: float) -> float:
    d_val = d(val)
    mult1 = get_multiplier(val, 1)
    mult2 = get_multiplier(val, 2)
    return mult1 * mult2 * d_val

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

The first shared downstream function is d(), so move both get_multiplier() calls into d(), return both generated multipliers along with d()'s original result, and reuse those returned multipliers in b() and c().
<output>
import sys
from mylibrary import get_multiplier

def a(val: float) -> float:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: float) -> float:
    d_val, mult1, mult2 = d(val)
    e_val = e(val)
    return mult1 * mult2 * (d_val + e_val)

def c(val: float) -> float:
    d_val, mult1, mult2 = d(val)
    return mult1 * mult2 * d_val

def d(val: float) -> tuple[float, float, float]:
    mult1: float = get_multiplier(val, 1)
    mult2: float = get_multiplier(val, 2)
    e_val = e(val)
    return e_val, mult1, mult2

def e(val: float) -> float:
    return val

def main(val: float):
    return a(val)

if __name__ == '__main__':
    main(float(sys.argv[1]))
</output>

Note that while another valid solution could have moved the get_multiplier() calls to e(), the correct answer in the example is d(), as it is earlier in the call graph. Do not return multiplier values beyond the functions that need them in their computation.

get_multiplier() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + EXTRACT_HELPER_CONSTRAINTS_SECTION


PROMPT_ARRAY_EXTRACT_HELPER_CONSTRAINTS = """
In solution.py, multiple functions independently call get_multiplier(val, 1), get_multiplier(val, 2), ..., get_multiplier(val, N), which return multipliers for a given numpy array val and index idx. To reduce this duplication, refactor the code so the generated multipliers mult1, mult2, ..., multN are defined once at the earliest shared downstream function reached by following calls from each of those functions, then return those multipliers back up to the functions that need them. Do not move the multiplier computations into a caller/ancestor of the duplicated functions. The index identifies which generated multiplier is being computed, so preserve those indexes exactly when moving or reusing get_multiplier() results; do not replace indexed calls with unindexed calls, and do not swap the indexes between generated multipliers.

A function `f()` is the nearest shared downstream function of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, `g_i()` calls `f()` directly or indirectly through one or more intermediate functions.
2. There is no other function `h()` such that every `g_i()` calls `h()` directly or indirectly, and `h()` calls `f()` directly or indirectly.
In other words, `f()` is the earliest function reached in common when tracing calls downward from all of `g_1(), ..., g_n()`.

For example, if you were given the following code block (with two generated multipliers mult1 and mult2):
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
    mult1 = get_multiplier(val, 1)
    mult2 = get_multiplier(val, 2)
    return mult1 * mult2 * (d_val + e_val)

def c(val: np.ndarray) -> np.ndarray:
    d_val = d(val)
    mult1 = get_multiplier(val, 1)
    mult2 = get_multiplier(val, 2)
    return mult1 * mult2 * d_val

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

The first shared downstream function is d(), so move both get_multiplier() calls into d(), return both generated multipliers along with d()'s original result, and reuse those returned multipliers in b() and c().
<output>
import sys
import numpy as np
from mylibrary import get_multiplier

def a(val: np.ndarray) -> np.ndarray:
    b_val = b(val)
    c_val = c(val)
    return b_val + c_val

def b(val: np.ndarray) -> np.ndarray:
    d_val, mult1, mult2 = d(val)
    e_val = e(val)
    return mult1 * mult2 * (d_val + e_val)

def c(val: np.ndarray) -> np.ndarray:
    d_val, mult1, mult2 = d(val)
    return mult1 * mult2 * d_val

def d(val: np.ndarray) -> tuple[np.ndarray, float, float]:
    mult1: float = get_multiplier(val, 1)
    mult2: float = get_multiplier(val, 2)
    e_val = e(val)
    return e_val, mult1, mult2

def e(val: np.ndarray) -> np.ndarray:
    return val

def main(val: np.ndarray):
    return a(val)

if __name__ == '__main__':
    main(np.array(eval(sys.argv[1])))
</output>

Note that while another valid solution could have moved the get_multiplier() calls to e(), the correct answer in the example is d(), as it is earlier in the call graph. Do not return multiplier values beyond the functions that need them in their computation.

get_multiplier() and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + EXTRACT_HELPER_CONSTRAINTS_SECTION


PROMPT_STRING_EXTRACT_HELPER_CONSTRAINTS = """
In solution.py, multiple functions independently call get_key(val, 1), get_key(val, 2), ..., get_key(val, N), which return string prefixes for a given value val and index idx. To reduce this duplication, refactor the code so the generated prefixes prefix1, prefix2, ..., prefixN are defined once at the earliest shared downstream function reached by following calls from each of those functions, then return those prefixes back up to the functions that need them. Do not move the prefix computations into a caller/ancestor of the duplicated functions. The index identifies which generated prefix is being computed, so preserve those indexes exactly when moving or reusing get_key() results; do not replace indexed calls with unindexed calls, and do not swap the indexes between generated prefixes.

A function `f()` is the nearest shared downstream function of functions `g_1(), ..., g_n()` if and only if:
1. For every `g_i()`, `g_i()` calls `f()` directly or indirectly through one or more intermediate functions.
2. There is no other function `h()` such that every `g_i()` calls `h()` directly or indirectly, and `h()` calls `f()` directly or indirectly.
In other words, `f()` is the earliest function reached in common when tracing calls downward from all of `g_1(), ..., g_n()`.

For example, if you were given the following code block (with two generated prefixes prefix1 and prefix2):
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
    prefix1 = get_key(val, 1)
    prefix2 = get_key(val, 2)
    return prefix1 + prefix2 + strops.zip_chars(d_val, e_val)

def c(val: str) -> str:
    d_val = d(val)
    prefix1 = get_key(val, 1)
    prefix2 = get_key(val, 2)
    return strops.swap_halves(prefix1 + prefix2, d_val)

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

The first shared downstream function is d(), so move both get_key() calls into d(), return both generated prefixes along with d()'s original result, and reuse those returned prefixes in b() and c().
<output>
import sys
import strops
from mylibrary import get_key

def a(val: str) -> str:
    b_val = b(val)
    c_val = c(val)
    return strops.interleave(b_val, c_val)

def b(val: str) -> str:
    d_val, prefix1, prefix2 = d(val)
    e_val = e(val)
    return prefix1 + prefix2 + strops.zip_chars(d_val, e_val)

def c(val: str) -> str:
    d_val, prefix1, prefix2 = d(val)
    return strops.swap_halves(prefix1 + prefix2, d_val)

def d(val: str) -> tuple[str, str, str]:
    prefix1: str = get_key(val, 1)
    prefix2: str = get_key(val, 2)
    e_val = e(val)
    return e_val, prefix1, prefix2

def e(val: str) -> str:
    return val

def main(val: str):
    return a(val)

if __name__ == '__main__':
    main(str(sys.argv[1]))
</output>

Note that while another valid solution could have moved the get_key() calls to e(), the correct answer in the example is d(), as it is earlier in the call graph. Do not return prefix values beyond the functions that need them in their computation.

strops, get_key(), and mylibrary are undefined and will be defined later; do not try to define them. You CANNOT add new functions, imports, or variables outside of the provided functions. You MUST preserve all function names (do not rename them). You may define variables within functions. Do not change the "__main__" block or main() function.
""".strip() + "\n\n" + STRING_EXTRACT_HELPER_CONSTRAINTS_SECTION
