"""Translate ten dialogue rows to a separate preview; never write game JSON."""
import argparse
from pathlib import Path
from translate import Engine, ChatCompletions, Store, atomic_json, load_json, resolve_api_key, validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    if args.offset < 0:
        parser.error('offset must be nonnegative')
    folder = Path(__file__).resolve().parent
    cfg = load_json(folder / 'config.json')
    root = (folder / cfg['game_root']).resolve()
    spec = next(s for s in cfg['files'] if Path(s['path']).name == 'LocalText.json')
    rows = load_json(root / spec['path'])
    selected = [r for r in rows if r['key'].startswith('drama_dialogue')
                and len(r['ch'].strip()) >= 12][args.offset:args.offset+10]
    if len(selected) != 10:
        raise ValueError('Could not select ten dialogue rows')
    cfg['files'] = [{**spec, 'include_key_globs': [r['key'] for r in selected],
                     'exclude_key_globs': []}]
    cfg['state_directory'] = 'state_sample10' + (('_offset' + str(args.offset)) if args.offset else '')
    cfg['parallel_requests'] = 1
    config = folder / 'config.sample10.json'
    atomic_json(config, cfg)
    engine = Engine(config)
    key = resolve_api_key(cfg, folder)
    if not key:
        raise ValueError('API key environment variable or api_key_file is missing')
    store = Store(engine.state)
    store.recover()
    ready = store.ready(engine.jobs)
    pending = [j for j in engine.jobs if j.key not in ready]
    seeds = [(j, validate(j, j.exact, masked=False)) for j in pending if j.exact is not None]
    store.save(seeds)
    pending = [j for j in pending if j.exact is None]
    if pending:
        ChatCompletions(cfg, engine.style, key, store).translate(pending)
    ready = store.ready(engine.jobs)
    previous = {r['key']: r['en'] for r in selected}
    preview = [{'key': j.game_key, 'ch': j.source, 'previous_en': previous[j.game_key],
                'en': ready.get(j.key), 'status': 'done' if j.key in ready else 'failed'}
               for j in engine.jobs]
    output = engine.state / 'preview.json'
    atomic_json(output, preview)
    print('Accepted:', len(ready), '/', len(engine.jobs), flush=True)
    print('Preview:', output, flush=True)
    for row in preview:
        print(row['key'] + ': ' + str(row['en']), flush=True)
    return 0 if len(ready) == 10 else 2


if __name__ == '__main__':
    raise SystemExit(main())
