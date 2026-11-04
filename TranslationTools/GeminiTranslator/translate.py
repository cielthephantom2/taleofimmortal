"""Resumable Chat Completions localization. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fnmatch
import hashlib
import http.client
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import socket
import sqlite3
import ssl
import sys
import threading
import time
from urllib import error, parse, request
import uuid
from terminology import Matcher, NameReferences

VERSION = 1
CJK = re.compile(r'[\u3400-\u9fff]')
# Preserve engine syntax, newline layout and numeric values before sending text to the model.
TOKENS = re.compile(
    r'\(\*｀皿´\*\)ﾉ?|<[^>\n]+>|\{[^{}\n]*\}|\$[^$\n]+\$|&[A-Za-z0-9_][^&\r\n]*&|\|[A-Za-z0-9_+*/.:\-]+\||\|'
    r'|\\[nrt]|\r\n|\r|\n|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[sdifug](?![^\W\d_])'
    r'|[+\u2212-][ \t]*(?=\d)|\d+(?:[.,]\d+)*(?:[%％])?'
)
MARKER = re.compile(r'__GGBH_P\d{4,}__')
STOP = threading.Event()
PRINT_LOCK = threading.Lock()


def log(message):
    with PRINT_LOCK:
        print(datetime.now().strftime('%H:%M:%S'), message, flush=True)


def connection_error_reason(exc, timeout):
    cause = exc.reason if isinstance(exc, error.URLError) else exc
    if isinstance(cause, TimeoutError):
        return f'Hết thời gian chờ {timeout}s'
    if isinstance(cause, json.JSONDecodeError):
        return f'JSON từ API bị lỗi (dòng {cause.lineno}, cột {cause.colno})'
    if isinstance(cause, UnicodeDecodeError):
        return 'Phản hồi API sai mã hóa'
    if isinstance(cause, socket.gaierror):
        return 'Không tìm được địa chỉ máy chủ (DNS)'
    if isinstance(cause, ssl.SSLError):
        return 'Lỗi kết nối bảo mật TLS/SSL'
    if isinstance(cause, http.client.IncompleteRead):
        return 'Phản hồi bị ngắt giữa chừng'
    if isinstance(cause, ConnectionRefusedError):
        return 'Máy chủ từ chối kết nối'
    if isinstance(cause, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
                          http.client.RemoteDisconnected)):
        return 'Máy chủ ngắt kết nối'
    if isinstance(cause, OSError):
        code = getattr(cause, 'winerror', None) or cause.errno
        return f'Lỗi kết nối (mã {code})' if code else 'Lỗi kết nối tới API'
    if isinstance(cause, ValueError):
        return 'API trả JSON sai cấu trúc'
    return 'Không kết nối được tới API'


def validation_error_summary(reasons):
    counts = Counter()
    for reason in reasons:
        if 'giữ chỗ' in reason or 'Mã game' in reason:
            label = 'sai mã/số/xuống dòng'
        elif 'chữ Hán' in reason:
            label = 'còn chữ Hán'
        elif 'Tên riêng' in reason:
            label = 'sai thuật ngữ'
        elif 'Khóa' in reason:
            label = 'thiếu/trùng khóa'
        elif 'đoạn' in reason or 'Đoạn' in reason:
            label = 'sai đoạn dịch'
        elif 'token đầu ra' in reason:
            label = 'hết token đầu ra'
        elif 'Phản hồi không dùng được' in reason:
            label = 'JSON bản dịch lỗi'
        else:
            label = reason
        counts[label] += 1
    return ', '.join(f'{label} ({count})' for label, count in counts.most_common(2))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def resolve_api_key(config, folder):
    key = os.environ.get(config.get('api_key_env', 'OPENAI_API_KEY'), '').strip()
    if not key and config.get('api_key_file'):
        key = load_json(folder / config['api_key_file']).get('api_key', '').strip()
    return key


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mask(text):
    if '__GGBH_P' in text:
        raise ValueError('Nguồn chứa tiền tố mã giữ chỗ dành riêng')
    values = []
    def replace(match):
        values.append(match.group())
        return f'__GGBH_P{len(values)-1:04d}__'
    return TOKENS.sub(replace, text), values


def format_edges(job, text):
    return job.prefix + text.strip(' \t\u2009\u00a0') + job.suffix


def validate(job, translated, masked=True):
    if not isinstance(translated, str) or (job.source.strip() and not translated.strip()):
        raise ValueError('Bản dịch rỗng hoặc không phải chuỗi')
    if masked:
        _, values = mask(job.source)
        wanted = [f'__GGBH_P{i:04d}__' for i in range(len(values))]
        if MARKER.findall(translated) != wanted:
            raise ValueError('Mã giữ chỗ bị thiếu, lặp hoặc sai thứ tự')
        if CJK.search(MARKER.sub('', translated)) and job.reject_chinese:
            remaining = ''.join(sorted(set(CJK.findall(MARKER.sub('', translated)))))[:24]
            raise ValueError('Bản dịch vẫn còn chữ Hán: ' + remaining)
        for i, value in enumerate(values):
            translated = translated.replace(f'__GGBH_P{i:04d}__', value)
    if '__GGBH_P' in translated:
        raise ValueError('Mã giữ chỗ sai định dạng')
    # Explicit approved values may intentionally retain a rare source name.
    # Keep those decisions; cached/model text receives the normal CJK check.
    if job.reject_chinese and translated != job.exact and CJK.search(TOKENS.sub('', translated)):
        remaining = ''.join(sorted(set(CJK.findall(TOKENS.sub('', translated)))))[:24]
        raise ValueError('Bản dịch vẫn còn chữ Hán: ' + remaining)
    exception = job.format_exception
    approved_format = (exception is not None and exception.get('source') == job.source and
                       exception.get('vi') == translated)
    if TOKENS.findall(job.source) != TOKENS.findall(translated) and not approved_format:
        original = Counter(TOKENS.findall(job.source))
        actual = Counter(TOKENS.findall(translated))
        extra = list((actual-original).elements())[:6]
        missing = list((original-actual).elements())[:6]
        raise ValueError('Mã game, số liệu hoặc xuống dòng bị thay đổi; '
                         f'thừa {extra!r}, thiếu {missing!r}. '
                         'Số viết bằng chữ phải dịch bằng chữ, không tự đổi thành chữ số hay ký hiệu %.')
    for term in job.terms:
        expected = term['vi'] if term.get('case_sensitive', True) else term['vi'].casefold()
        actual = translated if term.get('case_sensitive', True) else translated.casefold()
        if term.get('strict') and expected not in actual:
            raise ValueError('Tên riêng đã duyệt không được giữ đúng: ' + term['vi'])
    return format_edges(job, translated)


@dataclass
class Job:
    key: str
    game_key: str
    file: str
    row_id: str
    source_field: str
    target_field: str
    source: str
    source_hash: str
    policy: str
    cache_key: str
    context: dict
    terms: list
    prefix: str
    suffix: str
    reject_chinese: bool
    exact: str | None = None
    format_exception: dict | None = None

    def api_item(self, segmented=False, indexed=False):
        masked, _ = mask(self.source)
        item = {'key': self.key, 'game_key': self.game_key, 'ch': masked,
                'context': self.context, 'approved_terms': [
                    {k: v for k, v in term.items() if k in
                     ('source', 'vi', 'strict', 'case_sensitive', 'kind', 'note')}
                    for term in self.terms]}
        if segmented:
            parts = MARKER.split(masked)
            if indexed:
                item['translatable_segments'] = {str(i): part for i, part in enumerate(parts) if part.strip()}
            else:
                item['ch_segments'] = parts
            # Real tags/variables identify locations, quantities and rich-text
            # boundaries that opaque marker IDs cannot explain to the model.
            item['ch_context'] = self.source
        else:
            item['required_placeholder_order'] = MARKER.findall(masked)
        return item


def response_translation(job, entry):
    if 'segments' not in entry:
        return entry.get('en')
    masked, _ = mask(job.source)
    source_parts = MARKER.split(masked)
    translated = entry['segments']
    if isinstance(translated, dict):
        expected_indices = {str(i) for i, part in enumerate(source_parts) if part.strip()}
        if set(translated) != expected_indices or any(not isinstance(value, str) for value in translated.values()):
            raise ValueError('Danh sách đoạn dịch thiếu chỉ số hoặc sai định dạng')
        translated = [translated[str(i)] if str(i) in translated else part
                      for i, part in enumerate(source_parts)]
    if (not isinstance(translated, list) or len(translated) != len(source_parts)
            or any(not isinstance(part, str) for part in translated)):
        raise ValueError('Danh sách đoạn dịch thiếu mục hoặc sai định dạng')
    translated = list(translated)
    for index, (source, target) in enumerate(zip(source_parts, translated)):
        if not source.strip() and source != target:
            if not target.strip(' \t\u2009\u00a0'):
                translated[index] = source
            else:
                raise ValueError('Đoạn trống hoặc khoảng trắng giữa mã game bị thay đổi')
        # Vietnamese places date units and verbs differently. A source suffix
        # may be absorbed into a neighbouring phrase; the reconstructed text
        # must still pass all token, terminology and nonempty checks below.
        if '__GGBH_P' in target:
            raise ValueError('Model chèn mã giữ chỗ vào đoạn chữ')
    markers = MARKER.findall(masked)
    return ''.join(part + (markers[i] if i < len(markers) else '')
                   for i, part in enumerate(translated))


def validate_candidate(job, translated):
    # Some providers return actual engine tokens instead of marker IDs. Accept
    # that representation only when the full original token sequence validates.
    masked = not (isinstance(translated, str) and '__GGBH_P' not in translated and mask(job.source)[1])
    return validate(job, translated, masked=masked)


def translation_entries(response):
    if not isinstance(response, dict):
        raise ValueError('Phản hồi API phải là đối tượng JSON')
    if 'choices' in response:
        choice = response['choices'][0]
        content = choice['message']['content']
    else:
        candidate = response.get('candidates', [])[0]
        content = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', [])
                          if not p.get('thought'))
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Nội dung API trả về rỗng hoặc không phải chuỗi')
    content = content.strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\s*\n?', '', content, count=1)
        content = re.sub(r'\s*```$', '', content)
    try:
        entries = json.loads(content)['translations']
    except json.JSONDecodeError:
        # Recover only fully decoded objects from the known root array prefix.
        # Never repair a string, invent a closing quote, or scan beyond an
        # invalid object. All decoded rows still undergo ordinary validation.
        prefix = re.match(r'\s*\{\s*"translations"\s*:\s*\[', content)
        if not prefix:
            raise
        decoder, entries, offset = json.JSONDecoder(), [], prefix.end()
        while offset < len(content):
            while offset < len(content) and content[offset].isspace():
                offset += 1
            if offset >= len(content) or content[offset] == ']':
                break
            try:
                entry, end = decoder.raw_decode(content, offset)
            except json.JSONDecodeError:
                break
            delimiter = end
            while delimiter < len(content) and content[delimiter].isspace():
                delimiter += 1
            if delimiter < len(content) and content[delimiter] not in ',]':
                break
            entries.append(entry)
            if delimiter >= len(content) or content[delimiter] == ']':
                break
            offset = delimiter + 1
        if not entries:
            raise
    if not isinstance(entries, list):
        raise ValueError('Danh sách bản dịch trả về sai định dạng')
    return entries


def normalize_wire_response(response, wire_keys):
    if not wire_keys:
        return response
    try:
        entries = copy.deepcopy(translation_entries(response))
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get('key'), str):
                entry['key'] = wire_keys.get(entry['key'], entry['key'])
        normalized = copy.deepcopy(response)
        normalized['choices'][0]['message']['content'] = json.dumps(
            {'translations': entries}, ensure_ascii=False)
        return normalized
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return response


def validate_response(jobs, response):
    expected = {j.key: j for j in jobs}
    good, bad = [], []
    try:
        entries = translation_entries(response)
        matched = []
        for entry in entries:
            # Unknown/malformed rows must not discard unrelated valid rows.
            if not isinstance(entry, dict) or not isinstance(entry.get('key'), str):
                continue
            key = entry['key']
            if key not in expected:
                # Accept JSON whitespace/escaping differences only. Never guess
                # another row from an ID, game key, fuzzy match or array position.
                try:
                    identity = json.loads(key)
                    key = json.dumps(identity, ensure_ascii=False, separators=(',', ':'))
                except (ValueError, TypeError):
                    continue
            if key in expected:
                matched.append((key, entry))
        counts = Counter(key for key, _ in matched)
        mapped = dict(matched)
        for key, job in expected.items():
            try:
                if counts[key] != 1:
                    raise ValueError('Khóa bản dịch bị thiếu hoặc lặp')
                good.append((job, validate_candidate(job, response_translation(job, mapped[key]))))
            except (ValueError, TypeError) as exc:
                bad.append((job, str(exc)))
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        bad = [(job, 'Phản hồi không dùng được: ' + str(exc)) for job in jobs]
        good = []
    return good, bad


class Store:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'journal').mkdir(exist_ok=True)
        self.path = directory / 'progress.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS results (
                    key TEXT, source_hash TEXT, policy TEXT, vi TEXT, status TEXT,
                    error TEXT, updated TEXT, PRIMARY KEY(key,source_hash,policy));
                CREATE TABLE IF NOT EXISTS memory (signature TEXT PRIMARY KEY, vi TEXT);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, model TEXT, usage TEXT, valid INTEGER, invalid INTEGER);
                CREATE TABLE IF NOT EXISTS applied (
                    key TEXT PRIMARY KEY, source_hash TEXT, policy TEXT, vi TEXT);
                CREATE TABLE IF NOT EXISTS conflicts (key TEXT PRIMARY KEY, reason TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=60)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def ready(self, jobs):
        jobs = list(jobs)
        with self.connect() as db:
            if len(jobs) <= 500:
                # The primary key already indexes (key, source_hash, policy).
                # Avoid copying every saved translation for a small batch.
                found = {}
                for job in jobs:
                    row = db.execute("SELECT vi FROM results WHERE key=? AND source_hash=? "
                                     "AND policy=? AND status='done'",
                                     (job.key, job.source_hash, job.policy)).fetchone()
                    if row is not None:
                        found[job.key] = row[0]
                return found
            values = {(k, s, p): v for k, s, p, v in db.execute(
                "SELECT key,source_hash,policy,vi FROM results WHERE status='done'")}
        return {j.key: values[(j.key, j.source_hash, j.policy)] for j in jobs
                if (j.key, j.source_hash, j.policy) in values}

    def memories(self):
        with self.connect() as db:
            return dict(db.execute('SELECT signature,vi FROM memory'))

    def checked_ready(self, jobs):
        ready = self.ready(jobs)
        invalid = []
        for job in jobs:
            if job.key not in ready:
                continue
            try:
                validate(job, ready[job.key], masked=False)
            except ValueError as exc:
                invalid.append((job, ready.pop(job.key), str(exc)))
        if invalid:
            # Preserve the old values before removing only invalid cache entries.
            atomic_json(self.directory / 'cache_review' / (uuid.uuid4().hex + '.json'), [
                {'job': asdict(j), 'previous_vi': vi, 'error': reason}
                for j, vi, reason in invalid])
            with self.connect() as db:
                for job, _, reason in invalid:
                    db.execute("UPDATE results SET status='failed',error=? "
                               'WHERE key=? AND source_hash=? AND policy=?',
                               (reason, job.key, job.source_hash, job.policy))
                    db.execute('DELETE FROM memory WHERE signature=?', (job.cache_key,))
            log(f'Cần dịch lại {len(invalid):,} mục cũ không qua kiểm tra; đã sao lưu vào state/cache_review.')
        return ready

    def failures(self, jobs, include_previous_policies=False):
        jobs = list(jobs)
        with self.connect() as db:
            if include_previous_policies:
                rows = list(db.execute("SELECT key,source_hash,policy,error FROM results "
                                       "WHERE status!='done' ORDER BY updated"))
                current = {(k, s, p): message for k, s, p, message in rows}
                previous = {(k, s): message for k, s, _, message in rows}
                return {j.key: current.get((j.key, j.source_hash, j.policy),
                                          previous[(j.key, j.source_hash)])
                        for j in jobs if (j.key, j.source_hash) in previous}
            if len(jobs) > 500:
                saved = {(k, s, p): message for k, s, p, message in db.execute(
                    "SELECT key,source_hash,policy,error FROM results WHERE status!='done'")}
                return {j.key: saved[(j.key, j.source_hash, j.policy)] for j in jobs
                        if (j.key, j.source_hash, j.policy) in saved}
            result = {}
            for job in jobs:
                row = db.execute("SELECT error FROM results WHERE key=? AND source_hash=? "
                                 "AND policy=? AND status!='done'",
                                 (job.key, job.source_hash, job.policy)).fetchone()
                if row is not None:
                    result[job.key] = row[0]
            return result

    def save(self, pairs, errors=()):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            for job, vi in pairs:
                db.execute('INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?)',
                           (job.key, job.source_hash, job.policy, vi, 'done', '', now))
                db.execute('INSERT OR REPLACE INTO memory VALUES (?,?)', (job.cache_key, vi))
            for job, reason in errors:
                # A later failed duplicate must never downgrade an already accepted result.
                db.execute('INSERT INTO results VALUES (?,?,?,?,?,?,?) '
                           'ON CONFLICT(key,source_hash,policy) DO UPDATE SET error=excluded.error '
                           "WHERE results.status!='done'",
                           (job.key, job.source_hash, job.policy, '', 'failed', reason, now))

    def accept_response(self, jobs, response, request_id, model):
        good, bad = validate_response(jobs, response)
        self.save(good, bad)
        usage = response.get('usage', response.get('usageMetadata', {})) if isinstance(response, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO requests VALUES (?,?,?,?,?)',
                       (request_id, model, json.dumps(usage), len(good), len(bad)))
        return [j for j, _ in good], [j for j, _ in bad]

    def recover(self):
        with self.connect() as db:
            processed = {r[0] for r in db.execute('SELECT id FROM requests')}
        recovered = 0
        for path in sorted((self.directory / 'journal').glob('*.json')):
            if path.stem in processed:
                continue
            record = load_json(path)
            if record.get('version') != VERSION:
                raise ValueError('Phiên bản nhật ký khác công cụ; giữ nguyên tiến độ và dùng đúng phiên bản công cụ')
            jobs = [Job(**j) for j in record['jobs']]
            response = normalize_wire_response(record['response'], record.get('wire_keys', {}))
            self.accept_response(jobs, response, path.stem, record['model'])
            recovered += 1
        if recovered:
            log(f'[KHÔI PHỤC] Đã xử lý lại {recovered} phản hồi đã lưu; không cần gọi lại API.')


class Limiter:
    def __init__(self, rpm):
        self.rpm = rpm
        self.calls = deque()
        self.lock = threading.Lock()
        self.cooldown = 0.0

    def take(self):
        while not STOP.is_set():
            with self.lock:
                now = time.monotonic()
                while self.calls and self.calls[0] <= now - 60:
                    self.calls.popleft()
                delay = max(0, self.cooldown - now)
                if self.rpm and len(self.calls) >= self.rpm:
                    delay = max(delay, self.calls[0] + 60 - now)
                if delay <= 0:
                    self.calls.append(now)
                    return
            STOP.wait(min(delay, 1))
        raise InterruptedError('Đã dừng')

    def backoff(self, seconds):
        with self.lock:
            self.cooldown = max(self.cooldown, time.monotonic() + seconds)


class FatalAPIError(RuntimeError):
    pass


class ChatCompletions:
    def __init__(self, config, style, key, store):
        self.cfg, self.style, self.key, self.store = config, style, key, store
        self.limiter = Limiter(config['requests_per_minute'])
        self.schema = {
            'type': 'object', 'properties': {'translations': {
                'type': 'array', 'items': {'type': 'object', 'properties': {
                    'key': {'type': 'string'}, 'en': {'type': 'string'}}, 'required': ['key', 'en']}}},
            'required': ['translations']}

    def call(self, jobs, feedback=None, segmented=False):
        wire_keys = {f'k{i:04d}': job.key for i, job in enumerate(jobs)}
        wire_by_key = {key: wire for wire, key in wire_keys.items()}
        items = []
        for job in jobs:
            item = job.api_item(segmented=segmented, indexed=segmented)
            item['key'] = wire_by_key[job.key]
            items.append(item)
        feedback = {wire_by_key.get(key, key): value for key, value in (feedback or {}).items()}
        schema = self.schema
        instruction = ('Translate every item from ch into Vietnamese en, preserving its key. '
                       'Copy all placeholder tokens exactly in required_placeholder_order. '
                       'Never reorder tagged phrases even to make Vietnamese more natural. '
                       'Do not introduce new numbers or line breaks. '
                       'Chinese numbers written as words MUST remain Vietnamese words: '
                       '一层 = một tầng, 一次 = một lần, 两个 = hai; NEVER write 1 or 2 for them.')
        if segmented:
            schema = {'type': 'object', 'properties': {'translations': {
                'type': 'array', 'items': {'type': 'object', 'properties': {
                    'key': {'type': 'string'},
                    'segments': {'type': 'object', 'additionalProperties': {'type': 'string'}}},
                    'required': ['key', 'segments']}}}, 'required': ['translations']}
            instruction = (
                'Translate translatable_segments into a Vietnamese segments OBJECT with EXACTLY the same index keys. '
                'Each index is the fixed position of that text between game tokens. Never renumber indices. '
                'Empty/whitespace-only positions are managed by the program and are NOT sent; do not create them. '
                'Read the whole ch for context, but translate each segment at its original index. '
                'Read ch_context to identify what each variable represents (areaName is a LOCATION, '
                'not an object to collect), and determine the subject, object, negation and conditions '
                'of the COMPLETE sentence before translating any segment. '
                'For Chinese A内的B or A区域内的B, B is INSIDE A. Never reverse that containment: '
                'translate the link between them as ", tại " or ", ở ", NOT "nằm trong" or '
                '"trong khu vực" after A, which would wrongly put A inside B. '
                'Return key and segments only, not en. The program inserts all game tokens between segments. '
                'NEVER output placeholder tokens, tags, new line breaks or new numeric values in segments. '
                'Do not merge, split, omit or reorder indexed segments. '
                'Keep each segment\'s nouns, verbs and time units at the SAME index. '
                'Do not move a damage increase into the segment before a duration token. '
                'Example {"0":"将在","1":"秒内提升","2":"%造成的伤害"} becomes '
                '{"0":"trong vòng ","1":" giây sẽ tăng ","2":"% sát thương gây ra"}. '
                'Example {"0":"可为场上随机","1":"个敌人叠加一层","2":"。"} becomes '
                '{"0":"có thể khiến ngẫu nhiên ","1":" kẻ địch trên sân được cộng dồn một tầng ","2":"."}. '
                'Chinese numeral words must become Vietnamese WORDS: 一层 = một tầng, 一次 = một lần. '
                '第一期 = kỳ đầu tiên, 十万元 = mười vạn tệ, 一百 = một trăm. '
                'Inside translated segment VALUES, numeric digits may NEVER occur: original digits are all stored '
                'outside segments by the program; numeric index KEYS must be copied unchanged. '
                'Use Vietnamese words for every number written in Chinese. '
                '上一百个 = một trăm mục trước; 百分之 followed by a numeric token must use '
                'the SAME token followed by the words "phần trăm", not append a new % symbol. '
                'Never introduce digits 1, 2, etc. when the source uses Chinese numeral words. '
                'Grammar-only suffixes such as 年/月/日 or 的事件 may be empty if their meaning is already '
                'expressed before the token. Do not drop actual information. '
                'For nonempty translated segments, INCLUDE leading/trailing spaces needed around adjacent '
                'tags, words and variables. Never trim each segment separately. '
                'Keep the meaning of each segment local to that index, even if the sentence is less natural. '
                'Use approved_terms consistently across the whole sentence. '
                'For example, 可在[AREA]内的[PLACE]中获得[ITEM] means '
                'Có thể tìm thấy tại [AREA], ở [PLACE], vật phẩm [ITEM]; '
                'never say thu thập [AREA]. Do not invent a new action before a location. '
                'Example {"0":"可在","1":"内的青云谷中获得灵石。"} around an areaName token '
                'becomes {"0":"Có thể đến ","1":", tại Thanh Vân Cốc, để nhận linh thạch."}. '
                'Before returning, read the reconstructed Vietnamese sentence with all tokens inserted '
                'and check its meaning against ch_context. '
                'Return the segments OBJECT, not an array; for example {"0":"Trước ","6":" sau"}. '
                'The rule in this task to return segments overrides any general rule about returning en.')
        body = {'temperature': self.cfg['temperature'],
                'max_tokens': self.cfg['max_output_tokens']}
        body.update(self.cfg.get('generation_overrides', {}))
        if self.cfg.get('json_mode', False):
            body['response_format'] = {'type': 'json_object'}
        # Send the same minimal Chat Completions protocol as test.py. Enforce
        # JSON locally rather than requiring gateway-specific schema support.
        body.update({'model': self.cfg['model'], 'stream': False,
                'messages': [{'role': 'system', 'content': self.style +
                    '\nReturn only a JSON object matching this schema, without Markdown: ' + json.dumps(schema) +
                    '\n' + instruction + '\nCopy the short key exactly (for example k0000). '
                    'Do not create a key from game_key, row ID or source content.'},
                    {'role': 'user', 'content': json.dumps(
                    {'task': instruction,
                     'validation_feedback': feedback or {},
                     'items': items}, ensure_ascii=False)}]})
        endpoint = self.cfg['base_url'].rstrip('/') + '/chat/completions'
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')
        request_id = uuid.uuid4().hex
        for attempt in range(self.cfg['http_retries'] + 1):
            self.limiter.take()
            try:
                req = request.Request(endpoint, data=payload, headers={
                    'Content-Type': 'application/json', 'Accept': 'application/json',
                    'Authorization': 'Bearer ' + self.key}, method='POST')
                with request.urlopen(req, timeout=self.cfg['request_timeout_seconds']) as reply:
                    result = json.load(reply)
                if not isinstance(result, dict):
                    raise ValueError('Phản hồi API phải là một đối tượng JSON')
                if result.get('error'):
                    raise FatalAPIError('API báo lỗi: kiểm tra model, khóa và cấu hình máy chủ')
            except error.HTTPError as exc:
                status = exc.code
                # Do not log request headers, API keys or the provider's echoed error body.
                if status not in (408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524):
                    raise FatalAPIError(f'HTTP {status}: kiểm tra model, khóa, quyền API và cấu hình') from None
                reason = ('Máy chủ API phản hồi quá lâu, Cloudflare đã ngắt kết nối'
                          if status == 524 else 'Lỗi tạm thời từ API hoặc gateway')
                if attempt == self.cfg['http_retries']:
                    raise RuntimeError(f'HTTP {status}: {reason}; đã hết số lần thử lại. '
                                       'Lô này được giữ để chạy lại; có thể giảm parallel_requests hoặc kích thước lô') from None
                delay = min(60, 2 ** (attempt + 1) + random.random())
                try:
                    delay = max(delay, min(300, float(exc.headers.get('Retry-After', '0'))))
                except ValueError:
                    pass
                self.limiter.backoff(delay)
                brief = {408: 'hết thời gian chờ', 429: 'quá giới hạn gọi',
                         500: 'lỗi máy chủ', 502: 'lỗi gateway', 503: 'máy chủ bận',
                         504: 'gateway hết thời gian chờ', 524: 'Cloudflare hết thời gian chờ'}
                log(f'[THỬ {attempt+1}/{self.cfg["http_retries"]}] HTTP {status}: '
                    f'{brief.get(status, "lỗi gateway")} | {len(jobs)} mục | chờ {delay:.0f}s.')
                continue
            except (error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException) as exc:
                reason = connection_error_reason(exc, self.cfg['request_timeout_seconds'])
                if attempt == self.cfg['http_retries']:
                    raise RuntimeError(reason + '; đã hết số lần thử lại') from None
                delay = min(60, 2 ** (attempt + 1) + random.random())
                log(f'[THỬ {attempt+1}/{self.cfg["http_retries"]}] {reason} | {len(jobs)} mục | chờ {delay:.0f}s.')
                if STOP.wait(delay):
                    raise InterruptedError('Đã dừng')
                continue
            # Do not retry a billable request when the failure is local disk I/O.
            atomic_json(self.store.directory / 'journal' / (request_id + '.json'), {
                'version': VERSION, 'model': self.cfg['model'],
                'jobs': [asdict(j) for j in jobs], 'wire_keys': wire_keys,
                'mask_pattern': TOKENS.pattern, 'response': result})
            return normalize_wire_response(result, wire_keys), request_id
        raise RuntimeError('Không nhận được phản hồi')

    def translate(self, jobs, depth=0):
        if STOP.is_set():
            return []
        try:
            feedback = self.store.failures(jobs, include_previous_policies=True)
            if feedback:
                feedback['instruction'] = ('Correct the validation errors from the previous attempt. '
                    'Use Vietnamese Latin script in en, with no remaining Chinese characters. '
                    'Preserve all placeholder tokens and approved names exactly.')
            segmented = any(len(mask(j.source)[1]) > 1 for j in jobs)
            response, request_id = self.call(jobs, feedback, segmented=segmented)
        except (FatalAPIError, InterruptedError):
            raise
        except RuntimeError as exc:
            self.store.save([], [(j, str(exc)) for j in jobs])
            log(f'[LỖI LÔ] {len(jobs)} mục chưa dịch được: {exc}')
            return []
        good, bad = self.store.accept_response(jobs, response, request_id, self.cfg['model'])
        if bad and depth < self.cfg['validation_retries'] and not STOP.is_set():
            # Retry only invalid/missing keys, with smaller batches to reduce truncation.
            midpoint = max(1, len(bad) // 2)
            for start in range(0, len(bad), midpoint):
                good.extend(self.translate(bad[start:start+midpoint], depth + 1))
        return good


class Engine:
    def __init__(self, config_path, limit=0):
        self.config_path = config_path.resolve()
        self.folder = self.config_path.parent
        self.cfg = load_json(self.config_path)
        c = self.cfg
        endpoint = parse.urlsplit(c.get('base_url', ''))
        if endpoint.scheme not in ('http', 'https') or not endpoint.netloc or endpoint.query or endpoint.fragment:
            raise ValueError('base_url phải là URL gốc HTTP(S), ví dụ https://host/v1')
        if not isinstance(c['batch_size'], int) or not 1 <= c['batch_size'] <= 1000:
            raise ValueError('batch_size phải từ 1 đến 1000')
        for key in ('parallel_requests', 'request_timeout_seconds', 'max_source_characters_per_batch', 'max_output_tokens'):
            if not isinstance(c[key], int) or c[key] < 1:
                raise ValueError(key + ' phải là số nguyên dương')
        for key in ('http_retries', 'validation_retries', 'requests_per_minute'):
            if not isinstance(c[key], int) or c[key] < 0:
                raise ValueError(key + ' phải là số nguyên không âm')
        self.root = (self.folder / c['game_root']).resolve()
        self.state = (self.folder / c['state_directory']).resolve()
        self.style = (self.folder / c['style_file']).read_text(encoding='utf-8-sig')
        self.glossary = load_json(self.folder / c['glossary_file'])['terms']
        self.rule_index = defaultdict(list)
        for rule in self.glossary:
            if not isinstance(rule.get('source'), str) or not rule['source'] or not rule.get('vi'):
                raise ValueError('Quy tắc thuật ngữ rỗng hoặc không hợp lệ')
            for spelling in [rule['source'], *rule.get('variants', [])]:
                if not isinstance(spelling, str) or not spelling:
                    raise ValueError('Biến thể thuật ngữ rỗng hoặc không hợp lệ')
                self.rule_index[spelling].append(rule)
        self.rule_matcher = Matcher(self.rule_index)
        self.name_fragments = {}
        if c.get('name_fragments_file'):
            for entry in load_json(self.folder / c['name_fragments_file'])['entries']:
                identity = (entry['file'], str(entry['id']), entry['key'])
                self.name_fragments[identity] = entry
        self.item_names = {}
        if c.get('item_names_file'):
            self.item_names = {entry['key']: entry for entry in load_json(self.folder / c['item_names_file'])['entries']}
        if c.get('skill_fate_names_file'):
            self.item_names.update({entry['key']: entry for entry in load_json(self.folder / c['skill_fate_names_file'])['entries']})
        self.name_references = NameReferences(self.item_names.values())
        self.format_exceptions = {}
        if c.get('approved_format_exceptions_file'):
            for entry in load_json(self.folder / c['approved_format_exceptions_file'])['entries']:
                identity = (entry['file'], entry['key'])
                if identity in self.format_exceptions:
                    raise ValueError('Ngoại lệ định dạng đã duyệt bị trùng: ' + str(identity))
                self.format_exceptions[identity] = entry
        self.base_policy = digest({'version': VERSION, 'model': c['model'], 'style': self.style,
                                   'api_protocol': 'chat-completions-v1',
                                   'temperature': c['temperature'], 'generation': c.get('generation_overrides', {}),
                                   'reject_chinese': c['reject_remaining_chinese']})
        self.jobs = []
        self.expected = {}
        self.specs = {}
        self.conflicts = {}
        self.run_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        for spec in c['files']:
            path = (self.root / spec['path']).resolve()
            path.relative_to(self.root)
            name = path.name
            if name in self.specs:
                raise ValueError('Tên file trong cấu hình không được trùng nhau')
            self.specs[name] = (path, spec)
            rows = load_json(path)
            if not isinstance(rows, list):
                raise ValueError(name + ': dữ liệu phải là mảng JSON')
            identities = set()
            for row in rows:
                row_id = str(row[spec['id_field']])
                if row_id in identities:
                    raise ValueError(name + ': ID dòng bị trùng ' + row_id)
                identities.add(row_id)
                game_key = str(row.get(spec.get('key_field', ''), row_id))
                if spec.get('include_key_globs') and not any(fnmatch.fnmatchcase(game_key, p) for p in spec['include_key_globs']):
                    continue
                if any(fnmatch.fnmatchcase(game_key, p) for p in spec.get('exclude_key_globs', [])):
                    continue
                for source_field, target_field in spec['fields'].items():
                    source = row[source_field]
                    if not isinstance(source, str) or not isinstance(row[target_field], str):
                        raise ValueError(name + ': nguồn và đích phải là chuỗi')
                    key = json.dumps([name, row_id, game_key, target_field], ensure_ascii=False, separators=(',', ':'))
                    context = {'file': name, 'key': game_key, 'source_field': source_field,
                               'category': re.sub(r'\d+', '#', game_key),
                               'metadata': {k: row[k] for k in spec.get('context_fields', []) if k in row}}
                    if name in ('NpcNameFirst.json', 'NpcNameLast.json', 'BattleSkillPrefixName.json'):
                        context['category'] = name + ':' + source_field
                        context['metadata'] = {k: row[k] for k in ('gender', 'index') if k in row}
                    rules = self.rules(name, game_key, source)
                    fragment = self.name_fragments.get((name, row_id, game_key))
                    if fragment and fragment['source'] != source:
                        raise ValueError(f'Nguồn mảnh tên đã thay đổi: {name}:{game_key}; cần duyệt lại âm Hán–Việt trước')
                    if fragment:
                        rules = [{'source': source, 'vi': fragment['vi'], 'strict': True,
                                  'note': 'Mảnh ghép tên đã duyệt: bắt buộc Hán–Việt, không dịch nghĩa thuần Việt.'}]
                    approved_item = self.item_names.get(game_key) if name == 'LocalText.json' else None
                    if approved_item:
                        if approved_item['ch'] != source:
                            raise ValueError(f'Nguồn tên đã duyệt đã thay đổi: {game_key}; cần duyệt lại tên trước')
                        rules = [{'source': source, 'vi': approved_item['en'], 'strict': True,
                                  'note': 'Tên vật phẩm đã duyệt: tên riêng Hán–Việt, tên mô tả dịch rõ nghĩa.'}]
                    exact = {r['vi'] for r in rules if r.get('allow_exact', True) and
                             source in [r['source'], *r.get('variants', [])]}
                    if len(exact) > 1:
                        raise ValueError(f'Nghĩa thuật ngữ xung đột ở {name}:{game_key}')
                    prefix = suffix = ''
                    if c['preserve_target_edge_whitespace']:
                        current = row[target_field]
                        prefix = re.match(r'^[ \t\u2009\u00a0]*', current).group()
                        suffix = re.search(r'[ \t\u2009\u00a0]*$', current).group()
                        if not current.strip(' \t\u2009\u00a0'):
                            prefix = suffix = ''
                    format_exception = self.format_exceptions.get((name, game_key))
                    if format_exception and format_exception['source'] != source:
                        raise ValueError('Nguồn ngoại lệ định dạng đã thay đổi: ' + game_key)
                    policy = digest([self.base_policy, rules, prefix, suffix, format_exception, 'terminology-context-v2'])
                    semantic = {k: v for k, v in context.items() if k != 'key'}
                    signature = digest([source, semantic, policy]) if c['deduplicate_within_context'] else digest([key, source, policy])
                    self.jobs.append(Job(key, game_key, name, row_id, source_field, target_field,
                                         source, digest(source), policy, signature, context, rules,
                                         prefix, suffix, c['reject_remaining_chinese'], next(iter(exact), None), format_exception))
                    self.expected[key] = row[target_field]
        if limit:
            self.jobs = self.jobs[:limit]
        self.by_key = {j.key: j for j in self.jobs}
        assert len(self.by_key) == len(self.jobs)

    def rules(self, name, key, source):
        matched = []
        seen = set()
        for spelling in sorted({word for _, _, word in self.rule_matcher.find(source)}):
            for rule in self.rule_index[spelling]:
                identity = id(rule)
                if identity in seen:
                    continue
                seen.add(identity)
                if rule.get('files') and not any(fnmatch.fnmatchcase(name, p) for p in rule['files']):
                    continue
                if rule.get('key_globs') and not any(fnmatch.fnmatchcase(key, p) for p in rule['key_globs']):
                    continue
                excluded_spans = [(m.start(), m.end())
                                  for phrase in [*rule.get('exclude_within', []), *rule.get('context_exclusions', [])]
                                  for m in re.finditer(re.escape(phrase), source)]
                if excluded_spans:
                    occurrences = list(re.finditer(re.escape(spelling), source))
                    if occurrences and all(any(a <= m.start() and m.end() <= b
                                               for a, b in excluded_spans) for m in occurrences):
                        continue
                selected = {k: v for k, v in rule.items()
                            if k not in ('context_exclusions', 'context_advisory_key_globs')}
                advisory = any(fnmatch.fnmatchcase(key, p) for p in rule.get('context_advisory_key_globs', []))
                quoted = bool(re.search(r'[《【「“"‘\']\s*' + re.escape(spelling) + r'\s*[》】」”"’\']', source))
                if advisory and not quoted:
                    selected = {**selected, 'strict': False, 'allow_exact': False,
                                'note': 'Cụm này mang nghĩa thông thường trong câu; không ép thành tên khí vận.'}
                if rule.get('strict_key_globs') and not any(fnmatch.fnmatchcase(key, p) for p in rule['strict_key_globs']):
                    selected = {**selected, 'strict': False}
                matched.append(selected)
        # Specialized senses override the global sense of the same source term.
        special = {r['source'] for r in matched if r.get('key_globs') or r.get('files')}
        chosen = [r for r in matched if r['source'] not in special or r.get('key_globs') or r.get('files')]
        senses = defaultdict(set)
        for rule in chosen:
            senses[rule['source']].add(rule['vi'])
        if any(len(values) > 1 for values in senses.values()):
            raise ValueError(f'Phạm vi thuật ngữ chưa rõ ở {name}:{key}; cần thu hẹp files/key_globs')
        full = [r for r in chosen if source in [r['source'], *r.get('variants', [])]]
        if full:
            return full
        # Suppress nested constraints: a longer canonical phrase owns its spelling.
        # E.g. 'contribution points' must not also require a second translation of 'points'.
        def shadowed(short, long):
            if not short.get('strict') or len(short['source']) >= len(long['source']):
                return False
            if short['source'] not in long['source'] or short['vi'].casefold() in long['vi'].casefold():
                return False
            containers = [(m.start(), m.end()) for m in re.finditer(re.escape(long['source']), source)]
            occurrences = [(m.start(), m.end()) for m in re.finditer(re.escape(short['source']), source)]
            return bool(occurrences) and all(any(a <= start and end <= b for a, b in containers)
                                             for start, end in occurrences)
        chosen = [r for r in chosen if not any(shadowed(r, other) for other in chosen)]
        references = self.name_references.rules(source, {r['source'] for r in chosen})
        # Quoted names take precedence over general terms contained in that name.
        for reference in references:
            if reference['strict']:
                chosen = [r for r in chosen if not (r.get('strict') and r['source'] in reference['source']
                    and r['vi'].casefold() not in reference['vi'].casefold()
                    and source.count(r['source']) == source.count(reference['source']) * reference['source'].count(r['source']))]
        combined = chosen + references
        full = [r for r in combined if source == r['source']]
        return full if full else combined

    def plan(self):
        direct = sum(j.exact is not None or not CJK.search(j.source) for j in self.jobs)
        log(f'Tổng {len(self.jobs):,} mục | có sẵn theo bảng duyệt/nguồn: {direct:,} | '
            f'{self.cfg["batch_size"]} mục/lô | {self.cfg["parallel_requests"]} luồng | '
            f'timeout {self.cfg["request_timeout_seconds"]}s.')

    def batches(self, jobs):
        batch, characters, group = [], 0, None
        for job in sorted(jobs, key=lambda j: (j.file, j.context['category'], j.row_id, j.target_field)):
            current = (job.file, job.context['category'])
            if batch and (len(batch) >= self.cfg['batch_size']
                          or characters + len(job.source) > self.cfg['max_source_characters_per_batch']
                          or job.file != batch[0].file
                          or (current != group and len(batch) >= 100)):
                yield batch
                batch, characters = [], 0
            batch.append(job)
            characters += len(job.source)
            group = current
        if batch:
            yield batch

    def apply(self, store, jobs, quiet=False):
        ready = store.checked_ready(jobs)
        grouped = defaultdict(list)
        for job in jobs:
            if job.key in ready:
                grouped[job.file].append(job)
        written = 0
        for name, candidates in grouped.items():
            path, spec = self.specs[name]
            raw = path.read_bytes()
            rows = json.loads(raw.decode('utf-8-sig'))
            lookup = {str(r[spec['id_field']]): r for r in rows}
            if len(lookup) != len(rows):
                raise ValueError('ID bị trùng trong file hiện tại: ' + name)
            changed = False
            applied = []
            with store.connect() as db:
                previous = {}
                for offset in range(0, len(candidates), 500):
                    keys = [j.key for j in candidates[offset:offset+500]]
                    previous.update({k: (s, p, v) for k, s, p, v in db.execute(
                        'SELECT * FROM applied WHERE key IN (' + ','.join('?' for _ in keys) + ')', keys)})
            for job in candidates:
                row = lookup.get(job.row_id)
                translated = ready[job.key]
                if row is None or row.get(job.source_field) != job.source:
                    self.conflicts[job.key] = 'Nguồn thay đổi hoặc dòng bị xóa khi đang dịch'
                    continue
                current_key = str(row.get(spec.get('key_field', ''), job.row_id))
                if current_key != job.game_key:
                    self.conflicts[job.key] = 'Khóa game thay đổi khi đang dịch; chưa ghi kết quả'
                    continue
                old_applied = previous.get(job.key)
                current = row.get(job.target_field)
                if old_applied and current != old_applied[2] and current != translated:
                    self.conflicts[job.key] = 'Bản dịch được sửa thủ công sau lần ghi trước'
                    continue
                if current not in (self.expected[job.key], translated):
                    self.conflicts[job.key] = 'Trường đích thay đổi khi đang dịch'
                    continue
                if current != translated:
                    row[job.target_field] = translated
                    changed = True
                    written += 1
                applied.append((job.key, job.source_hash, job.policy, translated))
            if changed:
                backup = store.directory / 'backups' / self.run_id / name
                if not backup.exists():
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, backup)
                if path.read_bytes() != raw:
                    raise RuntimeError('File bị thay đổi trước khi ghi; tiến độ vẫn được giữ: ' + name)
                atomic_json(path, rows)
            with store.connect() as db:
                db.executemany('INSERT OR REPLACE INTO applied VALUES (?,?,?,?)', applied)
                for job in candidates:
                    if job.key in self.conflicts:
                        db.execute('INSERT OR REPLACE INTO conflicts VALUES (?,?)',
                                   (job.key, self.conflicts[job.key]))
                db.executemany('DELETE FROM conflicts WHERE key=?', [(k,) for k, _, _, _ in applied])
            for key, _, _, vi in applied:
                self.expected[key] = vi
                self.conflicts.pop(key, None)
        if written and not quiet:
            log(f'Đã ghi {written:,} mục vào file game.')

    def report(self, store, write=True, quiet=False):
        ready = store.ready(self.jobs)
        failures = store.failures([j for j in self.jobs if j.key not in ready], include_previous_policies=True)
        with store.connect() as db:
            usage = [json.loads(row[0]) for row in db.execute('SELECT usage FROM requests')]
            conflicts = {key: reason for key, reason in db.execute('SELECT key,reason FROM conflicts')
                         if key in self.by_key}
        pending = [{'key': j.key, 'ch': j.source, 'error': failures.get(j.key, 'Chưa dịch')}
                   for j in self.jobs if j.key not in ready]
        totals = Counter()
        for entry in usage:
            if not isinstance(entry, dict):
                continue
            for key, value in entry.items():
                if isinstance(value, int):
                    totals[key] += value
        report = {'model': self.cfg['model'], 'items': len(self.jobs), 'accepted': len(ready),
                  'pending': len(pending), 'conflicts': conflicts,
                  'approved_names_with_chinese': [
                      {'file': j.file, 'key': j.game_key, 'source': j.source, 'vi': j.exact}
                      for j in self.jobs if j.exact is not None and CJK.search(TOKENS.sub('', j.exact))],
                  'all_recorded_usage': dict(totals), 'pending_items': pending}
        failed_items = [{'key': j.key, 'file': j.file, 'game_key': j.game_key,
                         'ch': j.source, 'error': failures[j.key]}
                        for j in self.jobs if j.key not in ready and
                        j.key in failures]
        report['deferred_failed_items'] = len(failed_items)
        if write:
            atomic_json(store.directory / 'report.json', report)
            atomic_json(store.directory / 'failed_items.json', failed_items)
        percent = 100 * len(ready) / len(self.jobs) if self.jobs else 100
        if not quiet:
            log(f'Tiến độ {len(ready):,}/{len(self.jobs):,} ({percent:.1f}%) | '
                f'còn {len(pending):,} | xung đột {len(conflicts):,}.')
        return len(pending) + len(conflicts)

    def run(self, store, key, retry_failed=False):
        ready = store.checked_ready(self.jobs)
        memory = store.memories()
        failures = store.failures([j for j in self.jobs if j.key not in ready], include_previous_policies=True)
        deferred = 0
        seeds = []
        groups = defaultdict(list)
        for job in self.jobs:
            if job.key in ready:
                continue
            value = job.exact if job.exact is not None else (job.source if not CJK.search(job.source) else memory.get(job.cache_key))
            if value is not None:
                seeds.append((job, validate(job, value, masked=False)))
            else:
                if retry_failed and job.key not in failures:
                    continue
                if not retry_failed and self.cfg.get('defer_failed_items', False) and job.key in failures:
                    deferred += 1
                    continue
                groups[job.cache_key].append(job)
        store.save(seeds)
        self.apply(store, self.jobs, quiet=True)
        log(f'Bắt đầu | đã có {len(ready)+len(seeds):,}/{len(self.jobs):,} mục | '
            f'cần dịch {len(groups):,} mục sau gộp trùng' +
            (f' | hoãn {deferred:,} mục lỗi.' if deferred else '.'))
        api = ChatCompletions(self.cfg, self.style, key, store)
        completed_keys = set(ready) | {j.key for j, _ in seeds}
        self.report(store, quiet=True)
        last_report = time.monotonic()
        last_update = time.monotonic()
        batches = iter(self.batches([items[0] for items in groups.values()]))
        executor = ThreadPoolExecutor(max_workers=self.cfg['parallel_requests'])
        futures = {}
        fatal = None
        try:
            while not STOP.is_set():
                while len(futures) < self.cfg['parallel_requests']:
                    batch = next(batches, None)
                    if batch is None:
                        break
                    futures[executor.submit(api.translate, batch)] = (batch, time.monotonic())
                if not futures:
                    break
                completed, _ = wait(futures, timeout=1, return_when=FIRST_COMPLETED)
                if not completed and time.monotonic() - last_update >= 30:
                    log(f'Đang dịch... {len(futures)} lô đang xử lý.')
                    last_update = time.monotonic()
                for future in completed:
                    batch, started = futures.pop(future)
                    accepted = future.result()
                    accepted_values = store.ready(accepted)
                    copies, apply_jobs = [], []
                    for leader in accepted:
                        value = accepted_values[leader.key]
                        for job in groups[leader.cache_key]:
                            copies.append((job, validate(job, value, masked=False)))
                            apply_jobs.append(job)
                    store.save(copies)
                    self.apply(store, apply_jobs, quiet=True)
                    completed_keys.update(j.key for j, _ in copies)
                    if time.monotonic() - last_report >= 30:
                        self.report(store, quiet=True)
                        last_report = time.monotonic()
                    percent = 100 * len(completed_keys) / len(self.jobs) if self.jobs else 100
                    unresolved = len(batch) - len(accepted)
                    suffix = f' | chưa đạt {unresolved}' if unresolved else ''
                    if unresolved:
                        failed_jobs = [j for j in batch if j.key not in accepted_values]
                        summary = validation_error_summary(store.failures(failed_jobs).values())
                        if summary:
                            suffix += ': ' + summary
                    log(f'{len(completed_keys):,}/{len(self.jobs):,} ({percent:.1f}%) | '
                        f'{batch[0].file} | đạt {len(accepted)}/{len(batch)} | '
                        f'{time.monotonic()-started:.0f}s{suffix}')
                    last_update = time.monotonic()
        except InterruptedError as exc:
            if not STOP.is_set():
                fatal = exc
            STOP.set()
        except Exception as exc:
            fatal = exc
            STOP.set()
        finally:
            if STOP.is_set():
                log('Đang dừng, chờ lưu các lô đang chạy...')
            executor.shutdown(wait=True, cancel_futures=True)
            # A stopped worker may have checkpointed its leader before returning.
            # Populate the identical-context followers from that durable result too.
            cached = store.memories()
            copies = [(j, validate(j, cached[signature], masked=False))
                      for signature, followers in groups.items() if signature in cached for j in followers]
            store.save(copies)
            # Also apply results returned by in-flight workers after stop/error.
            self.apply(store, self.jobs, quiet=True)
            remaining = self.report(store, quiet=True)
        if fatal:
            raise fatal
        if STOP.is_set():
            log('Đã dừng và lưu tiến độ. Chạy lại để tiếp tục.')
        elif remaining:
            log(f'Còn {remaining:,} mục chưa xong/xung đột. Lỗi lưu trong failed_items.json; '
                'dùng run.cmd retry để xử lý sau.')
        else:
            log('Hoàn tất. Bản dịch đã lưu vào file game.')
        return 2 if remaining else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'run', 'retry', 'status', 'apply'])
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--limit', type=int, default=0, help='Giới hạn số mục để dịch thử; tiến độ được lưu theo từng khóa')
    args = parser.parse_args()
    if args.limit < 0:
        parser.error('--limit phải lớn hơn hoặc bằng 0')
    engine = Engine(args.config, args.limit)
    engine.plan()
    if args.command == 'plan':
        log('[XEM KẾ HOẠCH] Chưa gọi API, chưa ghi bản dịch. Nhập run.cmd run để bắt đầu dịch; run.cmd run 200 để thử 200 mục.')
        return 0
    api_key = resolve_api_key(engine.cfg, engine.folder) if args.command in ('run', 'retry') else ''
    if args.command in ('run', 'retry') and not api_key:
        raise ValueError('Cần đặt biến ' + engine.cfg['api_key_env'] + ' hoặc cấu hình api_key_file trước khi dịch')
    if args.command == 'status':
        if not (engine.state / 'progress.sqlite3').exists():
            log('[TIẾN ĐỘ] Chưa có tiến độ đã lưu. Nhập run.cmd run để bắt đầu.')
            return 0
        # WAL readers can inspect an active run without taking its exclusive session lock.
        return 2 if engine.report(Store(engine.state), write=False) else 0
    engine.state.mkdir(parents=True, exist_ok=True)
    # OS file lock releases automatically after crash; no stale PID lock to delete.
    lock = (engine.state / 'session.lock').open('a+b')
    lock.seek(0, 2)
    if lock.tell() == 0:
        lock.write(b'0'); lock.flush()
    lock.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise RuntimeError('Một phiên dịch khác đang sử dụng thư mục tiến độ này') from None
    try:
        store = Store(engine.state)
        store.recover()
        if args.command == 'apply':
            engine.apply(store, engine.jobs)
        if args.command in ('apply', 'status'):
            return 2 if engine.report(store) else 0
        def stop_signal(*_):
            if not STOP.is_set():
                log('Đã nhận Ctrl+C, đang lưu tiến độ...')
            STOP.set()
        signal.signal(signal.SIGINT, stop_signal)
        signal.signal(signal.SIGTERM, stop_signal)
        return engine.run(store, api_key, retry_failed=args.command == 'retry')
    finally:
        lock.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        log('[LỖI] ' + type(exc).__name__ + ': ' + str(exc))
        sys.exit(1)
