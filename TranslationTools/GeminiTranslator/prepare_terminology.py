"""Import reviewed game terms that actually occur in LocalText; preserve approved names."""
import csv
from pathlib import Path
from translate import atomic_json, load_json
from terminology import Matcher


def main():
    folder = Path(__file__).resolve().parent
    root = folder.parents[1]
    rows = load_json(root / 'Mods/Villain/patch_vh/LocalText.json')
    path = root / 'TranslationExports/danh_sach_dong_bo.json'
    master = load_json(path)
    by_source = {}
    for term in master['terms']:
        by_source.setdefault(term.get('source_ch', term.get('source_tc')), []).append(term)
    with (folder / 'game_terms_reviewed.tsv').open(encoding='utf-8-sig') as handle:
        candidates = [r for r in csv.reader(handle, delimiter='\t') if r and not r[0].startswith('#')]
    present = set()
    matcher = Matcher(r[0] for r in candidates)
    for row in rows:
        present.update(word for _, _, word in matcher.find(row['ch']))
    added, updated, absent = [], [], []
    for source, vi, domain, mode, *tail in candidates:
        if source not in present:
            absent.append(source)
            continue
        note = tail[0] if tail and tail[0] else 'Thuật ngữ game đã rà theo nguồn LocalText; không tự đổi sang từ đồng nghĩa.'
        strict = mode == 'strict'
        values = by_source.get(source, [])
        if values:
            # Names already approved by key are never rewritten as generic prose terms.
            for term in values:
                if term.get('group') == 'congenital':
                    continue
                term.update(strict=strict, case_sensitive=False, domain=domain, note=note)
                updated.append(source)
            continue
        term = {'key': 'translator_reviewed_' + source.encode('utf-8').hex(),
                'source_ch': source, 'target_en': vi, 'group': 'game_terminology',
                'domain': domain, 'strict': strict, 'case_sensitive': False,
                'source_variants': [], 'note': note}
        # These words denote ordinary actions/emotions as well as combat mechanics.
        if source in ('伤害', '无敌', '流血', '沉默', '虚弱', '重伤', '穿透', '冷却'):
            term['strict_key_globs'] = ['skill*', 'effect*', 'battle*', 'GodEye*', 'spriteTalent*',
                'role_feature*', 'prefixDesc*', 'potmonSkill*', 'artifact*', 'modEffect*', 'item_desc*']
        master['terms'].append(term)
        by_source[source] = [term]
        added.append(source)
    master['terminology_review'] = {
        'source': 'TranslationTools/GeminiTranslator/game_terms_reviewed.tsv',
        'scanned_rows': len(rows), 'reviewed_sources_present': len(present),
        'not_found_in_current_source': absent,
        'policy': 'Exact names remain locked by key. Ambiguous prose terms are hints; strict terms respect scope.'}
    atomic_json(path, master)
    print('Reviewed present:', len(present), 'added:', len(added), 'updated:', len(set(updated)),
          'absent:', len(absent), 'master terms:', len(master['terms']))


if __name__ == '__main__':
    main()
