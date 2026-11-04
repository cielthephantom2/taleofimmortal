"""Regression checks for segmented translation; no API calls or game writes."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from translate import (Engine, Job, STOP, Store, TOKENS, VERSION, atomic_json,
                       connection_error_reason, mask, response_translation,
                       validate, validate_candidate, validate_response,
                       normalize_wire_response, validation_error_summary)
from dataclasses import asdict
from terminology import Matcher, NameReferences


class ErrorLogTests(unittest.TestCase):
    def test_computed_macro_is_preserved_as_one_engine_token(self):
        formula = '&91011_zhsh|+91011_zhsh%1+1|+91011_zhsh%2+1|f2&'
        masked, values = mask('增加' + formula + '%的伤害')
        self.assertEqual(values, [formula])
        job = Job('test', 'test', 'test.json', '1', 'ch', 'en',
                  '增加' + formula + '%的伤害', 's', 'p', 'c', {}, [], '', '', True)
        self.assertEqual(validate(job, 'Tăng __GGBH_P0000__% sát thương'),
                         'Tăng ' + formula + '% sát thương')
        with self.assertRaises(ValueError):
            validate_candidate(job, 'Tăng ' + formula.replace('zhsh', 'wrong') + '% sát thương')

    def test_percent_before_vietnamese_word_is_not_printf(self):
        for text in ('% sát thương', '% giây', '% số lượng', '% dùng'):
            with self.subTest(text=text):
                self.assertEqual(TOKENS.findall(text), [])

    def test_real_printf_codes_remain_protected(self):
        self.assertEqual(TOKENS.findall('%s %d %2$.2f %03i'), ['%s', '%d', '%2$.2f', '%03i'])

    def test_percent_macro_translation_is_accepted(self):
        job = Job('test', 'test', 'test.json', '1', 'ch', 'en',
                  '增加&damage&%的伤害', 's', 'p', 'c', {}, [], '', '', True)
        self.assertEqual(validate(job, 'Tăng __GGBH_P0000__% sát thương'),
                         'Tăng &damage&% sát thương')

    def test_wrapped_timeout_is_identified(self):
        self.assertEqual(connection_error_reason(URLError(TimeoutError()), 180),
                         'Hết thời gian chờ 180s')

    def test_bad_json_reports_position_without_echoing_response(self):
        exc = json.JSONDecodeError('error', 'secret-server-response', 3)
        reason = connection_error_reason(exc, 180)
        self.assertIn('JSON', reason)
        self.assertIn('cột 4', reason)
        self.assertNotIn('secret-server-response', reason)

    def test_validation_errors_are_grouped(self):
        summary = validation_error_summary([
            'Mã giữ chỗ bị thiếu, lặp hoặc sai thứ tự',
            'Mã game, số liệu hoặc xuống dòng bị thay đổi',
            'Bản dịch vẫn còn chữ Hán'])
        self.assertEqual(summary, 'sai mã/số/xuống dòng (2), còn chữ Hán (1)')


class SegmentedTranslationTests(unittest.TestCase):
    def setUp(self):
        self.job = Job('test', 'test', 'test.json', '1', 'ch', 'en',
                       '甲<g>乙</g>{0}丙\n12%', 'source', 'policy', 'cache',
                       {}, [], '', '', True)
        self.entry = {'segments': ['Trước', 'Giữa', '', 'Sau', '', '']}

    def test_rebuild_preserves_tags_variables_newlines_and_numbers(self):
        self.assertEqual(validate(self.job, response_translation(self.job, self.entry)),
                         'Trước<g>Giữa</g>{0}Sau\n12%')

    def test_item_contains_matching_segment_count(self):
        item = self.job.api_item(segmented=True)
        self.assertEqual(len(item['ch_segments']), len(self.entry['segments']))
        self.assertEqual(item['ch'], mask(self.job.source)[0])

    def test_reject_missing_extra_nonstring_and_scalar_segments(self):
        for segments in (self.entry['segments'][:-1], self.entry['segments'] + [''],
                         [None] * 6, 'invalid'):
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                response_translation(self.job, {'segments': segments})

    def test_reject_injected_marker_and_empty_translation(self):
        for text in ('__GGBH_P0000__',):
            entry = copy.deepcopy(self.entry)
            entry['segments'][0] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                response_translation(self.job, entry)
        self.job.source = '甲'
        with self.assertRaises(ValueError):
            validate(self.job, response_translation(self.job, {'segments': ['']}))

    def test_date_suffix_can_move_before_variable(self):
        self.job.source = '第{0}年{1}月'
        entry = {'segments': ['Năm thứ ', ' tháng ', '']}
        self.assertEqual(validate(self.job, response_translation(self.job, entry)),
                         'Năm thứ {0} tháng {1}')

    def test_prose_inside_pipes_is_not_hidden_from_translation(self):
        masked, values = mask('甲|乙|丙|x22111_dmg|')
        self.assertIn('乙', masked)
        self.assertEqual(values, ['|', '|', '|x22111_dmg|'])
        self.job.source = '甲|乙|丙'
        with self.assertRaises(ValueError):
            validate(self.job, 'Trước|乙|Sau', masked=False)

    def test_kaomoji_is_preserved_as_a_visual_symbol(self):
        self.job.source = '甲(*｀皿´*)ﾉ'
        masked, values = mask(self.job.source)
        self.assertEqual(values, ['(*｀皿´*)ﾉ'])
        self.assertEqual(validate(self.job, 'Xin chào __GGBH_P0000__'), 'Xin chào (*｀皿´*)ﾉ')

    def test_reject_added_text_between_adjacent_game_tokens(self):
        entry = copy.deepcopy(self.entry)
        entry['segments'][2] = 'extra'
        with self.assertRaises(ValueError):
            response_translation(self.job, entry)

    def test_horizontal_whitespace_is_restored_in_empty_source_slots(self):
        entry = copy.deepcopy(self.entry)
        entry['segments'][2] = '  '
        self.assertEqual(validate(self.job, response_translation(self.job, entry)),
                         'Trước<g>Giữa</g>{0}Sau\n12%')

    def test_indexed_segments_do_not_require_empty_positions(self):
        item = self.job.api_item(segmented=True, indexed=True)
        self.assertEqual(set(item['translatable_segments']), {'0', '1', '3'})
        entry = {'segments': {'0': 'Trước', '1': 'Giữa', '3': 'Sau'}}
        self.assertEqual(validate(self.job, response_translation(self.job, entry)),
                         'Trước<g>Giữa</g>{0}Sau\n12%')
        entry['segments']['2'] = ''
        with self.assertRaises(ValueError):
            response_translation(self.job, entry)

    def test_raw_engine_tokens_still_need_exact_token_validation(self):
        self.assertEqual(validate_candidate(self.job, 'Trước<g>Giữa</g>{0}Sau\n12%'),
                         'Trước<g>Giữa</g>{0}Sau\n12%')
        with self.assertRaises(ValueError):
            validate_candidate(self.job, 'Trước<g>Giữa</g>{1}Sau\n12%')

    def test_reject_added_numbers_newlines_and_chinese(self):
        for text in ('Trước 99', 'Trước\n', '甲'):
            entry = copy.deepcopy(self.entry)
            entry['segments'][0] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate(self.job, response_translation(self.job, entry))

    def test_approved_terms_still_required(self):
        self.job.terms = [{'vi': 'Tên Đã Duyệt', 'strict': True}]
        with self.assertRaises(ValueError):
            validate(self.job, response_translation(self.job, self.entry))

    def test_existing_en_responses_still_supported(self):
        self.assertEqual(response_translation(self.job, {'en': 'previous'}), 'previous')

    def test_context_exposes_location_variable_to_model(self):
        self.job.source = '可在<g>{#areaName6}</g>获得。'
        self.assertEqual(self.job.api_item(segmented=True)['ch_context'], self.job.source)

    def test_reject_chinese_when_reusing_cached_translation(self):
        self.job.source = '甲'
        with self.assertRaises(ValueError):
            validate(self.job, '甲', masked=False)

    def test_keep_explicitly_approved_rare_name(self):
        self.job.source = self.job.exact = '琒'
        self.assertEqual(validate(self.job, '琒', masked=False), '琒')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temporary.name))
        self.job = Job('test', 'test', 'test.json', '1', 'ch', 'en',
                       '甲', 'source', 'policy', 'cache', {}, [], '', '', True)

    def tearDown(self):
        self.temporary.cleanup()

    def test_lookup_is_scoped_to_source_and_policy(self):
        self.store.save([(self.job, 'Xin chào')])
        self.assertEqual(self.store.ready([self.job]), {'test': 'Xin chào'})
        self.job.source_hash = 'changed'
        self.assertEqual(self.store.ready([self.job]), {})

    def test_invalid_cached_text_is_backed_up_and_removed_only_for_that_job(self):
        other = copy.deepcopy(self.job)
        other.key, other.cache_key = 'other', 'other-cache'
        self.store.save([(self.job, '甲'), (other, 'Xin chào')])
        with redirect_stdout(io.StringIO()):
            ready = self.store.checked_ready([self.job, other])
        self.assertEqual(ready, {'other': 'Xin chào'})
        self.assertNotIn('cache', self.store.memories())
        self.assertEqual(self.store.memories()['other-cache'], 'Xin chào')
        self.assertEqual(len(list((self.store.directory / 'cache_review').glob('*.json'))), 1)

    def test_failure_does_not_overwrite_completed_translation(self):
        self.store.save([(self.job, 'Xin chào')])
        self.store.save([], [(self.job, 'later failure')])
        self.assertEqual(self.store.failures([self.job]), {})
        self.assertEqual(self.store.ready([self.job]), {'test': 'Xin chào'})

    def test_connection_is_closed_and_failed_transaction_rolls_back(self):
        with self.assertRaises(RuntimeError):
            with self.store.connect() as db:
                db.execute("INSERT INTO memory VALUES ('rollback', 'test')")
                raise RuntimeError('rollback')
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute('SELECT 1')
        self.assertEqual(self.store.memories(), {})

    def test_usage_null_and_journal_recovery(self):
        response = {'choices': [{'message': {'content': json.dumps({
            'translations': [{'key': self.job.key, 'en': 'Xin chào'}]})}}], 'usage': None}
        good, bad = self.store.accept_response([self.job], response, 'request', 'model')
        self.assertEqual((len(good), len(bad)), (1, 0))
        with self.store.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT usage FROM requests').fetchone()[0]), {})

    def test_recover_journal_once_without_api(self):
        response = {'choices': [{'message': {'content': json.dumps({
            'translations': [{'key': self.job.key, 'en': 'Xin chào'}]})}}]}
        atomic_json(self.store.directory / 'journal/recover.json', {
            'version': VERSION, 'model': 'test', 'jobs': [asdict(self.job)], 'response': response})
        with redirect_stdout(io.StringIO()):
            self.store.recover()
            self.store.recover()
        self.assertEqual(self.store.ready([self.job]), {'test': 'Xin chào'})
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM requests').fetchone()[0], 1)

    def test_missing_duplicate_and_unknown_keys_are_rejected(self):
        for entries in ([], [{'key': 'test', 'en': 'Xin chào'}] * 2,
                        [{'key': 'unknown', 'en': 'Xin chào'}]):
            response = {'choices': [{'message': {'content': json.dumps({'translations': entries})}}]}
            good, bad = self.store.accept_response([self.job], response, 'invalid', 'test')
            self.assertEqual((len(good), len(bad)), (0, 1))

    def test_one_unknown_key_does_not_discard_other_valid_rows(self):
        other = copy.deepcopy(self.job)
        other.key = 'other'
        response = {'choices': [{'message': {'content': json.dumps({'translations': [
            {'key': 'test', 'en': 'Xin chào'}, {'key': 'wrong-key', 'en': 'Other'}, None]})}}]}
        good, bad = validate_response([self.job, other], response)
        self.assertEqual([j.key for j, _ in good], ['test'])
        self.assertEqual([j.key for j, _ in bad], ['other'])

    def test_complete_rows_are_salvaged_without_inventing_partial_strings(self):
        other = copy.deepcopy(self.job)
        other.key = 'other'
        prefix = '{"translations":[{"key":"test","en":"Xin chào"},'
        response = {'choices': [{'finish_reason': 'length', 'message': {
            'content': prefix + '{"key":"other","en":"unfinished'}}]}
        good, bad = validate_response([self.job, other], response)
        self.assertEqual([j.key for j, _ in good], ['test'])
        self.assertEqual([j.key for j, _ in bad], ['other'])

    def test_trailing_json_garbage_does_not_invalidate_complete_rows(self):
        response = {'choices': [{'message': {'content':
            '{"translations":[{"key":"test","en":"Xin chào"}]壯}'}}]}
        self.assertEqual(len(validate_response([self.job], response)[0]), 1)
        response['choices'][0]['message']['content'] = 'not JSON {"key":"test","en":"Xin chào"}'
        self.assertEqual(len(validate_response([self.job], response)[0]), 0)

    def test_composite_key_json_whitespace_is_canonicalized_without_fuzzy_matching(self):
        identity = ['test.json', '1', 'game-key', 'en']
        self.job.key = json.dumps(identity, separators=(',', ':'))
        response = {'choices': [{'message': {'content': json.dumps({'translations': [
            {'key': json.dumps(identity), 'en': 'Xin chào'}]})}}]}
        self.assertEqual(len(validate_response([self.job], response)[0]), 1)
        identity[1] = 'wrong-id'
        response['choices'][0]['message']['content'] = json.dumps({'translations': [
            {'key': json.dumps(identity), 'en': 'Xin chào'}]})
        self.assertEqual(len(validate_response([self.job], response)[0]), 0)

    def test_short_wire_keys_normalize_and_recover_from_raw_journal(self):
        response = {'choices': [{'message': {'content': json.dumps({'translations': [
            {'key': 'k0000', 'en': 'Xin chào'}]})}}]}
        mapping = {'k0000': self.job.key}
        normalized = normalize_wire_response(response, mapping)
        self.assertEqual(len(validate_response([self.job], normalized)[0]), 1)
        self.assertIn('k0000', response['choices'][0]['message']['content'])
        atomic_json(self.store.directory / 'journal/wire.json', {
            'version': VERSION, 'model': 'test', 'jobs': [asdict(self.job)],
            'wire_keys': mapping, 'response': response})
        with redirect_stdout(io.StringIO()):
            self.store.recover()
        self.assertEqual(self.store.ready([self.job]), {'test': 'Xin chào'})

    def test_retry_can_find_failure_after_terminology_policy_changes(self):
        self.store.save([], [(self.job, 'old terminology error')])
        self.job.policy = 'new-terminology'
        self.assertEqual(self.store.failures([self.job]), {})
        self.assertEqual(self.store.failures([self.job], include_previous_policies=True),
                         {'test': 'old terminology error'})
        self.job.source_hash = 'changed-source'
        self.assertEqual(self.store.failures([self.job], include_previous_policies=True), {})


class EngineIntegrationTests(unittest.TestCase):
    def setUp(self):
        STOP.clear()
        self.temporary = tempfile.TemporaryDirectory()
        folder = Path(self.temporary.name)
        self.path = folder / 'test.json'
        self.path.write_text(json.dumps([
            {'id': '1', 'key': 'a', 'ch': '甲', 'en': 'old'},
            {'id': '2', 'key': 'b', 'ch': '甲', 'en': 'old'}]), encoding='utf-8')
        engine = self.engine = object.__new__(Engine)
        engine.cfg = {'batch_size': 25, 'max_source_characters_per_batch': 6000,
                      'parallel_requests': 1, 'requests_per_minute': 0,
                      'validation_retries': 0, 'model': 'test'}
        engine.style = ''
        engine.jobs = [Job(key, key, 'test.json', str(i), 'ch', 'en', '甲',
                           'source', 'policy', 'shared-cache', {'category': 'test'},
                           [], '', '', True) for i, key in enumerate(('a', 'b'), 1)]
        engine.by_key = {j.key: j for j in engine.jobs}
        engine.expected = {j.key: 'old' for j in engine.jobs}
        engine.specs = {'test.json': (self.path, {'id_field': 'id', 'key_field': 'key'})}
        engine.conflicts = {}
        engine.run_id = 'test-run'
        self.store = Store(folder / 'state')

    def tearDown(self):
        STOP.clear()
        self.temporary.cleanup()

    def response(self, jobs, *args, **kwargs):
        return {'choices': [{'message': {'content': json.dumps({'translations': [
            {'key': j.key, 'en': 'Xin chào'} for j in jobs]})}}]}, 'test-request'

    def test_deduplicate_apply_backup_and_resume_without_new_api_calls(self):
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call', side_effect=self.response) as call:
            self.assertEqual(self.engine.run(self.store, 'fake'), 0)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(len(call.call_args.args[0]), 1)
        self.assertEqual([r['en'] for r in json.loads(self.path.read_text(encoding='utf-8'))],
                         ['Xin chào', 'Xin chào'])
        backup = self.store.directory / 'backups/test-run/test.json'
        self.assertEqual(json.loads(backup.read_text(encoding='utf-8'))[0]['en'], 'old')
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call') as call:
            self.assertEqual(self.engine.run(self.store, 'fake'), 0)
            call.assert_not_called()

    def test_stop_saves_inflight_response_and_identical_followers(self):
        def stop_response(*args, **kwargs):
            STOP.set()
            return self.response(*args, **kwargs)
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call', side_effect=stop_response):
            self.engine.run(self.store, 'fake')
        self.assertEqual(len(self.store.ready(self.engine.jobs)), 2)
        self.assertEqual([r['en'] for r in json.loads(self.path.read_text(encoding='utf-8'))],
                         ['Xin chào', 'Xin chào'])

    def test_stop_while_waiting_is_not_a_fatal_error(self):
        def interrupt(*args, **kwargs):
            STOP.set()
            raise InterruptedError('Đã dừng')
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call', side_effect=interrupt):
            self.assertEqual(self.engine.run(self.store, 'fake'), 2)

    def test_batches_never_mix_game_files(self):
        self.engine.jobs[1].file = 'other.json'
        batches = list(self.engine.batches(self.engine.jobs))
        self.assertEqual(len(batches), 2)

    def test_normal_run_defers_saved_failures_and_retry_processes_them(self):
        self.engine.cfg['defer_failed_items'] = True
        self.store.save([], [(j, 'previous failure') for j in self.engine.jobs])
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call') as call:
            self.assertEqual(self.engine.run(self.store, 'fake'), 2)
            call.assert_not_called()
        failed_path = self.store.directory / 'failed_items.json'
        self.assertEqual(len(json.loads(failed_path.read_text(encoding='utf-8'))), 2)
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call', side_effect=self.response) as call:
            self.assertEqual(self.engine.run(self.store, 'fake', retry_failed=True), 0)
            self.assertEqual(call.call_count, 1)
        self.assertEqual(json.loads(failed_path.read_text(encoding='utf-8')), [])

    def test_failed_batch_is_not_retried_and_next_batch_runs(self):
        self.engine.cfg.update(batch_size=1, validation_retries=0, defer_failed_items=True)
        self.engine.jobs[1].cache_key = 'different-cache'
        def response(jobs, *args, **kwargs):
            if jobs[0].key == 'a':
                return {'choices': [{'message': {'content': '{"translations":[]}'}}]}, 'failed-request'
            return self.response(jobs)
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call', side_effect=response) as call:
            self.assertEqual(self.engine.run(self.store, 'fake'), 2)
            self.assertEqual(call.call_count, 2)
        self.assertEqual(self.store.ready(self.engine.jobs), {'b': 'Xin chào'})
        failed = json.loads((self.store.directory / 'failed_items.json').read_text(encoding='utf-8'))
        self.assertEqual([j['game_key'] for j in failed], ['a'])

    def test_retry_command_does_not_send_unattempted_jobs(self):
        self.engine.cfg['defer_failed_items'] = True
        self.engine.jobs[1].cache_key = 'different-cache'
        self.store.save([], [(self.engine.jobs[0], 'previous failure')])
        with redirect_stdout(io.StringIO()), patch('translate.ChatCompletions.call', side_effect=self.response) as call:
            self.assertEqual(self.engine.run(self.store, 'fake', retry_failed=True), 2)
            self.assertEqual([j.key for j in call.call_args.args[0]], ['a'])
        self.assertNotIn('b', self.store.ready(self.engine.jobs))

    def test_manual_edits_are_preserved(self):
        self.store.save([(self.engine.jobs[0], 'Xin chào')])
        rows = json.loads(self.path.read_text(encoding='utf-8'))
        rows[0]['en'] = 'manual edit'
        self.path.write_text(json.dumps(rows), encoding='utf-8')
        with redirect_stdout(io.StringIO()):
            self.engine.apply(self.store, self.engine.jobs)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))[0]['en'], 'manual edit')
        self.assertIn('a', self.engine.conflicts)


class GlossaryScopeTests(unittest.TestCase):
    def test_context_exclusion_does_not_change_rule_in_unrelated_sentences(self):
        engine = object.__new__(Engine)
        original = {'source': '老身', 'vi': 'lão thân', 'strict': True}
        rule = {**original, 'context_exclusions': ['长老身']}
        engine.rule_index = {'老身': [rule]}
        engine.rule_matcher = Matcher(engine.rule_index)
        engine.name_references = NameReferences([])
        self.assertEqual(engine.rules('RoleLogLocal.json', 'log', '以大长老身份参战'), [])
        self.assertEqual(engine.rules('RoleLogLocal.json', 'log', '老身在此'), [original])
        self.assertEqual(engine.rules('RoleLogLocal.json', 'log', '长老身份和老身'), [original])

    def test_fate_name_is_advisory_only_in_reviewed_narrative_context(self):
        engine = object.__new__(Engine)
        rule = {'source': '傻子', 'vi': 'Si Nhân', 'strict': True,
                'context_advisory_key_globs': ['drama_*']}
        engine.rule_index = {'傻子': [rule]}
        engine.rule_matcher = Matcher(engine.rule_index)
        engine.name_references = NameReferences([])
        selected = engine.rules('RoleLogLocal.json', 'drama_option1', '傻子，准备应战')[0]
        self.assertFalse(selected['strict'])
        self.assertFalse(selected['allow_exact'])
        self.assertTrue(engine.rules('LocalText.json', 'role_feature_name1', '傻子')[0]['strict'])
        self.assertTrue(engine.rules('RoleLogLocal.json', 'drama_option1', '“傻子”')[0]['strict'])

    def test_excluded_substrings_do_not_force_unrelated_meanings(self):
        engine = object.__new__(Engine)
        rules = [{'source': '义女', 'vi': 'nghĩa nữ', 'strict': True, 'exclude_within': ['自定义女']},
                 {'source': '药效', 'vi': 'dược hiệu', 'strict': True, 'exclude_within': ['丹药效果']}]
        engine.rule_index = {r['source']: [r] for r in rules}
        engine.rule_matcher = Matcher(engine.rule_index)
        engine.name_references = NameReferences([])
        for text in ('自定义女性模型', '丹药效果'):
            self.assertEqual(engine.rules('test.json', 'test', text), [])
        for text, expected in (('自定义女性模型和义女', '义女'), ('丹药效果及药效', '药效')):
            self.assertEqual([r['source'] for r in engine.rules('test.json', 'test', text)], [expected])


if __name__ == '__main__':
    unittest.main()
