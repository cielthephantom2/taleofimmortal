"""Capitalize standalone UI labels; retain join fragments and prose."""
from datetime import datetime
import hashlib
from pathlib import Path
import re
import shutil
from translate import atomic_json, load_json

folder = Path(__file__).resolve().parent
root = folder.parents[1]
target = root / 'Mods/Villain/patch_vh/LocalText.json'
rows = load_json(target)
prefixes = ('common_', 'player_', 'playerInfo_', 'artifact_', 'artifactSprite_',
            'item_type_name', 'itemType_', 'skillInfo_', 'defaultKeysKeyText_',
            'ui_', 'uiChickenInfo_', 'mobilePaper_')
excluded = {'common_tian', 'common_miao', 'common_xiaoshi', 'common_yuetishi',
            'common_yue', 'common_nian', 'common_fenzhong'}
label_sources = {'属性', '寿命', '技能', '法宝', '器灵', '道具', '技艺', '物品', '关系'}
changes = []
for row in rows:
    old = row['en']
    if row['key'] in excluded or old != old.strip():
        continue
    if not old or not old[0].islower() or len(old) > 65 or re.search(r'[\n<>{}]', old):
        continue
    if not (row['key'].startswith(prefixes) or row['ch'] in label_sources):
        continue
    row['en'] = old[0].upper() + old[1:]
    changes.append({'key': row['key'], 'ch': row['ch'], 'before': old, 'after': row['en']})
backup = root / 'ModBackups' / ('UI-capitalization-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
master_path = root / 'TranslationExports/danh_sach_dong_bo.json'
for path in [target, master_path, folder / 'style.txt', folder / 'translate.py']:
    shutil.copy2(path, backup / path.name)
master = load_json(master_path)
for change in changes:
    rule = next((t for t in master['terms'] if t['key'] == change['key'] and t.get('key_globs') == [change['key']]), None)
    if rule is None:
        rule = {'key': 'ui_case_' + change['key'], 'source_ch': change['ch'],
                'files': ['LocalText.json'], 'key_globs': [change['key']],
                'group': 'ui_capitalization', 'strict': True, 'case_sensitive': True,
                'note': 'Nhãn giao diện: viết hoa chữ đầu, không viết hoa mọi từ.'}
        master['terms'].append(rule)
    rule['target_en'] = change['after']
atomic_json(master_path, master)
atomic_json(target, rows)
by_key = {c['key']: c for c in changes}
parts = root / 'TranslationExports/LocalText_PhanLoai'
manifest = load_json(parts / '_manifest.json')
for group in manifest['groups']:
    path = parts / group['file']
    data = load_json(path)
    dirty = False
    for row in data:
        change = by_key.get(row['key'])
        if change and row['en'] == change['before']:
            row['en'] = change['after']; dirty = True
    if dirty:
        shutil.copy2(path, backup / path.name)
        atomic_json(path, data)
manifest['source_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
atomic_json(parts / '_manifest.json', manifest)
atomic_json(root / 'TranslationExports/ui_capitalization_report.json', {'count': len(changes), 'changes': changes})
print('UI labels updated:', len(changes), 'backup:', backup)
