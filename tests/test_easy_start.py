"""Easy Start installation tests; scientific modules remain unchanged."""
from __future__ import annotations

import importlib.util
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import errno
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mdtest_easy_launcher', ROOT / 'tools/launch_mdtest.py')
LAUNCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCH)


class EasyStartTests(unittest.TestCase):
    @contextmanager
    def fake_location(self, top: Path):
        top.mkdir(parents=True, exist_ok=True)
        (top / 'pyproject.toml').write_text('[project]\nversion = "2.2.0.dev7"\n', encoding='utf-8')
        # The actual Windows environment is under LOCALAPPDATA, not under ROOT.
        user_env = top.parent / ('private-mdtest-' + top.name)
        python = user_env / 'bin/python'
        state = user_env / '.mdtest_environment.json'
        with patch.multiple(LAUNCH, ROOT=top, VENV=user_env, PYTHON=python, STATE_FILE=state):
            yield

    @staticmethod
    def make_fake_venv(venv: Path):
        (venv / 'bin').mkdir(parents=True, exist_ok=True)
        (venv / 'pyvenv.cfg').write_text('home = python\n', encoding='utf-8')
        (venv / 'bin/python').touch()

    def test_expected_launchers_and_guides_exist(self):
        for name in ('START_MDTEST_WINDOWS.bat', 'START_MDTEST_MAC.command',
                     'START_MDTEST_LINUX.sh', 'START_HERE.html',
                     'docs/START_HERE.md', 'docs/INSTALL_HELP.md'):
            with self.subTest(name=name):
                self.assertTrue((ROOT / name).is_file())

    def test_version_and_source_unchanged(self):
        self.assertEqual(LAUNCH.project_version(), '2.2.0.dev7')
        self.assertTrue(LAUNCH.EXPECTED_MODULE.is_file())
        self.assertTrue(LAUNCH.NOTEBOOK.is_file())

    def test_windows_path_is_independent_of_deep_download_folder(self):
        folder = Path('C:/Users/jerry/Downloads/a-really-long-name/MDTest/src')
        chosen = LAUNCH.choose_environment_dir(
            folder, platform='win32', environ={'LOCALAPPDATA': 'C:/Users/jerry/AppData/Local'})
        self.assertEqual(chosen.as_posix(), 'C:/Users/jerry/AppData/Local/MDTest/e')
        self.assertNotIn('Downloads', str(chosen))
        jupyter_asset = (chosen / 'Lib/site-packages/jupyterlab/galata/@jupyterlab/'
                         'galata-extension/static/vendors-node_modules_fontsource-variable_'
                         'noto-sans-sc_index_css.386da7677f8b1f52.js')
        self.assertLess(len(str(jupyter_asset)), 230)

    def test_windows_env_fallback_is_per_user_without_admin(self):
        chosen = LAUNCH.choose_environment_dir(
            Path('C:/MDTest'), platform='win32',
            environ={'USERPROFILE': 'C:/Users/tester'})
        self.assertEqual(chosen.as_posix(), 'C:/Users/tester/AppData/Local/MDTest/e')

    def test_non_windows_uses_repo_environment(self):
        loc = Path('/tmp/MDTest/repo')
        self.assertEqual(LAUNCH.choose_environment_dir(loc, platform='linux'), loc / '.venv')
        self.assertEqual(LAUNCH.choose_environment_dir(loc, platform='darwin'), loc / '.venv')

    def test_fresh_environment_does_not_need_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.fake_location(Path(tmp)/'repo'):
                self.assertIsNone(LAUNCH.environment_needs_repair())

    def test_moved_source_relinks_without_rebuilding_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'
            top.mkdir()
            with self.fake_location(top):
                self.make_fake_venv(LAUNCH.VENV)
                state = LAUNCH.environment_state()
                state['install_folder'] = str(top/'old-download-location')
                LAUNCH.STATE_FILE.write_text(json.dumps(state), encoding='utf-8')
                self.assertIn('moved', LAUNCH.environment_needs_repair())
                with patch.object(LAUNCH, 'installed_ok', side_effect=[False, True]), \
                     patch.object(LAUNCH, 'private_python_version', return_value=LAUNCH.sys.version_info[:2]), \
                     patch.object(LAUNCH, 'dependencies_ok', return_value=True), \
                     patch.object(LAUNCH.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
                    self.assertTrue(LAUNCH.setup())
                    self.assertEqual(run.call_count, 1)
                    args = run.call_args.args[0]
                    self.assertEqual(args[:5], [str(LAUNCH.PYTHON), '-m', 'pip', 'install', '--no-deps'])
                    self.assertEqual(args[5:], ['-e', str(top)])
                    self.assertEqual(LAUNCH.prior_state(), LAUNCH.environment_state())
                    self.assertTrue((LAUNCH.VENV/'pyvenv.cfg').is_file())

    def test_existing_good_environment_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                self.make_fake_venv(LAUNCH.VENV)
                LAUNCH.STATE_FILE.write_text(json.dumps(LAUNCH.environment_state()), encoding='utf-8')
                with patch.object(LAUNCH, 'installed_ok', return_value=True), \
                     patch.object(LAUNCH, 'private_python_version', return_value=LAUNCH.sys.version_info[:2]), \
                     patch.object(LAUNCH.subprocess, 'run') as run:
                    self.assertTrue(LAUNCH.setup())
                    run.assert_not_called()

    def test_first_install_uses_short_private_environment_and_notebook_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                def faux_run(cmd, **kwargs):
                    if cmd[:3] == [LAUNCH.sys.executable, '-m', 'venv']:
                        self.make_fake_venv(LAUNCH.VENV)
                    return SimpleNamespace(returncode=0)
                with patch.object(LAUNCH, 'installed_ok', side_effect=[False, True]), \
                     patch.object(LAUNCH, 'dependencies_ok', return_value=False), \
                     patch.object(LAUNCH.subprocess, 'run', side_effect=faux_run) as run:
                    self.assertTrue(LAUNCH.setup())
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(run.call_args_list[0].args[0][-1], str(LAUNCH.VENV))
                    self.assertEqual(run.call_args_list[1].args[0][-1], str(top)+'[notebook]')
                    self.assertEqual(LAUNCH.prior_state(), LAUNCH.environment_state())

    def test_legacy_in_repo_environment_is_not_used_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            legacy = top/'.venv'; legacy.mkdir()
            (legacy/'scientific-data.txt').write_text('safe', encoding='utf-8')
            with self.fake_location(top), patch.object(LAUNCH.sys, 'platform', 'win32'):
                def faux_run(cmd, **kwargs):
                    if cmd[:3] == [LAUNCH.sys.executable, '-m', 'venv']:
                        self.make_fake_venv(LAUNCH.VENV)
                    return SimpleNamespace(returncode=0)
                with patch.object(LAUNCH, 'installed_ok', side_effect=[False, True]), \
                     patch.object(LAUNCH, 'dependencies_ok', return_value=False), \
                     patch.object(LAUNCH.subprocess, 'run', side_effect=faux_run):
                    self.assertTrue(LAUNCH.setup())
                    self.assertEqual((legacy/'scientific-data.txt').read_text(), 'safe')

    def test_unrelated_folder_at_env_path_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                LAUNCH.VENV.mkdir(parents=True)
                (LAUNCH.VENV/'keep.txt').write_text('safe', encoding='utf-8')
                with patch.object(LAUNCH.subprocess, 'run') as run:
                    self.assertFalse(LAUNCH.setup())
                    run.assert_not_called()
                    self.assertEqual((LAUNCH.VENV/'keep.txt').read_text(), 'safe')

    def test_mocked_symlink_is_never_deleted(self):
        # Always exercise refusal independently of Windows symlink privileges.
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                target = top/'target'; target.mkdir()
                (target/'keep.txt').write_text('safe', encoding='utf-8')
                original = Path.is_symlink
                def fake_is_symlink(path):
                    return path == LAUNCH.VENV or original(path)
                with patch.object(Path, 'is_symlink', fake_is_symlink), \
                     patch.object(LAUNCH.subprocess, 'run') as run, \
                     patch.object(LAUNCH.shutil, 'rmtree') as remove:
                    self.assertFalse(LAUNCH.setup())
                    run.assert_not_called()
                    remove.assert_not_called()
                self.assertEqual((target/'keep.txt').read_text(encoding='utf-8'), 'safe')

    def test_real_symlink_is_never_deleted_when_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                LAUNCH.VENV.parent.mkdir(parents=True, exist_ok=True)
                target = top/'target'; target.mkdir()
                (target/'keep.txt').write_text('safe', encoding='utf-8')
                try:
                    LAUNCH.VENV.symlink_to(target, target_is_directory=True)
                except OSError as exc:
                    unsupported = {errno.EPERM, errno.EACCES, errno.ENOSYS,
                                   getattr(errno, 'ENOTSUP', -1), getattr(errno, 'EOPNOTSUPP', -1)}
                    if exc.errno in unsupported or getattr(exc, 'winerror', None) == 1314:
                        self.skipTest(f'Directory symlink creation unavailable: {exc}')
                    raise
                with patch.object(LAUNCH.subprocess, 'run') as run, \
                     patch.object(LAUNCH.shutil, 'rmtree') as remove:
                    self.assertFalse(LAUNCH.setup())
                    run.assert_not_called()
                    remove.assert_not_called()
                self.assertTrue(LAUNCH.VENV.is_symlink())
                self.assertEqual((target/'keep.txt').read_text(encoding='utf-8'), 'safe')

    def test_different_existing_python_is_archived_then_recreated(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                self.make_fake_venv(LAUNCH.VENV)
                (LAUNCH.VENV/'old-state.txt').write_text('old', encoding='utf-8')
                def faux_run(cmd, **kwargs):
                    if cmd[:3] == [LAUNCH.sys.executable, '-m', 'venv']:
                        self.make_fake_venv(LAUNCH.VENV)
                    return SimpleNamespace(returncode=0)
                with patch.object(LAUNCH, 'private_python_version', return_value=(3, 15)), \
                     patch.object(LAUNCH, 'installed_ok', side_effect=[False, True]), \
                     patch.object(LAUNCH, 'dependencies_ok', return_value=False), \
                     patch.object(LAUNCH.subprocess, 'run', side_effect=faux_run):
                    self.assertTrue(LAUNCH.setup())
                    self.assertTrue((LAUNCH.VENV/'pyvenv.cfg').exists())
                    self.assertFalse((LAUNCH.VENV/'old-state.txt').exists())

    def test_diagnostic_probe_prints_precise_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)/'repo'; top.mkdir()
            with self.fake_location(top):
                self.make_fake_venv(LAUNCH.VENV)
                with patch.object(LAUNCH.subprocess, 'run', return_value=SimpleNamespace(
                    stdout='    ERROR importing jupyterlab : ImportError: missing ABI', stderr='', returncode=0)), \
                     patch.object(LAUNCH, 'say') as say:
                    LAUNCH.show_install_diagnostics()
                    self.assertTrue(any('ImportError' in c.args[0] for c in say.call_args_list))

    def test_launch_invokes_module_not_stale_windows_console_entrypoint(self):
        with patch.object(LAUNCH.subprocess, 'call', return_value=0) as call:
            self.assertEqual(LAUNCH.launch(), 0)
            self.assertEqual(call.call_args.args[0],
                             [str(LAUNCH.PYTHON), '-m', 'jupyterlab', 'MDTestWorkbench.ipynb'])
            self.assertEqual(call.call_args.kwargs['cwd'], ROOT)


if __name__ == '__main__':
    unittest.main()
