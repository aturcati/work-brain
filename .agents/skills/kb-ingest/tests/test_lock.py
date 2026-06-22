import os
import subprocess
import sys
import time
from pathlib import Path

LOCK_PY = str(Path(__file__).parent.parent / "lock.py")


def run_lock(lock_file, action, lock_dir, timeout=1):
    env = {**os.environ, "KB_LOCK_DIR": str(lock_dir)}
    return subprocess.run(
        [sys.executable, LOCK_PY, "--lock-file", str(lock_file),
         "--action", action, "--timeout", str(timeout)],
        capture_output=True, text=True, env=env,
    )


def physical(lock_dir):
    return list(Path(lock_dir).glob("*.lock"))


def test_acquire_creates_lock_outside_vault(tmp_path):
    logical = tmp_path / "vault" / ".kb" / ".inbox.lock"
    lock_dir = tmp_path / "locks"
    r = run_lock(logical, "acquire", lock_dir)
    assert r.returncode == 0 and "ACQUIRED" in r.stdout
    assert len(physical(lock_dir)) == 1
    assert not logical.exists()  # nothing written into the (synced) vault


def test_acquire_busy_times_out(tmp_path):
    logical = tmp_path / ".inbox.lock"
    lock_dir = tmp_path / "locks"
    assert run_lock(logical, "acquire", lock_dir).returncode == 0
    r = run_lock(logical, "acquire", lock_dir, timeout=1)
    assert r.returncode == 1
    assert "LOCK_TIMEOUT" in r.stderr


def test_different_logical_paths_do_not_collide(tmp_path):
    lock_dir = tmp_path / "locks"
    assert run_lock(tmp_path / "a.lock", "acquire", lock_dir).returncode == 0
    assert run_lock(tmp_path / "b.lock", "acquire", lock_dir).returncode == 0
    assert len(physical(lock_dir)) == 2


def test_release_removes_lock(tmp_path):
    logical = tmp_path / ".inbox.lock"
    lock_dir = tmp_path / "locks"
    run_lock(logical, "acquire", lock_dir)
    r = run_lock(logical, "release", lock_dir)
    assert "RELEASED" in r.stdout
    assert physical(lock_dir) == []


def test_release_idempotent_when_no_lock(tmp_path):
    r = run_lock(tmp_path / ".inbox.lock", "release", tmp_path / "locks")
    assert r.returncode == 0 and "RELEASED" in r.stdout


def test_stale_lock_auto_cleared(tmp_path):
    logical = tmp_path / ".inbox.lock"
    lock_dir = tmp_path / "locks"
    run_lock(logical, "acquire", lock_dir)
    lock = physical(lock_dir)[0]
    stale = time.time() - 400  # past the 300s stale threshold
    os.utime(lock, (stale, stale))
    r = run_lock(logical, "acquire", lock_dir)
    assert r.returncode == 0 and "ACQUIRED" in r.stdout


def test_fresh_foreign_lock_not_cleared(tmp_path):
    logical = tmp_path / ".inbox.lock"
    lock_dir = tmp_path / "locks"
    run_lock(logical, "acquire", lock_dir)  # fresh, within stale window
    r = run_lock(logical, "acquire", lock_dir, timeout=1)
    assert r.returncode == 1


def test_legacy_in_vault_lock_file_removed(tmp_path):
    logical = tmp_path / ".kb" / ".inbox.lock"
    logical.parent.mkdir(parents=True)
    logical.write_text("legacy")  # pre-redirect leftover inside the vault
    lock_dir = tmp_path / "locks"
    r = run_lock(logical, "acquire", lock_dir)
    assert r.returncode == 0
    assert not logical.exists()
