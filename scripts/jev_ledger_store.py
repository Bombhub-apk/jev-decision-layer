"""Crash-conscious JSON ledger storage shared by Jev writers and the panel."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class LedgerError(RuntimeError):
    """The usage ledger could not be safely read or updated."""


class LedgerCorruptError(LedgerError):
    """The ledger and any available recovery copy are invalid."""


_THREAD_LOCKS = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _paths(ledger_path):
    path = Path(ledger_path)
    return path, path.with_name(path.name + ".bak"), path.with_name(path.name + ".lock")


def _thread_lock_for(path):
    key = str(Path(path).resolve()).casefold()
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def ledger_lock(ledger_path):
    """Serialize writers in this process and across cooperating processes."""
    path, _backup_path, lock_path = _paths(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    thread_lock = _thread_lock_for(path)
    with thread_lock:
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                if handle.seek(0, os.SEEK_END) == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _decode_valid_ledger(path):
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
        records = json.loads(raw)
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LedgerCorruptError(f"Invalid ledger JSON: {path.name}") from error
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise LedgerCorruptError(f"Ledger must be a JSON list of records: {path.name}")
    return records


def _atomic_write_json(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=path.name + ".tmp-",
            suffix=".json",
            dir=path.parent,
            delete=False,
        ) as handle:
            temp_name = handle.name
            json.dump(records, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _atomic_copy(source, destination):
    source, destination = Path(source), Path(destination)
    temp_name = None
    try:
        with source.open("rb") as input_handle, tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=destination.name + ".tmp-",
            suffix=".bak",
            dir=destination.parent,
            delete=False,
        ) as output_handle:
            temp_name = output_handle.name
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        shutil.copystat(source, temp_name)
        os.replace(temp_name, destination)
    finally:
        if temp_name and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _preserve_corrupt_copy(path):
    path = Path(path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 1
    while target.exists():
        target = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    shutil.copy2(path, target)
    return target


def _load_unlocked(path, create):
    path, backup_path, _lock_path = _paths(path)
    if path.exists():
        try:
            return _decode_valid_ledger(path), False
        except LedgerCorruptError as primary_error:
            if not backup_path.exists():
                raise primary_error
            try:
                backup_records = _decode_valid_ledger(backup_path)
            except (LedgerCorruptError, OSError) as backup_error:
                raise LedgerCorruptError(
                    f"Ledger and recovery backup are invalid: {path.name}"
                ) from backup_error
            _preserve_corrupt_copy(path)
            _atomic_write_json(path, backup_records)
            return backup_records, True

    if backup_path.exists():
        try:
            backup_records = _decode_valid_ledger(backup_path)
        except (LedgerCorruptError, OSError) as backup_error:
            raise LedgerCorruptError(
                f"Ledger is missing and its recovery backup is invalid: {path.name}"
            ) from backup_error
        _atomic_write_json(path, backup_records)
        return backup_records, True

    if not create:
        raise LedgerError(f"Ledger does not exist: {path.name}")
    _atomic_write_json(path, [])
    return [], False


def load_ledger(ledger_path, *, create=False):
    """Read a consistent ledger, restoring a validated backup without discarding corrupt bytes."""
    path, _backup_path, _lock_path = _paths(ledger_path)
    with ledger_lock(path):
        records, recovered = _load_unlocked(path, create)
    has_recovery_artifacts = any(path.parent.glob(path.name + ".corrupt-*"))
    return records, {
        "recovered": recovered,
        "has_recovery_artifacts": has_recovery_artifacts,
    }


def append_record(ledger_path, record):
    """Append under lock, keep a last-known-good backup, and atomically replace the ledger."""
    path, backup_path, _lock_path = _paths(ledger_path)
    with ledger_lock(path):
        records, recovered = _load_unlocked(path, create=True)
        _atomic_copy(path, backup_path)
        records.append(record)
        _atomic_write_json(path, records)
    return {
        "recovered": recovered,
        "has_recovery_artifacts": any(path.parent.glob(path.name + ".corrupt-*")),
    }


def has_recovery_artifacts(ledger_path):
    path = Path(ledger_path)
    return any(path.parent.glob(path.name + ".corrupt-*"))
