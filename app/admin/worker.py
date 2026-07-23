from __future__ import annotations

import argparse

from app.admin.job_service import run_next_job, worker_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the single-host admin job worker.")
    parser.add_argument("--once", action="store_true", help="Run at most one queued job and exit.")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()
    if args.once:
        run_next_job()
    else:
        worker_loop(args.poll_interval)


if __name__ == "__main__":
    main()
