"""Bounded compatibility reader for the private desktop worker pickle protocol.

Public scenario/project import remains JSON/SQLite-only. This reader accepts only
Planora's inert domain dataclasses and builtin data, never arbitrary globals.
Writers retain their current format so existing packaged workers still interop.
"""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import pickle
import pickletools
import stat
from typing import Any

from utils.domain import (
    Activity, Course, DistributionConstraint, GenericResource, Group, Instance,
    Program, Room, StaffMember,
)

MAX_BYTES = 64 * 1024 * 1024
MAX_OPCODES = 4_000_000
MAX_NODES = 2_000_000
MAX_DEPTH = 100
_DOMAIN_TYPES = (Activity, Course, DistributionConstraint, GenericResource, Group,
                 Instance, Program, Room, StaffMember)
_DOMAIN_GLOBALS = {('utils.domain', cls.__name__): cls for cls in _DOMAIN_TYPES}


class _WorkerUnpickler(pickle.Unpickler):
    def __init__(self, stream: io.BytesIO, *, instance: bool):
        super().__init__(stream)
        self._instance = instance

    def find_class(self, module: str, name: str) -> type:
        if self._instance and (module, name) in _DOMAIN_GLOBALS:
            return _DOMAIN_GLOBALS[module, name]
        # Older protocol versions use these globals for inert set containers.
        if module == 'builtins' and name in ('set', 'frozenset'):
            return set if name == 'set' else frozenset
        raise pickle.UnpicklingError('Worker payload requests a forbidden global')

    def persistent_load(self, pid: Any) -> Any:
        raise pickle.UnpicklingError('Worker payload cannot reference external data')


def _check_graph(value: Any, *, instance: bool) -> None:
    """Reject cycles, foreign objects and excessive nesting after safe decoding."""
    active: set[int] = set()
    seen: set[int] = set()
    stack = [(value, 0, False)]
    nodes = 0
    while stack:
        item, depth, leaving = stack.pop()
        identity = id(item)
        if leaving:
            active.remove(identity)
            continue
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError('Worker payload exceeds its structural limit')
        kind = type(item)
        if item is None or kind in (bool, int, str, bytes):
            continue
        if kind is float:
            if not math.isfinite(item):
                raise ValueError('Worker payload contains a nonfinite number')
            continue
        if identity in active:
            raise ValueError('Worker payload cannot contain reference cycles')
        if identity in seen:
            continue
        if kind is dict:
            children = [part for pair in item.items() for part in pair]
        elif kind in (list, tuple, set, frozenset):
            children = item
        elif instance and kind in _DOMAIN_TYPES:
            children = vars(item).values()
        else:
            raise ValueError('Worker payload contains a foreign object')
        if len(children) > MAX_NODES:
            raise ValueError('Worker payload exceeds its structural limit')
        seen.add(identity)
        active.add(identity)
        stack.append((item, depth, True))
        stack.extend((child, depth + 1, False) for child in children)


def _decode(raw: bytes, *, instance: bool) -> Any:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Worker payload exceeds its byte limit or is empty')
    last = None
    memo_writes = 0
    for count, (opcode, argument, position) in enumerate(pickletools.genops(raw), 1):
        if count > MAX_OPCODES:
            raise ValueError('Worker payload exceeds its opcode limit')
        # Explicit sparse memo indices make the C unpickler allocate before
        # graph validation. Bound them before constructing any unpickler.
        if opcode.name in ('PUT', 'BINPUT', 'LONG_BINPUT', 'GET', 'BINGET', 'LONG_BINGET'):
            if type(argument) is not int or not 0 <= argument < MAX_NODES:
                raise ValueError('Worker payload exceeds its memo index limit')
        if opcode.name in ('PUT', 'BINPUT', 'LONG_BINPUT', 'MEMOIZE'):
            memo_writes += 1
            if memo_writes > MAX_NODES:
                raise ValueError('Worker payload exceeds its memo entry limit')
        # Cached copyreg extensions can bypass find_class, so reject them even
        # if another library registered a harmless-looking extension globally.
        if opcode.name in ('EXT1', 'EXT2', 'EXT4', 'PERSID', 'BINPERSID'):
            raise pickle.UnpicklingError('Worker payload cannot reference extensions or external data')
        last = opcode, position
    if last is None or last[0].name != 'STOP' or last[1] != len(raw) - 1:
        raise pickle.UnpicklingError('Worker payload must contain one complete object')
    value = _WorkerUnpickler(io.BytesIO(raw), instance=instance).load()
    _check_graph(value, instance=instance)
    return value


def _read(path: str | Path, *, instance: bool) -> Any:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        stream = os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError('Worker payload must be a bounded regular file')
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if len(raw) != before.st_size or any(getattr(before, key) != getattr(after, key) for key in fields):
            raise ValueError('Worker payload changed while being read')
    return _decode(raw, instance=instance)


def read_worker_instance(path: str | Path) -> Instance:
    value = _read(path, instance=True)
    if type(value) is not Instance:
        raise ValueError('Worker input must be a Planora Instance')
    expected = {'programs': Program, 'groups': Group, 'courses': Course,
                'staff': StaffMember, 'rooms': Room, 'activities': Activity}
    for name, cls in expected.items():
        rows = getattr(value, name, None)
        if type(rows) is not dict or any(type(key) is not int or type(row) is not cls for key, row in rows.items()):
            raise ValueError('Worker input has an invalid domain collection')
    return value


def read_worker_result(path: str | Path) -> dict[str, Any]:
    value = _read(path, instance=False)
    if (type(value) is not dict or type(value.get('status')) is not int
            or type(value.get('schedule')) is not dict
            or any(type(key) is not int or type(row) is not dict for key, row in value['schedule'].items())
            or ('meta' in value and type(value['meta']) is not dict)):
        raise ValueError('Worker result has an invalid status, schedule or metadata')
    return value
