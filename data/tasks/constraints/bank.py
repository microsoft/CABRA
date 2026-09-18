# Random values / bounds
rand_values = [round(0.1 * i, 1) for i in range(1, 11)]
lower_bound_values = [-50, -75, -100, -125, -150, -175, -200]
upper_bound_values = [50, 75, 100, 125, 150, 175, 200]
not_values = [-40, -30, -20, -10, 10, 20, 30, 40]

rand_values_str = [repr(str(i)) for i in range(10)]
lower_bound_values_str = ["'!'", "'#'", "'$'", "'%'", "'&'", "'+'", "','"]
upper_bound_values_str = ["':'", "';'", "'<'", "'='", "'>'", "'?'", "'@'"]
not_values_str = ["'A'", "'B'", "'C'", "'D'", "'E'", "'F'", "'G'"]


# Semi-realistic prefixes/suffixes you might see in print() statements
print_prefixes = [
    "Value: ",
    "Printing: ",
    "Out: ",
    "Result: ",
    "Output: ",
    "Debug: ",
    "Log: ",
    "Info: ",
    "Trace: ",
    "mult = ",
    "current value -> ",
    "[mult] ",
    ">> ",
    "computed ",
    "checkpoint: ",
    "status: ",
    "got ",
    "now: ",
]
print_suffixes = [
    " (done)",
    " <- value",
    " [end]",
    " ...",
    " | logged",
    " #checkpoint",
    " -- mult",
    " (computed)",
    " ;",
    " ok",
    " <eol>",
    " //trace",
    " ->",
    " units",
    " (float)",
    " !!",
]

# Semi-realistic comments you might see in functions()
comment_values = [
    "TODO",
    "NOTE",
    "checkpoint",
    "trace",
    "debug",
    "handoff",
    "pass-through",
    "preserve",
    "review",
    "guard",
    "computed",
    "forwarded",
    "state",
    "local",
    "marker",
    "verify",
]

# Semi-realistic temporary variable names
temp_name_templates = [
    "{var}_temp",
    "temp_{var}",
    "{var}_copy",
    "copy_{var}",
    "{var}_snapshot",
    "snapshot_{var}",
    "{var}_stash",
    "stored_{var}",
    "{var}_current",
    "current_{var}",
    "{var}_local",
    "local_{var}",
    "{var}_checkpoint",
    "checkpoint_{var}",
    "{var}_dupe",
    "dupe_{var}",
]

# The actual list of sample rules that we use
add_parameter_templates_float = {
    "add_number": [
        {
            "implementation": "{new_var}={var}+{rand}",
            "descriptions": [
                "set {new_var} to {var}+{rand} on its own line.",
                "save {var}+{rand} in the temporary variable {new_var} without changing {var}.",
                "compute {var}+{rand} into {new_var} on a separate line.",
                "add {rand} to {var} and store the result in {new_var} without updating {var}.",
                "create the temporary variable {new_var} with the value {var}+{rand}.",
            ]
        }
    ],
    "subtract_number": [
        {
            "implementation": "{new_var}={var}-{rand}",
            "descriptions": [
                "set {new_var} to {var}-{rand} on its own line.",
                "save {var}-{rand} in the temporary variable {new_var} without changing {var}.",
                "compute {var}-{rand} into {new_var} on a separate line.",
                "subtract {rand} from {var} and store the result in {new_var} without updating {var}.",
                "create the temporary variable {new_var} with the value {var}-{rand}.",
            ]
        }
    ],
    "multiply_number": [
        {
            "implementation": "{new_var}={var}*{rand}",
            "descriptions": [
                "set {new_var} to {var}*{rand} on its own line.",
                "save {var}*{rand} in the temporary variable {new_var} without changing {var}.",
                "compute {var}*{rand} into {new_var} on a separate line.",
                "multiply {var} by {rand} and store the result in {new_var} without updating {var}.",
                "create the temporary variable {new_var} with the value {var}*{rand}.",
            ]
        }
    ],
    "divide_number": [
        {
            "implementation": "{new_var}={var}/{rand}",
            "descriptions": [
                "set {new_var} to {var}/{rand} on its own line.",
                "save {var} divided by {rand} in the temporary variable {new_var} without changing {var}.",
                "compute {var}/{rand} into {new_var} on a separate line.",
                "compute {var} divided by {rand} and store the result in {new_var} without updating {var}.",
                "create the temporary variable {new_var} with the value {var}/{rand}.",
            ]
        }
    ],
    "assert_not": [  # say you need to check some condition. assert that it's not equal to some random value
        {
            "implementation": "assert {var} != {rand}",
            "descriptions": [
                "assert() that {var} is not equal to {rand}.",
                "check that {var} never equals {rand} via an assertion statement.",
                "assert() that {var} differs from {rand}.",
                "guard the call by running assert({var} != {rand}).",
                "make sure {var} doesn't equal {rand} via an assert() statement.",
            ]
        }
    ],
    "assert_upper_bound": [  # always assert mult is below a rand value before calling other functions
        {
            "implementation": "assert {var} < {rand}",
            "descriptions": [
                "assert() that {var} is below {rand}.",
                "check that {var} is smaller than {rand} via an assertion statement.",
                "assert() that {var} is less than {rand}.",
                "guard the call by running assert({var} < {rand}).",
                "make sure {var} is strictly less than {rand} via an assert() statement.",
            ]
        }
    ],
    "assert_lower_bound": [  # always assert mult is above a rand value before calling other functions
        {
            "implementation": "assert {var} > {rand}",
            "descriptions": [
                "assert that {var} is above {rand}.",
                "check that {var} is larger than {rand} via an assertion statement.",
                "assert() that {var} is greater than {rand}.",
                "guard the call by running assert({var} > {rand}).",
                "make sure {var} is strictly greater than {rand} via an assert() statement.",
            ]
        }
    ],
    "print_prefix": [  # print an f-string with the prefix before {var} before calling other functions
        {
            "implementation": "print(f'{prefix}{{{var}}}')",
            "descriptions": [
                "print {var} prefixed with the string '{prefix}' in an fstring.",
                "print the prefix '{prefix}' concatenated with the suffix {var} via fstring.",
                "output the string '{prefix}' followed by {var} with an f-string.",
                "prepend '{prefix}' to {var} and print the result in an fstring.",
                "print '{prefix}' joined with {var} as a prefix in f string format.",
            ]
        }
    ],
    "print_suffix": [  # same w suffix, as an f-string
        {
            "implementation": "print(f'{{{var}}}{suffix}')",
            "descriptions": [
                "print {var} followed by the suffix string '{suffix}' in an fstring.",
                "print the prefix {var} concatenated with the suffix '{suffix}' via fstring.",
                "output {var} followed by the string '{suffix}' with an f-string.",
                "use an f-string to append '{suffix}' to {var} and print the result.",
                "print {var} joined with '{suffix}' as a suffix in f string format.",
            ]
        }
    ],
    "add_comment": [  # add an inert sampled comment before calling other functions
        {
            "implementation": "'# {rand}: {var}'",
            "descriptions": [
                "add the exact comment '# {rand}: {var}' to the function.",
                "include the verbatim comment '# {rand}: {var}'.",
                "place the exact comment '# {rand}: {var}' in the function body.",
                "write '# {rand}: {var}' exactly as a comment.",
                "add the comment '# {rand}: {var}' in the function.",
            ]
        }
    ]
}

