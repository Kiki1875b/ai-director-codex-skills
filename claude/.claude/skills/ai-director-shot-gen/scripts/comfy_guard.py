"""One GPU job at a time (user decision): refuse to queue while the server is running or holding a job.

submit() checks the queue and posts the job inside one cross-process lock, so two of our scripts that both see an
idle server cannot both queue. This guards our own scripts on this PC only; jobs started from the ComfyUI page or
another machine are not covered. Batch queueing is allowed only when the user asked for it (--allow-queue,
used by queue_shots.sh).
"""
import hashlib
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ai-director", "scripts"))
import file_lock  # noqa: E402


def busy_jobs(srv):
    """Return (running, pending) counts; raises SystemExit when the server cannot be reached."""
    try:
        q = requests.get(f"{srv}/queue", timeout=20).json()
    except (requests.RequestException, ValueError) as e:
        sys.exit(f"ComfyUI not reachable at {srv}: {e}")
    return len(q.get("queue_running", [])), len(q.get("queue_pending", []))


def require_free(srv, allow_queue=False):
    running, pending = busy_jobs(srv)
    if (running or pending) and not allow_queue:
        sys.exit(f"GPU busy ({running} running, {pending} pending): one job at a time. Wait for it to finish, "
                 f"check with comfy_progress.py --once, or pass --allow-queue only if the user asked to queue several jobs.")


def submit(srv, payload, allow_queue=False, timeout=60):
    """Check the queue and POST /prompt atomically (with respect to our other scripts). Returns the response."""
    name = "comfy_submit_" + hashlib.sha1(srv.encode("utf-8")).hexdigest()[:10]
    try:
        with file_lock.lock(name, timeout=180):
            require_free(srv, allow_queue)
            return requests.post(f"{srv}/prompt", json=payload, timeout=timeout)
    except TimeoutError as e:
        sys.exit(f"another submission is still in progress ({e}); try again in a moment")
