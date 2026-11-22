"""Fail-closed configuration and fault-policy regressions; no native game packages required."""
import copy
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'game_first_exam/tests'), str(ROOT / 'scripts'), str(ROOT / 'game_first_exam/runtime')]
from config_schema import (
    validate_instance,
    validate_metric_spec,
    validate_spec,
    validate_suite,
)
from contracts import Transition
from encoding import state_hash
from game_preflight import preflight
from game_schemas import schema_paths
from grade import grade
from run_games import aggregate
from server import EnvironmentFault, Game, InvalidAction
from test_game_service import Backend, instance
from test_games_runner import record, trial


class ConfigTests(unittest.TestCase):
    def test_each_bundled_schema_works_without_repo_or_engine_packages(self):
        for benchmark, schema in schema_paths().items():
            tasks = sorted((ROOT / 'game_first_exam/tasks' / benchmark).glob('*-standard'))
            sample = next((p / 'tests/instance.json' for p in tasks if '-i00-' not in p.name),
                          ROOT / 'game_first_exam/tests/fixtures' / f'{benchmark}-instance.json')
            with self.subTest(benchmark=benchmark), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                for name in ('config_schema.py', 'reducers.py'):
                    shutil.copyfile(ROOT / 'game_first_exam/runtime' / name, out / name)
                shutil.copyfile(schema, out / 'instance_schema.py')
                shutil.copyfile(sample, out / 'instance.json')
                program = '''import json, sys
sys.path.insert(0, '.')
from config_schema import validate_instance
x = json.load(open('instance.json'))
validate_instance(x)
for bad in ({**x, 'benchmark': 'unregistered'}, {**x, 'schema_path': 'evil.py'},
            {**x, 'observation_profile': 'unknown'}, {**x, 'unexpected_native_field': 1}):
    try: validate_instance(bad)
    except ValueError: pass
    else: raise AssertionError('untrusted configuration accepted')
'''
                subprocess.run([sys.executable, '-S', '-c', program], cwd=out, check=True, capture_output=True, text=True)

    def test_set_state_hash_is_order_independent_across_processes(self):
        script = "from encoding import state_hash; print(state_hash({'colors': set(['blue', 'red', 'green'])}))"
        outputs = []
        for seed in ['1', '71']:
            env = {**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONPATH': str(ROOT / 'game_first_exam/runtime')}
            outputs.append(subprocess.check_output([sys.executable, '-c', script], env=env, text=True).strip())
        self.assertEqual(outputs[0], outputs[1])
        self.assertNotEqual(state_hash({'red'}), state_hash(['red']))
        self.assertNotEqual(state_hash({'red'}), state_hash({'blue'}))

    def test_instance_and_reducer_typos_fail_closed(self):
        original = instance()
        validate_instance(original)
        for changes in ({'max_steps': True}, {'seed': -1}, {'schema_version': 'game-instance/99'},
                        {'adapter_version': '9.0.0'}, {'observation_profile': 'pixels-maybe'},
                        {'max_step': 5}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                validate_instance({**original, **changes})
        for changes in ({'reducer': 'famliy_macro'}, {'reducer_version': '2.0.0'}, {'primary_metic': 'score'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_metric_spec({**original['metric_spec'], **changes})
        wrong_metric = copy.deepcopy(original); wrong_metric['metric_spec']['primary'] = 'sucess'
        with self.assertRaises(ValueError): validate_instance(wrong_metric)
        missing = copy.deepcopy(original); del missing['metric_spec']['reducer_version']
        with self.assertRaises(ValueError):
            validate_instance(missing)

    def test_native_ci_and_runtime_dependency_locks_match(self):
        for benchmark in ('minigrid', 'crafter', 'textworld', 'babaisai', 'minihack'):
            filename = 'requirements-v2.txt' if benchmark == 'minigrid' else 'requirements.txt'
            runtime = ROOT / 'game_first_exam/benchmarks' / benchmark / filename
            lock = ROOT / 'game_first_exam/tests/envs/locks' / (benchmark + '.txt')
            self.assertEqual(runtime.read_text(), lock.read_text(), benchmark)

    def test_spec_capabilities_and_action_schema(self):
        config = instance(); spec = Backend().spec()
        validate_spec(spec, config)
        for change in ({'type': 'integer'}, {'min_length': 1}, {'pattern': '.*'}):
            bad = copy.deepcopy(spec); bad['action_schema'].update(change)
            with self.assertRaises(ValueError):
                validate_spec(bad, config)
        bad = copy.deepcopy(spec); bad['capabilities']['timing'] = 'realtime'
        with self.assertRaises(ValueError):
            validate_spec(bad, config)

    def test_preflight_validates_all_tasks_without_building(self):
        import tomllib
        suite = tomllib.loads((ROOT / 'configs/game_suites/core.toml').read_text())
        with patch('files_image.build', side_effect=AssertionError('must not build')):
            for path in sorted((ROOT / 'configs/game_suites').glob('*.toml')):
                with self.subTest(suite=path.name):
                    selected = tomllib.loads(path.read_text())
                    self.assertEqual(len(preflight(selected)), len(selected['tasks']))
        omitted = copy.deepcopy(suite); omitted['files_images'].remove('game-files')
        with self.assertRaisesRegex(ValueError, 'images required'):
            preflight(omitted)
        for mutate in ('duplicate', 'unknown_tier', 'unknown_field'):
            bad = copy.deepcopy(suite)
            if mutate == 'duplicate': bad['tasks'].append(copy.deepcopy(bad['tasks'][0]))
            if mutate == 'unknown_tier': bad['tier'] = 'production-ish'
            if mutate == 'unknown_field': bad['tiers'] = 'smoke'
            with self.assertRaises(ValueError):
                validate_suite(bad)

    def test_metric_conflict_rejected_before_execution_even_outside_filter(self):
        import tomllib

        import game_preflight
        suite = tomllib.loads((ROOT / 'configs/game_suites/babaisai.toml').read_text())
        original = game_preflight.validate_task
        for field, value in [('primary', 'native_return'), ('success_label', 'different')]:
            def changed(row, field=field, value=value):
                task, config, instance = original(row)
                if row == suite['tasks'][-1]:
                    instance['metric_spec'][field] = value
                return task, config, instance
            with self.subTest(field=field), patch('game_preflight.validate_task', side_effect=changed), \
                 self.assertRaisesRegex(ValueError, 'incompatible metric definitions'):
                preflight(suite)

    def test_reducer_version_is_part_of_metric_identity(self):
        records = {'a': record('example', 'one', 'score')}
        records['a']['metric_spec']['reducer'] = 'typo'
        with self.assertRaises(ValueError):
            aggregate([], records)
        records['a']['metric_spec']['reducer'] = 'family_macro'
        rows = [trial('a', 0, valid=False)]
        rows[0]['error_category'] = 'environment'
        result = aggregate(rows, records)['benchmarks']['example']
        self.assertEqual((result['valid'], result['environment_errors'], result['infrastructure_errors']), (0, 1, 0))
        self.assertIsNone(result['macro_primary_score'])


class FaultTests(unittest.TestCase):
    def game(self, backend, config=None):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        game = Game(backend, config or instance(), directory.name); self.addCleanup(game.close)
        return game

    def step(self, game, action='noop'):
        return game.submit({'action': action, 'expected_step': game.steps, 'request_id': str(game.steps)})

    def test_native_early_truncation_does_not_claim_budget_exhaustion(self):
        class Early(Backend):
            def step(self, action): return Transition(0.0, truncated=True)
        game = self.game(Early()); self.step(game)
        self.assertEqual((game.final['reason'], game.final['end_source'], game.final['steps']), ('native_truncated', 'native', 1))
        self.assertFalse(game.final['budget_exhausted'])
        self.assertEqual(grade(game.final, instance(), lambda f, i: None)['infra_error'], 0)
        changed = copy.deepcopy(game.final); changed.update(reason='step_limit', end_source='budget')
        with self.assertRaises(ValueError): grade(changed, instance(), lambda f, i: None)
        with self.assertRaises(ValueError): self.step(game)

    def test_budget_stop_preserves_native_flags_and_coincident_native_end(self):
        game = self.game(Backend())
        for _ in range(4): self.step(game)
        self.assertEqual(game.final['reason'], 'step_limit')
        self.assertFalse(game.final['truncated']); self.assertTrue(game.final['budget_exhausted'])
        self.assertEqual(grade(game.final, instance(), lambda f, i: None)['infra_error'], 0)
        class Both(Backend):
            def step(self, action): return Transition(0.0, terminated=True, truncated=True)
        config = instance(); config['max_steps'] = 1
        game = self.game(Both(), config); self.step(game)
        self.assertEqual(game.final['reason'], 'native_terminated')
        self.assertTrue(game.final['truncated'] and game.final['budget_exhausted'])
        grade(game.final, config, lambda f, i: None)

    def test_engine_valueerror_after_mutation_is_not_invalid_action_or_zero_score(self):
        class Broken(Backend):
            def step(self, action):
                self.position += 1
                raise ValueError('engine bug after partial mutation')
            def metrics(self): raise AssertionError('must not invent metrics after an engine failure')
        game = self.game(Broken())
        with self.assertRaises(InvalidAction): self.step(game, 'unknown')
        self.assertEqual(game.steps, 0)
        with self.assertRaises(EnvironmentFault): self.step(game)
        result = grade(game.final, instance(), lambda f, i: self.fail('must not validate guessed metrics'))
        self.assertEqual(result['error_category'], 'environment')
        self.assertEqual(result['infra_error'], 1)
        self.assertIsNone(game.final['success']); self.assertIsNone(result['primary_score'])
        self.assertIsNone(game.final['metrics'])
        with self.assertRaises(ValueError): self.step(game)

    def test_constructor_failure_leaves_explicit_invalid_evidence(self):
        def broken(*args): raise RuntimeError('cannot initialize engine')
        with tempfile.TemporaryDirectory() as out:
            game = Game.open(broken, instance(), None, out)
            self.assertTrue(game.observe()['done'])
            self.assertEqual(grade(game.final, instance(), lambda f, i: None)['environment_error'], 1)
            self.assertTrue((Path(out) / 'final.json').is_file())
            game.close()

    def test_bad_transition_and_undeclared_truncation_are_environment_faults(self):
        for transition in (Transition(float('nan')), Transition(0, truncated=True), {'reward': 0}):
            class Broken(Backend):
                def step(self, action, value=transition): return value
                def spec(self):
                    spec = super().spec(); spec['capabilities']['native_truncation'] = False; return spec
            config = instance(); config['capabilities']['native_truncation'] = False
            game = self.game(Broken(), config)
            with self.assertRaises(EnvironmentFault): self.step(game)
            self.assertFalse(game.final['result_valid'])


if __name__ == '__main__':
    unittest.main()
