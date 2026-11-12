#!/usr/bin/env python3
"""MDTest Easy Start: safely install and open the unchanged scientific package.

Windows uses a SHORT per-user environment path outside the downloaded ZIP.
This avoids legacy Windows MAX_PATH failures during JupyterLab installation and
keeps Python executable wrappers independent of where the MDTest source moves.
No statistical code or analysis settings are touched.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import textwrap

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / 'MDTestWorkbench.ipynb'
EXPECTED_MODULE = ROOT / 'src/mdtest/__init__.py'


def choose_environment_dir(root: Path, platform: str | None = None,
                           environ: dict[str, str] | None = None) -> Path:
    """Choose a user-writable short location on Windows, the usual venv elsewhere.

    Explicit parameters allow portable tests without requiring a Windows runner.
    """
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    if platform.startswith('win'):
        local = environ.get('LOCALAPPDATA') or (
            str(Path(environ.get('USERPROFILE', str(Path.home()))) / 'AppData' / 'Local')
        )
        # JupyterLab has deeply nested assets (galata/static); avoid long ZIP roots.
        return Path(local) / 'MDTest' / 'e'
    return root / '.venv'


VENV = choose_environment_dir(ROOT)
PYTHON = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
STATE_FILE = VENV / '.mdtest_environment.json'


def say(message: str) -> None:
    print(message, flush=True)


def project_version() -> str:
    with (ROOT / 'pyproject.toml').open('rb') as file:
        return tomllib.load(file)['project']['version']


def normal_path(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def environment_state() -> dict[str, str]:
    return {'install_folder': normal_path(ROOT), 'version': project_version(),
            'python': normal_path(PYTHON)}


def prior_state() -> dict[str, str] | None:
    try:
        data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def environment_needs_repair() -> str | None:
    """Return a reason for refresh; an old editable link needs relinking, not moving."""
    if not VENV.exists() and not VENV.is_symlink():
        return None
    if VENV.is_symlink() or not VENV.is_dir():
        return 'The private environment location is not an ordinary folder.'
    if not (VENV / 'pyvenv.cfg').is_file():
        return 'The private environment is incomplete.'
    if not PYTHON.is_file():
        return 'The private Python executable is missing.'
    saved = prior_state()
    if saved is None:
        return 'The existing environment needs a one-time installation check.'
    expected = environment_state()
    if saved.get('python') != expected['python']:
        return 'The private Python location has changed.'
    if saved.get('version') != expected['version']:
        return 'The MDTest package version has changed.'
    if saved.get('install_folder') != expected['install_folder']:
        return 'The MDTest source folder has moved; updating its installed link.'
    return None


def dependencies_ok() -> bool:
    """Check prerequisites independently from the editable source link."""
    if not PYTHON.is_file():
        return False
    try:
        result = subprocess.run(
            [str(PYTHON), '-c',
             'import numpy, scipy, pandas, matplotlib, ipywidgets, jupyterlab, nbconvert'],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=30)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def installed_ok() -> bool:
    if not PYTHON.is_file():
        return False
    check = (
        'import mdtest, ipywidgets, jupyterlab, nbconvert, pathlib, sys; '
        'want=pathlib.Path(sys.argv[1]).resolve(); '
        'assert pathlib.Path(mdtest.__file__).resolve()==want, '
        "'MDTest is imported from a different installation'; "
        'assert mdtest.__version__==sys.argv[2]'
    )
    try:
        proc = subprocess.run(
            [str(PYTHON), '-c', check, str(EXPECTED_MODULE), project_version()],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def private_python_version() -> tuple[int, int] | None:
    """Identify the existing environment's interpreter (never infer from its name)."""
    if not PYTHON.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(PYTHON), '-c', 'import sys; print(sys.version_info.major, sys.version_info.minor)'],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        pieces = proc.stdout.strip().split()
        return (int(pieces[0]), int(pieces[1])) if proc.returncode == 0 and len(pieces) == 2 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def show_install_diagnostics() -> None:
    """Explain a failed post-install check; the previous launcher suppressed all output."""
    say('  Detailed notebook check (copy this section when requesting help):')
    if not PYTHON.is_file():
        say('    Missing environment Python: ' + str(PYTHON))
        return
    probe = textwrap.dedent(r"""
        import importlib, pathlib, sys, traceback
        print('    Interpreter:', sys.executable)
        print('    Python version:', sys.version.split()[0])
        for name in ('numpy', 'scipy', 'pandas', 'matplotlib',
                     'ipywidgets', 'jupyterlab', 'nbconvert', 'mdtest'):
            try:
                module = importlib.import_module(name)
                print('    OK:', name, getattr(module, '__version__', '(no version)'))
                if name == 'mdtest':
                    actual = pathlib.Path(module.__file__).resolve()
                    expected = pathlib.Path(sys.argv[1]).resolve()
                    print('    MDTest imported from:', actual)
                    if actual != expected:
                        print('    ERROR: Wrong MDTest installation; expected:', expected)
                    if module.__version__ != sys.argv[2]:
                        print('    ERROR: MDTest version mismatch; expected:', sys.argv[2])
            except Exception as exc:
                print('    ERROR importing', name, ':', type(exc).__name__ + ':', exc)
                traceback.print_exc(limit=2, file=sys.stdout)
        """)
    try:
        proc = subprocess.run(
            [str(PYTHON), '-c', probe, str(EXPECTED_MODULE), project_version()],
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
        for line in (proc.stdout + '\n' + proc.stderr).strip().splitlines()[:100]:
            say('    ' + line)
        if proc.returncode:
            say('    Diagnostic process exited with status ' + str(proc.returncode))
    except (OSError, subprocess.TimeoutExpired) as exc:
        say('    Could not inspect environment: ' + str(exc))


def choose_backup() -> Path:
    for index in range(1, 1000):
        candidate = VENV.parent / f'e_previous_{index}'
        if not candidate.exists():
            return candidate
    raise OSError('Too many archived environments; contact support.')


def setup() -> bool:
    say('\nStep 1/3  Checking MDTest installation')
    say('  Private Python environment: ' + str(VENV))
    if sys.platform.startswith('win'):
        say('  This short Windows path avoids long-filename errors in JupyterLab.')
        legacy = ROOT / '.venv'
        if legacy.is_dir():
            say('  An older .venv folder was found beside MDTest; it will NOT be used.')
            say('  You can delete that old .venv later, after verifying the new launch.')
    problem = environment_needs_repair()
    backup: Path | None = None
    if problem:
        say('  ' + problem)
    # Never follow symlinks or replace arbitrary user folders.
    if VENV.is_symlink() or (VENV.exists() and not VENV.is_dir()):
        say('  ERROR: The chosen environment path is not a normal directory.')
        say('  See docs/INSTALL_HELP.md; no files have been deleted.')
        return False
    # An unrelated folder must never be treated as an MDTest environment.
    if VENV.exists() and not (VENV / 'pyvenv.cfg').is_file():
        say('  ERROR: A folder already exists at the private environment location.')
        say('  It is not identified as a Python environment and was not changed.')
        say('  See docs/INSTALL_HELP.md for guidance.')
        return False
    # A private environment created using a different Python minor version
    # cannot safely be reused, including on Windows when START selects a new
    # interpreter. Archive before installing under the selected interpreter.
    if VENV.exists() and PYTHON.is_file():
        found = private_python_version()
        expected = (sys.version_info.major, sys.version_info.minor)
        if found != expected:
            say('  Existing private environment uses Python ' + str(found) +
                '; START is using ' + '.'.join(map(str, expected)) + '.')
            say('  Preserving the old environment and creating one for this Python.')
            try:
                old = choose_backup()
                VENV.rename(old)
                backup = old
            except OSError as exc:
                say('  ERROR: Close Jupyter and retry: ' + str(exc))
                return False
    # A genuinely broken Python environment is archived, not erased.
    if VENV.exists() and not PYTHON.is_file():
        try:
            backup = choose_backup()
            VENV.rename(backup)
            say('  Archived an incomplete environment; preparing a clean one.')
        except OSError as exc:
            say('  ERROR: Close running MDTest windows and retry: ' + str(exc))
            return False
    try:
        VENV.parent.mkdir(parents=True, exist_ok=True)
        if not PYTHON.is_file():
            say('  Creating the private Python environment.')
            subprocess.run([sys.executable, '-m', 'venv', str(VENV)], cwd=ROOT, check=True)
        say('Step 2/3  Checking MDTest and JupyterLab')
        if not installed_ok():
            if dependencies_ok():
                say('  Updating the MDTest source link; existing JupyterLab is retained.')
                subprocess.run([str(PYTHON), '-m', 'pip', 'install', '--no-deps',
                                '-e', str(ROOT)], cwd=ROOT, check=True)
            else:
                say('  Installing MDTest and the notebook components (internet needed).')
                subprocess.run([str(PYTHON), '-m', 'pip', 'install', '-e',
                                str(ROOT) + '[notebook]'], cwd=ROOT, check=True)
        if not installed_ok():
            say('  ERROR: Installation finished, but the notebook is not ready.')
            show_install_diagnostics()
            say('  See docs/MAC_START_GUIDE.html (macOS) or docs/INSTALL_HELP.md.')
            return False
        STATE_FILE.write_text(json.dumps(environment_state(), indent=2) + '\n',
                              encoding='utf-8')
        if backup is not None:
            try:
                shutil.rmtree(backup)
            except OSError:
                say('  The previous private environment is saved at ' + str(backup))
        say('  Ready. MDTest and JupyterLab are installed.')
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        say('  Installation did not complete: ' + str(exc))
        say('  If you saw a Windows long-path warning, ensure you started')
        say('  with the NEW launcher; it uses ' + str(VENV))
        say('  Do not change Windows settings or copy Python packages by hand.')
        say('  Other installation problems: docs/INSTALL_HELP.md')
        if backup is not None:
            say('  The previous environment was saved at ' + str(backup))
        return False


def launch() -> int:
    say('Step 3/3  Opening the Jupyter Workbench')
    say('  Your browser should open automatically.')
    say('  Otherwise copy the local http://localhost:... URL printed below.')
    say('  Keep this window open; press Ctrl+C to stop JupyterLab.\n')
    try:
        # This avoids path-dependent Windows jupyter-lab.exe wrappers.
        return subprocess.call([str(PYTHON), '-m', 'jupyterlab', NOTEBOOK.name], cwd=ROOT)
    except KeyboardInterrupt:
        say('\nMDTest Workbench stopped.')
        return 0
    except OSError as exc:
        say('Unable to start JupyterLab: ' + str(exc))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description='Install MDTest and open its Workbench')
    parser.add_argument('--check', action='store_true', help='inspect without installing')
    parser.add_argument('--setup-only', action='store_true', help='install without launching')
    args = parser.parse_args()
    os.chdir(ROOT)
    say('=' * 60)
    say(' MDTest  |  Stationarity-aware MD time-series analysis')
    say('=' * 60)
    if sys.version_info < (3, 11):
        say('Python 3.11 or newer is required; found ' + sys.version.split()[0])
        return 2
    if sys.platform == 'darwin' and sys.version_info >= (3, 16):
        say('Python ' + sys.version.split()[0] + ' has not been enabled for this Mac launcher.')
        say('For a reliable first installation, please install Python 3.13 or 3.12.')
        say('Open docs/MAC_START_GUIDE.html for illustrated instructions.')
        return 2
    if not (ROOT / 'pyproject.toml').is_file() or not NOTEBOOK.is_file() or not EXPECTED_MODULE.is_file():
        say('Missing package files; extract the complete MDTest ZIP before starting.')
        return 2
    if args.check:
        say('Python: ' + sys.version.split()[0])
        say('MDTest source: ' + str(ROOT))
        say('Private environment: ' + str(VENV))
        problem = environment_needs_repair()
        say('State: ' + ('REFRESH NEEDED: ' + problem if problem else
                         'READY' if installed_ok() else 'NOT INSTALLED YET'))
        return 0
    if not setup():
        return 1
    if args.setup_only:
        say('\nSetup complete. Double-click START to open the Workbench.')
        return 0
    return launch()


if __name__ == '__main__':
    raise SystemExit(main())
