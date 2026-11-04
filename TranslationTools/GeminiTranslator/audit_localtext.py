"""Read every LocalText row and prepare a pre-translation terminology report. No API."""
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re
from translate import CJK, TOKENS, Engine, atomic_json, load_json, validate


def main():
    folder = Path(__file__).resolve().parent
    engine = Engine(folder / 'config.json')
    target = engine.root / 'Mods/Villain/patch_vh/LocalText.json'
    raw = target.read_bytes()
    rows = load_json(target)
    base = load_json(engine.root / 'Mods/Villain/base/LocalText.json')
    original = {r['key']: r for r in base}
    key_counts = Counter(r['key'] for r in rows)
    id_counts = Counter(str(r['id']) for r in rows)
    jobs = {j.game_key: j for j in engine.jobs if j.file == 'LocalText.json'}
    malformed, source_changes, syntax_differences, remaining_chinese = [], [], [], []
    exact_invalid, scope_conflicts = [], []
    coverage = Counter()
    hits, samples = Counter(), defaultdict(list)
    name_rows, quoted_rows, unprotected = [], [], []
    for row in rows:
        key, source = row['key'], row['ch']
        if set(row) != {'id', 'key', 'ch', 'en'} or not isinstance(source, str) or not isinstance(row['en'], str):
            malformed.append(key)
        if key not in original or original[key]['id'] != row['id'] or original[key]['ch'] != source:
            source_changes.append(key)
        job = jobs.get(key)
        if not job:
            continue
        if TOKENS.findall(source) != TOKENS.findall(row['en']):
            syntax_differences.append(key)
        if CJK.search(TOKENS.sub('', row['en'])):
            remaining_chinese.append(key)
        if job.exact is not None:
            coverage['exact_approved'] += 1
            try:
                validate(job, job.exact, masked=False)
            except ValueError as exc:
                exact_invalid.append({'key': key, 'ch': source, 'en': job.exact, 'error': str(exc)})
        elif not CJK.search(source):
            coverage['non_chinese'] += 1
        elif job.terms:
            coverage['context_terms'] += 1
        else:
            coverage['no_terms_needed_or_unreviewed'] += 1
        references = [r for r in job.terms if r.get('kind') == 'approved_name_reference']
        if references:
            name_rows.append(key)
        if any(r['strict'] for r in references):
            quoted_rows.append(key)
        for term in job.terms:
            hits[term['source']] += 1
            if len(samples[term['source']]) < 3:
                samples[term['source']].append(key)
        # Detect impossible literal requirements that a longer approved name supersedes.
        strict = [r for r in job.terms if r.get('strict')]
        for a in strict:
            for b in strict:
                if len(a['source']) < len(b['source']) and a['source'] in b['source'] and a['vi'].casefold() not in b['vi'].casefold():
                    scope_conflicts.append({'key': key, 'short': a['source'], 'long': b['source']})
        if CJK.search(source) and not job.terms and job.exact is None and len(source) <= 16:
            unprotected.append({'key': key, 'ch': source, 'current_en': row['en']})
    domains = Counter(t.get('domain', 'previous_approved') for t in engine.glossary)
    all_seed_errors, seed_count = [], 0
    for job in engine.jobs:
        value = job.exact if job.exact is not None else (job.source if not CJK.search(job.source) else None)
        if value is None:
            continue
        seed_count += 1
        try:
            validate(job, value, masked=False)
        except ValueError as exc:
            all_seed_errors.append({'file': job.file, 'key': job.game_key, 'error': str(exc)})
    report = {
        'scanned_rows': len(rows), 'base_rows': len(base),
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'api_calls': 0,
        'game_file_modified': False,
        'duplicate_keys': [k for k, n in key_counts.items() if n > 1],
        'duplicate_ids': [k for k, n in id_counts.items() if n > 1],
        'malformed_rows': malformed, 'ch_or_identity_differences_from_base': source_changes,
        'glossary_rules': len(engine.glossary), 'domains': dict(domains), 'coverage': dict(coverage),
        'exact_validation_errors': exact_invalid, 'nested_constraint_candidates': scope_conflicts,
        'all_files_seed_validation': {'items': seed_count, 'errors': all_seed_errors},
        'approved_name_references': {'unique_unambiguous_sources': len(engine.name_references.entries),
            'rows': len(name_rows), 'quoted_name_rows': len(quoted_rows),
            'ambiguous_sources': engine.name_references.ambiguous},
        'current_translation': {'syntax_or_number_differences': syntax_differences,
            'remaining_chinese': remaining_chinese,
            'note': 'Current en is not retranslated. Differences are diagnostic, not automatically repaired.'},
        'term_frequency': [{'ch': term, 'rows': count, 'sample_keys': samples[term]}
                           for term, count in hits.most_common()],
        'short_uncovered_rows': unprotected,
    }
    output = engine.root / 'TranslationExports/TerminologyPreflight'
    atomic_json(output / 'audit.json', report)
    atomic_json(output / 'all_files_seed_validation.json', report['all_files_seed_validation'])
    lines = ['# Rà soát thuật ngữ LocalText trước khi dịch', '',
             f'- Đã đọc {len(rows):,} bản ghi; không gọi API, không sửa file game.',
             f'- Glossary: {len(engine.glossary):,} quy tắc; các tên theo key vẫn được nạp riêng.',
             f'- Khớp bản dịch đã duyệt: {coverage["exact_approved"]:,} dòng.',
             f'- Dòng có thuật ngữ/ngữ cảnh: {coverage["context_terms"]:,}.',
             f'- Dòng có tham chiếu tên đã duyệt: {len(name_rows):,}; tên trong trích dẫn: {len(quoted_rows):,}.',
             f'- Lỗi kiểm tra bản duyệt: {len(exact_invalid)}.',
             f'- Kiểm tra toàn bộ 7 file: {seed_count:,} mục dùng thẳng bản duyệt/nguồn không Hán; {len(all_seed_errors)} lỗi.',
             f'- Khác nguồn ch/id/key so với base: {len(source_changes)}.', '',
             'Báo cáo chi tiết audit.json chứa nguồn tên đa nghĩa không được tự khóa toàn cục, '
             'các khác biệt biến/số liệu trong en cũ và các nhãn ngắn chưa có thuật ngữ. '
             'Không coi kiểm tra cấu trúc hoặc mức phủ thuật ngữ là bảo đảm đúng nghĩa toàn bộ bản dịch.', '',
             '| Nhóm | Quy tắc |', '|---|---:|']
    lines += [f'| {domain} | {count} |' for domain, count in sorted(domains.items())]
    (output / 'README.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    assert target.read_bytes() == raw, 'LocalText changed during audit'
    print('Rows:', len(rows), 'glossary:', len(engine.glossary), 'coverage:', dict(coverage))
    print('Exact errors:', len(exact_invalid), 'source differences:', len(source_changes),
          'nested candidates:', len(scope_conflicts), 'name references:', len(name_rows))
    print('Report:', output / 'audit.json')
    return 2 if (malformed or source_changes or exact_invalid or all_seed_errors or scope_conflicts
                 or any(n > 1 for n in key_counts.values()) or any(n > 1 for n in id_counts.values())) else 0


if __name__ == '__main__':
    raise SystemExit(main())
