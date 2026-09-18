#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_PATH="${CONFIG_PATH:-${SCRIPT_DIR}/config.yaml}"

eval "$(uv run python "${ROOT_DIR}/experiments/_lib/load_config.py" "${CONFIG_PATH}")"

tasks_root="${tasks_root:-local_data/tasks}"
if [[ "${tasks_root}" = /* ]]; then
	output_dir="${tasks_root}"
else
	output_dir="${ROOT_DIR}/${tasks_root}"
fi

if [[ ${#allowed_transformations[@]} -eq 0 ]]; then
	allowed_transformations=(
		"rename_variables"
		"shuffle_lines"
		"multi_lines"
		"reorder"
		"logical_equiv"
	)
fi

if [[ ${#allowed_transformation_sets[@]} -eq 0 ]]; then
	allowed_transformation_sets=("${allowed_transformations[*]}")
fi

if [[ ${#allowed_perturbations[@]} -eq 0 ]]; then
	allowed_perturbations=(
		"swap_factor"
		"flip_sign"
		"change_coeff"
		"add_factor"
	)
fi

if [[ ${#allowed_perturbation_sets[@]} -eq 0 ]]; then
	allowed_perturbation_sets=("${allowed_perturbations[*]}")
fi

if [[ ${#merge_code_n_values[@]} -eq 0 ]]; then merge_code_n_values=("${n:-50}"); fi
if [[ ${#merge_code_d_values[@]} -eq 0 ]]; then merge_code_d_values=("${d:-5}"); fi
if [[ ${#merge_code_num_params_values[@]} -eq 0 ]]; then merge_code_num_params_values=("${num_params:-10}"); fi
if [[ ${#merge_code_min_block_values[@]} -eq 0 ]]; then merge_code_min_block_values=("${min_block:-3}"); fi
if [[ ${#merge_code_seed_values[@]} -eq 0 ]]; then merge_code_seed_values=("${seed:-42}"); fi
if [[ ${#merge_code_num_examples_values[@]} -eq 0 ]]; then merge_code_num_examples_values=("${num_examples:-10}"); fi
if [[ ${#merge_code_max_resample_attempts_values[@]} -eq 0 ]]; then merge_code_max_resample_attempts_values=("${max_resample_attempts:-100}"); fi

base_run_name="${run_name:-${experiment_name:-merge_code_sweep}}"

perturbation_set_name() {
	local set_text="$*"
	if [[ "${set_text}" == "swap_factor flip_sign change_coeff add_factor" ]]; then
		echo "all"
	elif [[ "$#" -eq 1 ]]; then
		echo "$1"
	elif [[ "$#" -eq 0 ]]; then
		echo "none"
	else
		local IFS=+
		echo "$*"
	fi
}

cd "${ROOT_DIR}"

for n_value in "${merge_code_n_values[@]}"; do
	for d_value in "${merge_code_d_values[@]}"; do
		for num_params_value in "${merge_code_num_params_values[@]}"; do
			for min_block_value in "${merge_code_min_block_values[@]}"; do
				for seed_value in "${merge_code_seed_values[@]}"; do
					for num_examples_value in "${merge_code_num_examples_values[@]}"; do
						for max_resample_attempts_value in "${merge_code_max_resample_attempts_values[@]}"; do
							for transformation_index in "${!allowed_transformation_sets[@]}"; do
								read -r -a transformation_set <<< "${allowed_transformation_sets[$transformation_index]}"
								for perturbation_index in "${!allowed_perturbation_sets[@]}"; do
									read -r -a perturbation_set <<< "${allowed_perturbation_sets[$perturbation_index]}"
									current_run_name="${base_run_name}_n=${n_value}_d=${d_value}_p=${num_params_value}_b=${min_block_value}_seed=${seed_value}_tf=${transformation_index}"
									if [[ "${perturbation_sweep_enabled}" == "true" ]]; then
										current_run_name+="_pt=$(perturbation_set_name "${perturbation_set[@]}")"
									fi

									args=(
										--n "${n_value}"
										--d "${d_value}"
										--num-params "${num_params_value}"
										--min-block "${min_block_value}"
										--seed "${seed_value}"
										--num-examples "${num_examples_value}"
										--max-resample-attempts "${max_resample_attempts_value}"
										--allowed-transformations "${transformation_set[@]}"
										--allowed-perturbations "${perturbation_set[@]}"
										--run-name "${current_run_name}"
										--output-dir "${output_dir}"
									)

									if [ "${overwrite}" = true ]; then
										args+=(--overwrite)
									fi

									if [ "${yes}" = true ]; then
										args+=(-y)
									fi

									echo "=== ${current_run_name} ==="
									uv run python -m data.tasks.merge_code.generate_data "${args[@]}"
								done
							done
						done
					done
				done
			done
		done
	done
done
