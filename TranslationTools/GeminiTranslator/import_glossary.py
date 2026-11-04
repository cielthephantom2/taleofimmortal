"""Import approved terms, retaining custom context-specific senses."""
import json
from pathlib import Path

folder = Path(__file__).resolve().parent
source = folder.parents[1] / 'TranslationExports/danh_sach_dong_bo.json'
target = folder / 'glossary.json'
old = json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else {'terms': []}
terms = []
for term in json.loads(source.read_text(encoding='utf-8-sig'))['terms']:
    imported = {
        'id': 'import:' + term['key'],
        'source': term.get('source_ch', term.get('source_tc')),
        'vi': term['target_en'],
        'strict': term.get('strict', term.get('group') == 'congenital'),
        'case_sensitive': term.get('case_sensitive', True),
        'variants': term.get('source_variants', []),
        'note': term.get('note') or ('Tên riêng khí vận: giữ đúng tên và viết hoa.' if term.get('group') == 'congenital'
                 else 'Nhãn thuật ngữ đã duyệt; khi nằm trong câu, dùng đúng nghĩa và ngữ pháp.')
    }
    for field in ('files', 'key_globs', 'strict_key_globs', 'domain'):
        if field in term:
            imported[field] = term[field]
    terms.append(imported)
terms += [t for t in old['terms'] if not t.get('id', '').startswith('import:')]
data = {'version': 1, 'description': 'Thuật ngữ đã duyệt; quy tắc files/key_globs ghi đè nghĩa toàn cục của cùng source.',
        'terms': terms}
temporary = target.with_name(target.name + '.import.tmp')
with temporary.open('x', encoding='utf-8') as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
temporary.replace(target)
print('Imported approved terms:', len(terms), '->', target)
