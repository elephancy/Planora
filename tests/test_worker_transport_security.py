from __future__ import annotations
import ast
import builtins
import dataclasses
import inspect
import struct
import copyreg
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace
import pytest
from utils.generator import generate_instance
from utils import worker_transport as transport

class _Execute:
    def __init__(self, marker): self.marker = marker
    def __reduce__(self): return builtins.exec, (f"open({str(self.marker)!r}, 'w').write('executed')",)

@pytest.mark.parametrize('protocol', [4, 5])
def test_desktop_producer_to_worker_preserves_domain_and_metadata(tmp_path, protocol):
    from ui.window_solver import _write_private_solver_payload
    instance = generate_instance('small_demo')
    instance.locked_activities = {1: {'day': 'MON', 'slot': 0, 'room_id': 1}}
    instance.day_start_time = '08:30'
    instance.calendar_rules = {'dates': {'2026-10-22'}, 'pair': ('MON', 2)}
    path = tmp_path / 'instance.pkl'
    if protocol == pickle.DEFAULT_PROTOCOL: _write_private_solver_payload(str(path), instance)
    else: path.write_bytes(pickle.dumps(instance, protocol=protocol))
    restored = transport.read_worker_instance(path)
    assert restored == instance
    assert restored.day_start_time == '08:30'
    assert restored.locked_activities == instance.locked_activities
    assert restored.calendar_rules == instance.calendar_rules

def test_worker_producer_to_desktop_result_consumer(tmp_path, monkeypatch):
    import core.engine_cli as engine
    from services.contracts import SolveResult
    from ui.window_solver import _write_private_solver_payload
    instance = generate_instance('small_demo')
    source, result = tmp_path / 'input.pkl', tmp_path / 'output.pkl'
    _write_private_solver_payload(str(source), instance)
    schedule = {1: {'day': 'MON', 'slot': 0, 'room_id': 1, 'group_ids': [1]}}
    answer = SolveResult(status=0, raw_status=2, schedule=schedule, hard_conflicts=[], meta={'source': 'test'})
    seen = []
    def solve(value, options, progress_hook): seen.append(value); return answer
    monkeypatch.setattr(engine, 'solve_with_engine', solve)
    monkeypatch.setattr(sys, 'argv', ['engine_cli.py', str(source), str(result)])
    assert engine.main() == 0
    assert seen[0] == instance
    payload = transport.read_worker_result(result)
    assert payload['schedule'] == schedule
    assert payload['meta']['engine_backend']['transport'] == 'desktop_qprocess_pickle_v1'

@pytest.mark.parametrize('reader', [transport.read_worker_instance, transport.read_worker_result])
def test_arbitrary_global_rejected_without_execution(tmp_path, reader):
    marker, path = tmp_path / 'marker', tmp_path / 'payload.pkl'
    path.write_bytes(pickle.dumps(_Execute(marker)))
    with pytest.raises(pickle.UnpicklingError, match='forbidden global'): reader(path)
    assert not marker.exists()

def test_cached_extension_cannot_bypass_global_filter(tmp_path):
    marker = tmp_path / 'marker'
    code = f"open({str(marker)!r}, 'w').write('executed')"
    payload = b'\x80\x02\x82\xfa' + pickle.dumps((code,), protocol=2)[2:-1] + b'R.'
    previous = copyreg._extension_cache.get(250)
    copyreg._extension_cache[250] = builtins.exec
    try:
        with pytest.raises(pickle.UnpicklingError, match='extensions'): transport._decode(payload, instance=False)
    finally:
        if previous is None: copyreg._extension_cache.pop(250, None)
        else: copyreg._extension_cache[250] = previous
    assert not marker.exists()

@pytest.mark.parametrize('entry', ['main', '_legacy_main'])
def test_engine_rejects_input_before_solving(tmp_path, monkeypatch, entry):
    import core.engine_cli as engine
    marker, source, target = (tmp_path / name for name in ('marker', 'input.pkl', 'output.pkl'))
    source.write_bytes(pickle.dumps(_Execute(marker)))
    monkeypatch.setattr(sys, 'argv', ['engine_cli.py', str(source), str(target)])
    monkeypatch.setattr(engine, 'solve_with_engine', lambda *args, **kwargs: pytest.fail('must not solve'))
    assert getattr(engine, entry)() == 2
    assert not marker.exists() and not target.exists()