add_parameter_templates_str = {
    "add_character_prefix": [
        {
            "implementation": "{new_var}={rand}+{var}",
            "descriptions": [
                "set {new_var} to {rand}+{var} on its own line.",
                "save {rand}+{var} in the temporary variable {new_var} without changing {var}.",
                "compute {rand}+{var} into {new_var} on a separate line, leaving {var} unchanged.",
                "prefix {var} with {rand} and store the result in {new_var}, without updating {var}.",
                "create the temporary variable {new_var} with the value {rand}+{var}.",
            ]
        }
    ],
    "add_character_suffix": [
        {
            "implementation": "{new_var}={var}+{rand}",
            "descriptions": [
                "set {new_var} to {var}+{rand} on its own line.",
                "save {var}+{rand} in the temporary variable {new_var} without changing {var}.",
                "compute {var}+{rand} into {new_var} on a separate line, leaving {var} unchanged.",
                "suffix {var} with {rand} and store the result in {new_var}, without updating {var}.",
                "create the temporary variable {new_var} with the value {var}+{rand}.",
            ]
        }
    ],
    "replace_character": [
        {
            "implementation": "{new_var}={var}.replace({rand}, {rand2})",
            "descriptions": [
                "set {new_var} to {var}.replace({rand}, {rand2}) on its own line.",
                "save {var}.replace({rand}, {rand2}) in the temporary variable {new_var} without changing {var}.",
                "compute {var}.replace({rand}, {rand2}) into {new_var} on a separate line, leaving {var} unchanged.",
                "replace {rand} with {rand2} in {var} and store the result in {new_var}, without updating {var}.",
                "create the temporary variable {new_var} with the value {var}.replace({rand}, {rand2}).",
            ]
        }
    ],
    "sandwich": [
        {
            "implementation": "{new_var}={rand}+{var}+{rand2}",
            "descriptions": [
                "set {new_var} to {rand}+{var}+{rand2} on its own line.",
                "save {rand}+{var}+{rand2} in the temporary variable {new_var} without changing {var}.",
                "compute {rand}+{var}+{rand2} into {new_var} on a separate line, leaving {var} unchanged.",
                "implement {rand}+{var}+{rand2} and store the result in {new_var}, without updating {var}.",
                "create the temporary variable {new_var} with the value {rand}+{var}+{rand2}.",
            ]
        }
    ],

    "assert_not": add_parameter_templates_float["assert_not"],
    "assert_upper_bound": add_parameter_templates_float["assert_upper_bound"],
    "assert_lower_bound": add_parameter_templates_float["assert_lower_bound"],
    "print_prefix": add_parameter_templates_float["print_prefix"],
    "print_suffix": add_parameter_templates_float["print_suffix"],
    "add_comment": add_parameter_templates_float["add_comment"]
}

return_value_templates_str = add_parameter_templates_str

cache_slow_templates_float = add_parameter_templates_float
cache_slow_templates_str = add_parameter_templates_str

extract_helper_templates_mult = add_parameter_templates_float
extract_helper_templates_str = add_parameter_templates_str

template_banks = {
    "add_parameter_float": add_parameter_templates_float,
    "add_parameter_str": add_parameter_templates_str,
    "return_value_str": return_value_templates_str,
    "cache_slow_float": cache_slow_templates_float,
    "cache_slow_str": cache_slow_templates_str,
    "extract_helper_mult": extract_helper_templates_mult,
    "extract_helper_str": extract_helper_templates_str,
}