import argparse
import asyncio
import random
from pathlib import Path

from tqdm import tqdm

from data.tasks.task import TaskType
from data.tasks.task_loader import TaskLoader
from model.agents import AgentFactory, AgentKind, Codebase
from model.response_cache import ResponseCache
import time

SOLUTION_FILENAME = "solution.py"
MAX_CONSECUTIVE_FAILURES = 5

def _task_codebase(task) -> Codebase:
    if isinstance(task.starter_code, dict):
        return task.starter_code
    return {SOLUTION_FILENAME: task.starter_code}


def _parse_kwargs(pairs: list[str]) -> dict:
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"--agent-kwargs entries must be key=value, got: {p}")
        k, v = p.split("=", 1)
        out[k] = v
    return out


async def run_eval(
    tasks_root: Path,
    task_set_names: list[str],
    task_types: list[TaskType],
    agent_kind: AgentKind,
    agent_kwargs: dict,
    response_dir: Path,
    run_names: list[str],
    limit: int | None,
    n_parallel: int = 1,
    overwrite: bool = False,
    yes: bool = False,
    retry_errors: bool = False,
) -> None:
    agent = AgentFactory.create(agent_kind, **agent_kwargs)

    if overwrite:
        existing = [
            response_dir / run_name / task_set_name / tt.value / f"{agent.name}.jsonl"
            for run_name in run_names
            for task_set_name in task_set_names
            for tt in task_types
        ]
        existing = [p for p in existing if p.exists()]
        if existing:
            print(f"Overwrite will delete {len(existing)} existing result file(s):")
            for p in existing:
                print(f"  {p}")
            if not yes:
                response = input("Proceed? [y/N]: ")
                if response.lower() != "y":
                    print("Aborting.")
                    return
            for p in existing:
                p.unlink()

    all_tasks = []
    total_combos = len(run_names) * len(task_set_names) * len(task_types)
    combo_idx = 0

    for run_name in run_names:
        task_dir = tasks_root / run_name
        for task_set_name in task_set_names:
            for task_type in task_types:
                combo_idx += 1
                task_json_path = task_dir / task_set_name / f"{task_type.value}.json"
                if not task_json_path.exists():
                    print(f"[skip] {task_json_path} does not exist")
                    continue

                out_path = response_dir / run_name / task_set_name / task_type.value / f"{agent.name}.jsonl"
                cache = ResponseCache(out_path)
                cache.load(retry_errors=retry_errors)

                count = 0
                for _, task in TaskLoader.eval_task_inputs(
                    str(task_json_path), task_set_name, [task_type],
                    task_type_index=combo_idx, total_task_types=total_combos,
                    show_progress=False,
                ):
                    if limit is not None and count >= limit:
                        break
                    count += 1
                    if cache.should_skip(task.name, task.dag_id):
                        continue
                    all_tasks.append((task, cache, task_type))

    if not all_tasks:
        print("[done] nothing to run")
        return

    semaphore = asyncio.Semaphore(n_parallel)
    write_lock = asyncio.Lock()
    failures = 0
    consecutive_failures = 0
    abort = False
    pbar = tqdm(total=len(all_tasks), desc=f"running ({len(all_tasks)} tasks)")

    async def run_task(task, cache, task_type):
        nonlocal failures, consecutive_failures, abort
        if abort:
            return
        async with semaphore:
            if abort:
                return
            await asyncio.sleep(random.uniform(0, 5))
            codebase = _task_codebase(task)
            task_id = f"{task.dag_id}/{task_type.value}"
            t0 = time.monotonic()
            try:
                result = await agent.run(prompt=task.prompt, codebase=codebase, task_id=task_id)
                elapsed = round(time.monotonic() - t0, 3)
                result.metadata["time_seconds"] = elapsed
                async with write_lock:
                    cache.append({
                        "name": task.name,
                        "dag_id": task.dag_id,
                        "output": result.output,
                        "metadata": result.metadata,
                    })
                consecutive_failures = 0
            except Exception as exc:
                elapsed = round(time.monotonic() - t0, 3)
                print(f"\n[error] {task_id}: {exc}")
                async with write_lock:
                    cache.append({
                        "name": task.name,
                        "dag_id": task.dag_id,
                        "output": None,
                        "error": str(exc),
                        "metadata": {"time_seconds": elapsed},
                    })
                failures += 1
                
                # if there's five consecutive failures, there's probably an issue beyond timeouts, so abort the run
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\n[abort] {MAX_CONSECUTIVE_FAILURES} consecutive failures — stopping")
                    abort = True
            pbar.update(1)

    await asyncio.gather(*[run_task(t, c, tt) for t, c, tt in all_tasks])
    pbar.close()

    status = f"{pbar.n}/{len(all_tasks)} tasks completed"
    if failures:
        raise RuntimeError(f"{status}, {failures} failed")
    print(f"[done] {status}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tasks-root", type=Path, required=True,
                   help="Parent directory; per-run task dirs are tasks_root/run_name.")
    p.add_argument("--task-set-name", nargs="+", required=True,
                   help="One or more task set names to run.")
    p.add_argument("--task-types", nargs="+", required=True,
                   help="TaskType values to run (e.g. dead_code add_parameter)")
    p.add_argument("--agent", type=AgentKind, default=AgentKind.LLM)
    p.add_argument("--model-name", help="LiteLLM provider/model ID or Copilot model name; defaults to the backend's model.")
    p.add_argument("--agent-kwargs", nargs="*", default=[],
                   help="Extra agent kwargs as key=value (strings only)")
    p.add_argument("--response-dir", type=Path, default=Path("local_data/responses"))
    p.add_argument("--run-names", nargs="+", required=True,
                   help="One or more run names (each maps to tasks_root/run_name).")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--n-parallel", type=int, default=1,
                   help="Number of tasks to run concurrently across all run names and task types.")
    p.add_argument("--overwrite", action="store_true",
                   help="Delete existing result files before running (prompts for confirmation).")
    p.add_argument("-y", "--yes", action="store_true",
                   help="Skip confirmation prompts.")
    p.add_argument("--retry-errors", action="store_true",
                   help="Re-run tasks that previously failed (output=null in cache).")
    args = p.parse_args()

    task_types = [TaskType(t) for t in args.task_types]
    agent_kwargs = _parse_kwargs(args.agent_kwargs)
    if args.model_name is not None:
        agent_kwargs.setdefault("model_name", args.model_name)

    asyncio.run(run_eval(
        tasks_root=args.tasks_root,
        task_set_names=args.task_set_name,
        task_types=task_types,
        agent_kind=args.agent,
        agent_kwargs=agent_kwargs,
        response_dir=args.response_dir,
        run_names=args.run_names,
        limit=args.limit,
        n_parallel=args.n_parallel,
        overwrite=args.overwrite,
        yes=args.yes,
        retry_errors=args.retry_errors,
    ))


if __name__ == "__main__":
    main()