def test_actual_ui_callback_rejects_global_and_restores_ui(tmp_path, monkeypatch):
    from ui import window_solver
    marker, source = tmp_path / 'marker', tmp_path / 'result.pkl'
    source.write_bytes(pickle.dumps(_Execute(marker)))
    events = []
    fake = SimpleNamespace(proc=None, _solver_output_log='', tmp_res_path=str(source), sender=lambda: None,
        _update_solve_progress_status=lambda *args: None, set_busy=lambda *args: None,
        _stop_solve_progress=lambda: None, _append_audit_log=lambda *args: events.append(args[0]),
        _restore_locks_if_needed=lambda: events.append('restore'), _cleanup_solver_temp_files=lambda: events.append('cleanup'),
        set_status=lambda value: events.append(value))
    monkeypatch.setattr(window_solver.QMessageBox, 'critical', lambda *args: events.append('dialog'))
    window_solver.WindowSolverMixin.on_solver_finished(fake, 0, None)
    assert 'solve_result_read_error' in events and 'restore' in events and 'cleanup' in events
    assert not marker.exists()

@pytest.mark.parametrize('raw', [b'', b'N.N.', b'\x80\x04N', b'Pexternal\n.'])
def test_incomplete_trailing_or_external_payload_refused(raw):
    with pytest.raises((ValueError, pickle.UnpicklingError)): transport._decode(raw, instance=False)

def test_byte_opcode_depth_and_cycle_bounds(tmp_path, monkeypatch):
    path = tmp_path / 'bounded.pkl'; path.write_bytes(pickle.dumps({'status': 0, 'schedule': {}}))
    with monkeypatch.context() as patch:
        patch.setattr(transport, 'MAX_BYTES', 8)
        with pytest.raises(ValueError, match='bounded regular file'): transport.read_worker_result(path)
    with monkeypatch.context() as patch:
        patch.setattr(transport, 'MAX_OPCODES', 2)
        with pytest.raises(ValueError, match='opcode limit'): transport.read_worker_result(path)
    with monkeypatch.context() as patch:
        patch.setattr(transport, 'MAX_DEPTH', 2)
        with pytest.raises(ValueError, match='structural limit'): transport._decode(pickle.dumps([[[[1]]]]), instance=False)
    cycle=[]; cycle.append(cycle)
    with pytest.raises(ValueError, match='reference cycles'): transport._decode(pickle.dumps(cycle), instance=False)

@pytest.mark.parametrize('payload', [{'status': True, 'schedule': {}}, {'status': 0, 'schedule': []},
                                    {'status': 0, 'schedule': {'1': {}}}, {'status': 0, 'schedule': {}, 'meta': []}])
def test_result_schema_rejects_invalid_shape(tmp_path, payload):
    path = tmp_path / 'result.pkl'; path.write_bytes(pickle.dumps(payload))
    with pytest.raises(ValueError, match='invalid status'): transport.read_worker_result(path)

def test_domain_classes_have_no_execution_hooks_and_result_rejects_them(tmp_path):
    for cls in transport._DOMAIN_TYPES:
        assert not ({'__new__', '__setstate__', '__reduce__', '__reduce_ex__', '__setattr__', '__del__', '__post_init__', '__getattr__', '__getattribute__'} & vars(cls).keys())
    path = tmp_path / 'result.pkl'; path.write_bytes(pickle.dumps(generate_instance('small_demo')))
    with pytest.raises(pickle.UnpicklingError, match='forbidden global'): transport.read_worker_result(path)

def test_upstream_sha1_identifiers_and_sha256_exact():
    from benchmarks.cbctt_corpus import _hashes as cbctt
    from benchmarks.itc2019_corpus import _hashes as itc2019
    plain='aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d'
    blob='b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0'
    sha256='2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    assert cbctt(b'hello') == {'length': 5, 'sha1_git': blob, 'sha1': plain, 'sha256': sha256}
    assert itc2019(b'hello') == {'byte_length': 5, 'git_blob_sha1': blob, 'sha256': sha256}


