"""Cross-process lock and process-liveness helpers shared by the generation scripts.

lock(name) holds an OS byte-range lock (msvcrt on Windows, fcntl elsewhere) on a lock file that is never deleted.
The OS releases the lock when the owning process exits or crashes, so there is no stale-lock takeover step that two
waiters could race on. A per-name threading.Lock adds the same guarantee between threads of one process.
"""
import contextlib
import json
import os
import tempfile
import threading
import time

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is installed in this project
    psutil = None

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - this project runs on Windows
    import fcntl

LOCK_DIR = os.path.join(tempfile.gettempdir(), "ai_director_locks")
_thread_locks = {}
_thread_locks_guard = threading.Lock()


def proc_identity(pid=None):
    """(pid, create_time) so a reused PID can be told apart from the original process."""
    pid = pid or os.getpid()
    ct = None
    if psutil:
        try:
            ct = psutil.Process(pid).create_time()
        except (psutil.Error, OSError):
            ct = None
    return pid, ct


def alive(pid, create_time):
    """True if that exact process (pid + creation time) still runs."""
    if not pid:
        return False
    if psutil:
        try:
            p = psutil.Process(pid)
            if create_time is not None and abs(p.create_time() - create_time) > 1.0:
                return False  # PID reused by another process
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except (psutil.Error, OSError):
            return False
    return True  # cannot tell: be conservative


def atomic_write_json(path, data):
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _os_trylock(fd):
    try:
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _os_unlock(fd):
    with contextlib.suppress(OSError):
        if os.name == "nt":
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def lock(name, timeout=120.0, poll=0.1):
    os.makedirs(LOCK_DIR, exist_ok=True)
    with _thread_locks_guard:
        tl = _thread_locks.setdefault(name, threading.Lock())
    t0 = time.time()
    if not tl.acquire(timeout=timeout):
        raise TimeoutError(f"lock {name} busy in this process")
    fd = None
    try:
        fd = os.open(os.path.join(LOCK_DIR, f"{name}.lock"), os.O_RDWR | os.O_CREAT)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")  # Windows byte-range locks need a byte to lock
        while not _os_trylock(fd):
            if time.time() - t0 > timeout:
                raise TimeoutError(f"lock {name} held by another process")
            time.sleep(poll)
        try:
            yield
        finally:
            _os_unlock(fd)
    finally:
        if fd is not None:
            os.close(fd)
        tl.release()
