"""Fast source matching and conservative references to approved names."""
from collections import defaultdict, deque
import re


class Matcher:
    def __init__(self, words):
        self.nodes, self.fail, self.out = [{}], [0], [[]]
        for word in sorted(set(words)):
            if not word:
                raise ValueError('Empty terminology source')
            node = 0
            for ch in word:
                if ch not in self.nodes[node]:
                    self.nodes[node][ch] = len(self.nodes)
                    self.nodes.append({}); self.fail.append(0); self.out.append([])
                node = self.nodes[node][ch]
            self.out[node].append(word)
        queue = deque(self.nodes[0].values())
        while queue:
            node = queue.popleft()
            for ch, child in self.nodes[node].items():
                queue.append(child)
                fallback = self.fail[node]
                while fallback and ch not in self.nodes[fallback]:
                    fallback = self.fail[fallback]
                self.fail[child] = self.nodes[fallback].get(ch, 0)
                self.out[child].extend(self.out[self.fail[child]])

    def find(self, text):
        node = 0
        for end, ch in enumerate(text, 1):
            while node and ch not in self.nodes[node]:
                node = self.fail[node]
            node = self.nodes[node].get(ch, 0)
            for word in self.out[node]:
                yield end-len(word), end, word


class NameReferences:
    def __init__(self, names):
        grouped = defaultdict(lambda: defaultdict(list))
        for entry in names:
            ch, vi = entry['ch'].strip(), entry['en'].strip()
            if not 2 <= len(ch) <= 48 or not re.fullmatch(r'[\u3400-\u9fff·・]+', ch):
                continue
            if not vi or re.search(r'[\u3400-\u9fff]', vi):
                continue
            grouped[ch][vi.casefold()].append(entry)
        self.ambiguous = {ch: sorted({r['en'].strip() for values in targets.values() for r in values})
                          for ch, targets in grouped.items() if len(targets) > 1}
        self.entries = {ch: next(iter(targets.values()))[0] for ch, targets in grouped.items()
                        if len(targets) == 1}
        self.matcher = Matcher(self.entries)

    def matches(self, text):
        found = []
        for start, end, ch in self.matcher.find(text):
            quoted = bool(re.search(r'[《【「“"‘\']\s*$', text[:start]) and
                          re.match(r'\s*[》】」”"’\']', text[end:]))
            if len(ch) < 3 and not quoted:
                continue
            found.append((start, end, ch, quoted))
        # A short skill name inside a longer item name is not a second reference.
        selected, position = [], -1
        for match in sorted(found, key=lambda m: (m[0], -(m[1]-m[0]))):
            if match[0] >= position:
                selected.append(match)
                position = match[1]
        return selected

    def rules(self, text, existing):
        result, seen = [], set(existing)
        for _, _, ch, quoted in self.matches(text):
            if ch in seen:
                continue
            seen.add(ch)
            entry = self.entries[ch]
            result.append({'source': ch, 'vi': entry['en'].strip(), 'strict': quoted or text == ch,
                           'case_sensitive': True, 'reference_key': entry['key'],
                           'kind': 'approved_name_reference',
                           'note': ('Tên đã duyệt được gọi trong dấu trích dẫn: giữ nguyên tên.' if quoted else
                                    'Nếu cụm này gọi tên vật phẩm/kỹ năng/khí vận, dùng tên đã duyệt; '
                                    'nếu chỉ là thành ngữ/miêu tả thông thường, dịch nghĩa theo câu, không ép thành tên riêng.')})
        return result