@pytest.mark.parametrize('payload', [
    {'status': 4, 'schedule': {1: {'day': 'MON', 'slot': 0, 'room_id': 1}}, 'meta': {'attempts': []}},
    {'status': -2, 'schedule': {}, 'error': 'no rooms', 'reason': 'capacity', 'meta': {}},
    {'status': -1, 'schedule': {}, 'meta': {'hard_conflicts': ['test']}},
])
def test_legacy_packaged_worker_result_bytes_remain_compatible(tmp_path, payload):
    path = tmp_path / 'legacy-result.pkl'
    path.write_bytes(pickle.dumps(payload, protocol=4))
    assert transport.read_worker_result(path) == payload


def test_worker_reader_closes_descriptor_if_stream_wrapping_fails(tmp_path, monkeypatch):
    path = tmp_path / 'payload.pkl'; path.write_bytes(pickle.dumps(None))
    closed = []
    original_close = transport.os.close
    def close(descriptor):
        closed.append(descriptor)
        return original_close(descriptor)
    monkeypatch.setattr(transport.os, 'close', close)
    monkeypatch.setattr(transport.os, 'fdopen', lambda *args: (_ for _ in ()).throw(OSError('wrap failed')))
    with pytest.raises(OSError, match='wrap failed'): transport.read_worker_result(path)
    assert len(closed) == 1


@pytest.mark.parametrize('raw,limit', [
    (b'\x80\x04Nr' + struct.pack('<I', 0xffffffff) + b'.', transport.MAX_NODES),
    (b'Np4294967295\n.', transport.MAX_NODES),
    (b'Np-1\n.', transport.MAX_NODES),
    (b'\x80\x04Nq\x03.', 2),
    (b'\x80\x04j' + struct.pack('<I', 0xffffffff) + b'.', transport.MAX_NODES),
])
def test_sparse_memo_indices_refused_before_any_unpickler_construction(raw, limit, monkeypatch):
    monkeypatch.setattr(transport, 'MAX_NODES', limit)
    monkeypatch.setattr(transport, '_WorkerUnpickler', lambda *args, **kwargs: pytest.fail('must not construct or load'))
    with pytest.raises(ValueError, match='memo index limit'):
        transport._decode(raw, instance=False)


@pytest.mark.parametrize('raw', [b'\x80\x04N\x94\x94\x94.', b'Np0\np0\np0\n.'])
def test_memo_entry_count_refused_before_any_unpickler_construction(raw, monkeypatch):
    monkeypatch.setattr(transport, 'MAX_NODES', 2)
    monkeypatch.setattr(transport, '_WorkerUnpickler', lambda *args, **kwargs: pytest.fail('must not construct or load'))
    with pytest.raises(ValueError, match='memo entry limit'):
        transport._decode(raw, instance=False)


def test_actual_domain_class_source_and_generated_constructors_are_inert():
    from utils import domain
    source = Path(domain.__file__).read_text(encoding='utf-8')
    classes = {node.name: node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)}
    for cls in transport._DOMAIN_TYPES:
        node = classes[cls.__name__]
        # The actual domain source supplies only fields/docstrings, with no user
        # constructor, post-init hook, methods, base class or metaclass.
        assert not node.bases and not node.keywords
        assert len(node.decorator_list) == 1 and isinstance(node.decorator_list[0], ast.Name)
        assert node.decorator_list[0].id == 'dataclass'
        assert all(isinstance(item, ast.AnnAssign) or (
            isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str))
            for item in node.body)
        assert dataclasses.is_dataclass(cls)
        assert cls.__init__.__code__.co_filename == '<string>'
        assert set(cls.__init__.__code__.co_names) == {field.name for field in dataclasses.fields(cls)}
        closure = inspect.getclosurevars(cls.__init__)
        assert not closure.globals
        assert all(value is dataclasses._HAS_DEFAULT_FACTORY or value in (list, dict, set)
                   for value in closure.nonlocals.values())
        assert '__post_init__' not in vars(cls)
