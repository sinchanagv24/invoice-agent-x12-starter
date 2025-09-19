#!/usr/bin/env python
import argparse, glob, os, sys, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROCESSED_DIR = Path("data/processed")
REJECTS_DIR = Path("data/rejects")

def resolve_targets(inputs, recursive: bool, pattern: str):
    """
    Expand a list of inputs into concrete file paths:
      - existing file paths are kept
      - directories are scanned (pattern + recursive)
      - globs are expanded
    """
    files = []
    for raw in inputs:
        p = Path(raw)
        if p.is_file():
            files.append(str(p))
            continue

        # Expand globs early (supports ** with recursive=True)
        if any(ch in raw for ch in ["*", "?", "["]):
            files.extend([str(Path(x)) for x in glob.glob(raw, recursive=recursive)])
            continue

        # Directory scan
        if p.is_dir():
            if recursive:
                files.extend([str(x) for x in p.rglob(pattern)])
            else:
                files.extend([str(x) for x in p.glob(pattern)])
            continue

        print(f"[WARN] Input not found or unsupported: {raw}", file=sys.stderr)

    # dedupe + keep stable order
    return sorted(set([f for f in files if Path(f).is_file()]))

def infer_status(edi_path: str) -> str:
    """
    Determine result by presence of artifact JSON:
      - data/processed/<file>.json -> POSTED
      - data/rejects/<file>.json  -> REJECTED
      - neither -> MISSING
    """
    name = os.path.basename(edi_path) + ".json"
    if (PROCESSED_DIR / name).exists():
        return "POSTED"
    if (REJECTS_DIR / name).exists():
        return "REJECTED"
    return "MISSING"

def run_one(py: str, edi_path: str, env: dict):
    cmd = [py, "-m", "app.ingest", edi_path]
    try:
        # We don’t rely on return code—ingest usually prints & writes artifacts.
        subprocess.run(cmd, check=False, env=env)
    except Exception as e:
        return (edi_path, "ERROR", str(e))
    status = infer_status(edi_path)
    return (edi_path, status, None)

def main():
    ap = argparse.ArgumentParser(description="Batch-ingest EDI files into the Invoice Agent pipeline.")
    ap.add_argument(
        "inputs",
        nargs="*",
        help="Files, directories, or glob patterns (e.g., data/inbound, data/inbound/*.edi, 'data/**/ACME*.edi')"
    )
    ap.add_argument(
        "--pattern",
        default="*.edi",
        help="Filename pattern when scanning directories (default: *.edi)"
    )
    ap.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recurse into directories when scanning"
    )
    ap.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter to use (default: current)"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Set ERP_DRY_RUN=1 to simulate successful ERP posting"
    )
    ap.add_argument(
        "--jobs", "-j",
        type=int,
        default=1,
        help="Parallel workers (default: 1). Keep modest for demo safety."
    )
    ap.add_argument(
        "--preview",
        action="store_true",
        help="Only list files that would be ingested and exit"
    )
    # backward-compatible default if no inputs are given
    ap.add_argument(
        "--default-glob",
        default="data/inbound/*.edi",
        help=argparse.SUPPRESS
    )

    args = ap.parse_args()

    # If user didn’t pass inputs, fall back to your original behavior
    inputs = args.inputs if args.inputs else [args.default_glob]

    files = resolve_targets(inputs, recursive=args.recursive, pattern=args.pattern)
    if not files:
        print("No files matched given inputs.", file=sys.stderr)
        sys.exit(1)

    if args.preview:
        print("Planned files:")
        for f in files:
            print(" -", f)
        print(f"Total: {len(files)}")
        return

    # Ensure artifact dirs exist (avoids race on first file)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTS_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if args.dry_run:
        env["ERP_DRY_RUN"] = "1"

    print(f"Ingesting {len(files)} file(s){' [DRY RUN]' if args.dry_run else ''}...")
    results = []

    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(run_one, args.python, f, env): f for f in files}
            for fut in as_completed(futs):
                results.append(fut.result())
    else:
        for f in files:
            print(f"\n=== {os.path.basename(f)} ===")
            results.append(run_one(args.python, f, env))

    # Summarize
    posted = rejected = missing = errored = 0
    print("\n=== Batch Results ===")
    for edi_path, status, err in results:
        if status == "POSTED":
            posted += 1
            print(f"[POSTED]   {edi_path}")
        elif status == "REJECTED":
            rejected += 1
            print(f"[REJECTED] {edi_path}")
        elif status == "MISSING":
            missing += 1
            print(f"[MISSING]  {edi_path} (no artifact found)")
        else:  # ERROR
            errored += 1
            print(f"[ERROR]    {edi_path} :: {err}")

    total = len(results)
    print("\n--- Summary ---")
    print(f"Total:    {total}")
    print(f"Posted:   {posted}")
    print(f"Rejected: {rejected}")
    print(f"Errored:  {errored}")
    print(f"Missing:  {missing}")

    # Non-zero exit if anything went wrong/missing (useful for CI)
    if rejected or errored or missing:
        sys.exit(1)

if __name__ == "__main__":
    main()
