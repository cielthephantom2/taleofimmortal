"""Recover only validated failed translations from saved journals; never call an API."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import uuid

from translate import (CJK, Engine, Store, atomic_json, digest, load_json,
                       normalize_wire_response, validate, validate_response)


@contextmanager
def session_lock(state):
    handle = (state / 'session.lock').open('r+b')
    try:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def recover(engine, apply=False):
    store = object.__new__(Store)
    store.directory, store.path = engine.state, engine.state / 'progress.sqlite3'
    ready = store.ready(engine.jobs)
    failures = store.failures([j for j in engine.jobs if j.key not in ready], include_previous_policies=True)
    pending = {j.key: j for j in engine.jobs if j.key in failures and j.key not in ready}
    original_count = len(pending)
    recovered, provenance = [], []
    memory = store.memories()

    def accept(job, vi, method, request_id=None):
        try:
            vi = validate(job, vi, masked=False)
        except ValueError:
            return
        recovered.append((job, vi))
        provenance.append({'key': job.key, 'file': job.file, 'game_key': job.game_key,
                           'method': method, 'request_id': request_id})
        memory[job.cache_key] = vi
        pending.pop(job.key, None)

    for job in list(pending.values()):
        value = job.exact if job.exact is not None else memory.get(job.cache_key)
        if value is None and not CJK.search(job.source):
            value = job.source
        if value is not None:
            accept(job, value, 'approved-or-memory')

    for path in sorted((engine.state / 'journal').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        if not pending:
            break
        record = load_json(path)
        if record.get('model') != engine.cfg['model']:
            continue
        jobs = []
        for saved in record.get('jobs', []):
            job = pending.get(saved['key'])
            # Prove style/model/generation policy unchanged; only terminology
            # or edge formatting may differ, and current validation is applied.
            same_base_policy = saved['policy'] == digest([
                engine.base_policy, saved['terms'], saved['prefix'], saved['suffix'],
                saved.get('format_exception'), 'terminology-context-v2'])
            if (job is not None and saved['source'] == job.source and
                    saved['source_hash'] == job.source_hash and same_base_policy):
                jobs.append(job)
        if not jobs:
            continue
        response = normalize_wire_response(record['response'], record.get('wire_keys', {}))
        good, _ = validate_response(jobs, response)
        for job, vi in good:
            accept(job, vi, 'saved-journal', path.stem)

    for job in list(pending.values()):
        if job.cache_key in memory:
            accept(job, memory[job.cache_key], 'identical-context-memory')

    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'applied': apply,
              'failed_before': original_count, 'recovered': len(recovered),
              'remaining': len(pending), 'api_calls': 0, 'recovery': provenance,
              'remaining_items': [{'key': j.key, 'file': j.file, 'game_key': j.game_key,
                                   'ch': j.source, 'error': failures[j.key]} for j in pending.values()]}
    if apply:
        backup = engine.state / 'repairs' / ('journal-recovery-' + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        source_db = sqlite3.connect(store.path)
        backup_db = sqlite3.connect(backup / 'progress.before.sqlite3')
        try:
            source_db.backup(backup_db)
        finally:
            backup_db.close()
            source_db.close()
        atomic_json(backup / 'recovered_values.json', [
            {'job': asdict(j), 'vi': vi} for j, vi in recovered])
        store.save(recovered)
        engine.apply(store, [j for j, _ in recovered], quiet=True)
        engine.report(store, quiet=True)
        report['backup'] = str(backup)
    destination = engine.folder / ('journal_repair_result.json' if apply else 'journal_repair_preview.json')
    atomic_json(destination, report)
    print(f'Failed: {original_count}; recovered: {len(recovered)}; remaining: {len(pending)}; API calls: 0.')
    print(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--apply', action='store_true', help='Back up and save validated recoveries')
    args = parser.parse_args()
    if args.apply:
        cfg = load_json(args.config)
        state = (args.config.resolve().parent / cfg['state_directory']).resolve()
        with session_lock(state):
            recover(Engine(args.config), apply=True)
    else:
        recover(Engine(args.config))


if __name__ == '__main__':
    main()
