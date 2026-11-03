"""SteamCMD bootstrap and a terminal-owned authentication spike.

Passwords and Guard codes are entered directly into SteamCMD, not into this app.
Backend-owned cache/log confidentiality still requires native-platform review.
"""
import os
import re
from pathlib import Path
import shutil
import ssl
import certifi
import signal
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from .errors import DowngradeError, fail
from .files import inside, is_link, atomic_json
from .platforms import host

URLS = {
    'windows': 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip',
    'linux': 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz',
}


def extract(archive, destination, windows, cancel=lambda: None):
    """Extract only regular files/directories; precheck the entire archive."""
    entries = []
    with (zipfile.ZipFile(archive) if windows else tarfile.open(archive, 'r:gz')) as source:
        members = source.infolist() if windows else source
        total = 0
        seen = set()
        for index, member in enumerate(members):
            cancel()
            if index >= 10000:
                fail('UNSAFE_ARCHIVE', 'SteamCMD archive exceeds bootstrap limits.')
            name = member.filename if windows else member.name
            # Valve's tar uses a leading ./, which is benign.
            while name.startswith('./'):
                name = name[2:]
            name = name.rstrip('/')
            if not name:
                continue
            target = inside(destination, name)
            directory = member.is_dir() if windows else member.isdir()
            if windows:
                mode = (member.external_attr >> 16) & 0o170000
                if mode not in (0, 0o100000, 0o040000):
                    fail('UNSAFE_ARCHIVE', 'Archive contains a special file.')
                size = member.file_size
            else:
                if not (member.isfile() or member.isdir()):
                    fail('UNSAFE_ARCHIVE', 'Archive contains a link or special file.')
                size = member.size
            if name.casefold() in seen:
                fail('UNSAFE_ARCHIVE', 'Archive contains duplicate paths.')
            seen.add(name.casefold())
            total += size
            if total > 512 * 1024 * 1024:
                fail('UNSAFE_ARCHIVE', 'SteamCMD archive exceeds bootstrap limits.')
            entries.append((member, target, directory))
        for member, target, directory in entries:
            cancel()
            if directory:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with (source.open(member) if windows else source.extractfile(member)) as inp, target.open('wb') as out:
                    while chunk := inp.read(1024 * 1024):
                        cancel()
                        out.write(chunk)
                if not windows:
                    target.chmod(0o700 if member.mode & 0o111 else 0o600)


class SteamCmdProvider:
    def __init__(self, root, platform=None):
        self.root = Path(root).absolute()
        self.platform = platform or host()
        self.executable = inside(self.root, 'steamcmd.exe' if self.platform == 'windows' else 'steamcmd.sh')

    def check(self, allow_incomplete=False):
        if not allow_incomplete and inside(self.root, '.bootstrap-incomplete.json').exists():
            fail('STEAMCMD_NOT_FOUND', 'SteamCMD setup was interrupted. Retry setup before downloading.')
        if not self.executable.is_file():
            fail('STEAMCMD_NOT_FOUND', f'SteamCMD executable is missing from {self.root}. Run --setup-steamcmd.')
        if self.platform == 'linux':
            binary = inside(self.root, 'linux32/steamcmd')
            if not binary.is_file():
                fail('STEAMCMD_NOT_FOUND', 'The SteamCMD linux32 binary is missing. Retry setup.')
            if not os.access(self.executable, os.X_OK) or not os.access(binary, os.X_OK):
                fail('PERMISSION_DENIED', 'SteamCMD is not executable; check permissions and noexec mounts.')
            if not any(Path(p).exists() for p in ('/lib/ld-linux.so.2', '/lib32/ld-linux.so.2')):
                fail('LINUX_RUNTIME_MISSING', 'SteamCMD requires a 32-bit glibc loader and runtime. See Linux setup documentation.')
        return self.executable

    def ensure_available(self, cancel=lambda: None):
        cancel()
        incomplete = inside(self.root, '.bootstrap-incomplete.json')
        if not incomplete.exists() and self.executable.is_file() and (self.platform == 'windows' or (self.root / 'linux32/steamcmd').is_file()):
            return self.check()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_json(incomplete, {'schema': 1})
        # Extraction in a private sibling prevents a failed archive download from marking setup complete.
        with tempfile.TemporaryDirectory(prefix='.bootstrap-', dir=self.root.parent) as tmp:
            tmp = Path(tmp)
            archive = tmp / 'download.partial'
            try:
                # Use an explicitly packaged CA trust bundle. Frozen PyInstaller apps
                # cannot reliably discover distro CA paths (e.g. on Bazzite).
                # Certificate/hostname verification stays enabled.
                tls_context = ssl.create_default_context(cafile=certifi.where())
                with urllib.request.urlopen(URLS[self.platform], timeout=30, context=tls_context) as inp, archive.open('wb') as out:
                    count = 0
                    while chunk := inp.read(1024 * 1024):
                        cancel()
                        count += len(chunk)
                        if count > 128 * 1024 * 1024:
                            fail('STEAMCMD_BOOTSTRAP_FAILED', 'Bootstrap download exceeded its size limit.')
                        out.write(chunk)
                unpacked = tmp / 'unpacked'
                unpacked.mkdir()
                extract(archive, unpacked, self.platform == 'windows', cancel)
                expected = unpacked / self.executable.name
                if not expected.is_file() or (self.platform == 'linux' and not (unpacked / 'linux32/steamcmd').is_file()):
                    fail('STEAMCMD_BOOTSTRAP_FAILED', 'Valve archive is missing its expected executable.')
                # Move only archive files, with a destination boundary check on every file.
                # Publish the launcher last so interrupted setup is retried.
                for source in sorted(unpacked.rglob('*'), key=lambda p: p == expected):
                    cancel()
                    target = inside(self.root, source.relative_to(unpacked).as_posix())
                    if source.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        fd, temporary = tempfile.mkstemp(prefix='.bootstrap-copy-', dir=target.parent)
                        os.close(fd)
                        try:
                            shutil.copy2(source, temporary)
                            cancel()
                            os.replace(temporary, target)
                        finally:
                            Path(temporary).unlink(missing_ok=True)
            except (urllib.error.URLError, TimeoutError) as error:
                reason = getattr(error, 'reason', error)
                is_tls = isinstance(reason, (ssl.SSLError, ssl.CertificateError)) or 'CERTIFICATE_VERIFY_FAILED' in str(reason)
                if is_tls:
                    fail('TLS_VERIFY_FAILED', 'SteamCMD download failed certificate verification. Check the system clock, network interception, and CA trust.')
                fail('NETWORK_ERROR', f'Unable to reach the official SteamCMD download server over HTTPS ({type(reason).__name__}). Check DNS, firewall, proxy, and network connectivity.')
            except (tarfile.TarError, zipfile.BadZipFile):
                fail('STEAMCMD_BOOTSTRAP_FAILED', 'Invalid SteamCMD archive. Retry setup.')
        executable = self.check(allow_incomplete=True)
        incomplete.unlink()
        return executable

    def candidate_roots(self):
        return [self.root / 'steamapps/content/app_377160',
                self.root / 'linux32/steamapps/content/app_377160']

    def check_download_space(self, manifest, cancel=lambda: None):
        """Budget missing bytes plus one replacement file on the download volume."""
        manifest.require_inventory()
        relative = ('steamapps/content/app_377160' if self.platform == 'windows' else
                    'linux32/steamapps/content/app_377160')
        root = inside(self.root, relative)
        volume = root
        while not volume.exists():
            volume = volume.parent
        missing = largest = 0
        for depot in manifest.depots:
            for spec in depot['files']:
                cancel()
                path = inside(root, f"depot_{depot['id']}/{spec['path']}")
                present = min(path.stat().st_size, spec['size']) if path.is_file() else 0
                missing += spec['size'] - present
                largest = max(largest, spec['size'])
        required = missing + largest + 64 * 1024 * 1024
        if shutil.disk_usage(volume).free < required:
            fail('INSUFFICIENT_SPACE', f'Not enough free space for downloads at {root}. '
                 f'Allow at least {required:,} bytes for missing content, temporary files and overhead.')


def reset_incomplete_downloads(provider, manifest, cancel=lambda: None):
    """Invalidate SteamCMD completion records whose depot bytes no longer verify.

    Cleanup or an interrupted download can leave state_*.patch behind even when
    content is absent. Keep the downloaded bytes and unrelated backend state.
    """
    from .manifest import verify_file

    manifest.require_inventory()
    for root in provider.candidate_roots():
        if not root.is_dir():
            continue
        for depot in manifest.depots:
            cancel()
            state = inside(root, f"state_377160_{depot['id']}.patch")
            if not state.is_file():
                continue
            for spec in depot['files']:
                cancel()
                try:
                    verify_file(inside(root, f"depot_{depot['id']}/{spec['path']}"), spec)
                except DowngradeError as error:
                    if error.code not in ('DEPOT_INCOMPLETE', 'HASH_MISMATCH'):
                        raise
                    state.unlink()
                    break


def classify(returncode, output):
    """Classify explicit failure records, not isolated words in startup chatter."""
    import re
    lower = output.lower()
    for needles, code in [
        (('certificate_verify_failed', 'certificate verify failed', 'ssl error', 'ssl connect error'), 'TLS_VERIFY_FAILED'),
        (('rate limit exceeded', 'rate limited'), 'RATE_LIMITED'),
        (('invalid password', 'invalid login', 'invalid auth code', 'invalid login auth code'), 'AUTH_DENIED'),
        (('no subscription', 'missing license', 'access denied'), 'DEPOT_ACCESS_DENIED'),
    ]:
        if any(n in lower for n in needles):
            return code
    # ILocalize::AddFile() failed to load optional translation resources is a
    # normal first-bootstrap warning. A bare "failed" also matches account names.
    if (re.search(r'(?:^|[\r\n])\s*(?:error!|failed\b)', lower)
            or any(n in lower for n in ('error! ', 'depot download failed', 'failed to download depot'))):
        return 'DEPOT_DOWNLOAD_FAILED'
    if returncode:
        return 'DEPOT_DOWNLOAD_FAILED'
    if any(n in lower for n in ('steam guard', 'two-factor', 'authenticator')):
        return 'AUTH_PENDING'
    return None


def session_failure(code, phase, depot_id=None):
    """Fixed diagnostic text: never include raw Steam output or credentials."""
    stage = {'startup': 'SteamCMD startup', 'logout': 'Steam logout',
             'clear_credentials': 'clearing saved Steam credentials', 'login': 'Steam login',
             'download': f'download of depot {depot_id}', 'quit': 'SteamCMD shutdown'}[phase]
    messages = {
        'TLS_VERIFY_FAILED': 'SteamCMD reported a certificate or TLS connection error. Check the system clock, certificates and network.',
        'RATE_LIMITED': 'Steam reported a rate limit. Wait before retrying login.',
        'AUTH_DENIED': 'Steam rejected the login or authentication code. Check the account details and retry.',
        'DEPOT_ACCESS_DENIED': 'Steam denied access to the requested content. Check Fallout 4 and DLC ownership on this account.',
        'DEPOT_DOWNLOAD_FAILED': 'SteamCMD reported an explicit command failure.',
    }
    if code == 'DEPOT_DOWNLOAD_FAILED' and phase == 'startup':
        code = 'STEAMCMD_BOOTSTRAP_FAILED'
    return code, f"During {stage}: {messages.get(code, 'SteamCMD could not finish starting. Retry setup.')} Game files were not modified."


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # taskkill receives only the child PID; never game/user process names.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def interactive_download(provider, manifest, cancel=lambda: None, timeout=24*60*60):
    """Experimental terminal flow. Completion MUST be checked by the verifier.

    No credential collection, argv credentials, output capture or persistent login
    scripts. SteamCMD owns its terminal prompts and may persist its own session.
    """
    executable = provider.check()
    script = inside(provider.root, 'folon-depots.txt')
    lines = ['@ShutdownOnFailedCommand 1', '@NoPromptForPassword 1']
    lines += [f"download_depot 377160 {d['id']} {d['manifest']}" for d in manifest.depots]
    script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('SteamCMD will open in this terminal. Enter login <your username> and follow its prompts.')
    print('After login, enter: runscript "' + str(script) + '"')
    print('After all downloads finish, enter quit. The downgrader then verifies the content.')
    print('Do not enable SteamCMD debug logging or share its private cache/logs.')
    try:
        process = subprocess.Popen([str(executable)], cwd=provider.root,
            start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
    except FileNotFoundError:
        fail('STEAMCMD_NOT_FOUND', 'SteamCMD or its loader disappeared. Retry setup and check the runtime.')
    except PermissionError:
        fail('PERMISSION_DENIED', 'Cannot execute SteamCMD. Check permissions and noexec mounts.')
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            cancel()
            if time.monotonic() > deadline:
                fail('NETWORK_TIMEOUT', 'SteamCMD exceeded the total session time limit. Downloads were retained.')
            time.sleep(0.1)
        if process.returncode:
            fail('DEPOT_DOWNLOAD_FAILED', 'SteamCMD exited unsuccessfully. Downloads were retained.')
    finally:
        stop_process(process)


class _PipeSession:
    """SteamCMD over stdin/stdout pipes (Linux; also used by tests)."""

    def __init__(self, executable, cwd):
        self.process = subprocess.Popen([str(executable)], cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)

    def read(self):
        return self.process.stdout.read1(4096)

    def write(self, value):
        self.process.stdin.write((value + '\n').encode('utf-8'))
        self.process.stdin.flush()

    def poll(self):
        return self.process.poll()

    def stop(self):
        stop_process(self.process)

    def close(self):
        self.process.stdin.close()
        self.process.stdout.close()


class _ConPtySession:
    """SteamCMD inside a Windows pseudo-console (ConPTY).

    steamcmd.exe only flushes its ``Steam>`` prompt when attached to a console,
    so piped stdout never shows it. A hidden ConPTY gives it a console while the
    app still owns all input and output; the user never sees a terminal.
    """

    def __init__(self, executable, cwd):
        from winpty import PtyProcess
        self.process = PtyProcess.spawn([str(executable)], cwd=str(cwd), dimensions=(50, 300))

    def read(self):
        try:
            return self.process.read(4096).encode('utf-8')
        except (EOFError, OSError):
            # The pseudo-console closed (SteamCMD exited or was stopped).
            return b''

    def write(self, value):
        self.process.write(value + '\r')

    def poll(self):
        if self.process.isalive():
            return None
        return self.process.exitstatus or 0

    def stop(self):
        if self.process.isalive():
            subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.process.close(force=True)
        except Exception:
            pass

    def close(self):
        pass


def open_session(executable, cwd, use_conpty=None):
    """Pick the console transport: ConPTY on Windows, pipes elsewhere."""
    if use_conpty is None:
        use_conpty = os.name == 'nt'
    if use_conpty:
        try:
            return _ConPtySession(executable, cwd)
        except ImportError:
            fail('STEAMCMD_BOOTSTRAP_FAILED', 'The Windows console component (pywinpty) is missing. Reinstall the downgrader.')
    return _PipeSession(executable, cwd)


# CSI/OSC terminal sequences emitted by a pseudo-console (colours, cursor, title).
ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\^_]')
# "Update state (0x61) downloading, progress: 12.34 (1234 / 56789)"
PROGRESS = re.compile(r'progress:\s*(\d{1,3})(?:\.\d+)?\s*\(')


def gui_download(provider, manifest, ask, emit, cancel=lambda: None, timeout=24*60*60, use_conpty=None):
    """Pipe-based GUI spike. Only fixed status messages cross the UI boundary.

    ask(kind) must run its dialog on the GUI thread. Raw backend output is neither
    displayed nor persisted. SteamCMD's own logging remains outside this guarantee.
    """
    import queue
    import re
    import threading
    executable = provider.check()
    username = ask('username')
    # Opt-in diagnostics: FOLON_TRACE_STEAMCMD=<file>. Credentials are redacted.
    secrets = [username] if username else []
    trace = (open(os.environ['FOLON_TRACE_STEAMCMD'], 'a', encoding='utf-8')
             if os.environ.get('FOLON_TRACE_STEAMCMD') else None)
    if not re.fullmatch(r'[A-Za-z0-9_]+', username or ''):
        fail('AUTH_DENIED', 'Enter a Steam account name containing letters, digits or underscores.')
    try:
        process = open_session(executable, provider.root, use_conpty)
    except FileNotFoundError:
        fail('STEAMCMD_NOT_FOUND', 'SteamCMD or its runtime loader is missing. Retry setup.')
    chunks = queue.Queue(maxsize=128)
    stopped = threading.Event()
    def reader():
        while not stopped.is_set():
            chunk = process.read()
            if not chunk:
                break
            while not stopped.is_set():
                try:
                    chunks.put(chunk, timeout=0.1)
                    break
                except queue.Full:
                    pass
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    def send(value):
        if any(c in value for c in ('\r', '\n', '\x00')):
            fail('AUTH_DENIED', 'Steam input cannot contain line breaks or NUL characters.')
        process.write(value)
    buffer = ''
    phase = 'startup'
    depot_index = 0
    logged_in = False
    password_requested = False
    session_retry_count = 0
    mobile_approval_notified = False
    downloaded = False
    last_percent = -1
    started = time.monotonic()
    phase_started = started
    try:
        while True:
            cancel()
            if time.monotonic() - started > timeout:
                fail('NETWORK_TIMEOUT', 'SteamCMD exceeded the total download time limit.')
            if phase in ('startup', 'logout', 'clear_credentials', 'login') and time.monotonic() - phase_started > 300:
                fail('AUTH_PENDING', 'SteamCMD did not finish setup or authentication within five minutes. Retry login.')
            try:
                raw = chunks.get(timeout=0.1)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            text = ANSI.sub('', raw.decode('utf-8', errors='replace'))
            if trace:
                line = text
                for hidden in secrets:
                    line = line.replace(hidden, '***')
                trace.write(f'[{phase}] {line!r}\n')
                trace.flush()
            buffer = (buffer + text)[-16384:]
            lower = buffer.lower()
            code = classify(0, buffer)
            if code and code != 'AUTH_PENDING':
                depot_id = manifest.depots[depot_index]['id'] if depot_index < len(manifest.depots) else None
                error_code, message = session_failure(code, phase, depot_id)
                fail(error_code, message)
            if phase == 'startup' and 'Steam>' in buffer:
                # Clear the previous SteamCMD account before considering the
                # credentials supplied for this download. Do not delete depot files.
                send('logout')
                phase, buffer = 'logout', ''
                phase_started = time.monotonic()
                emit({'stage': 'authenticate', 'auth_state': 'waiting',
                      'message': 'Preparing a fresh Steam sign-in…'})
                continue
            if phase == 'logout' and 'Steam>' in buffer:
                send('clear_credentials')
                phase, buffer = 'clear_credentials', ''
                phase_started = time.monotonic()
                continue
            if phase == 'clear_credentials' and 'Steam>' in buffer:
                logged_in = False
                password_requested = False
                send('login ' + username)
                phase, buffer = 'login', ''
                phase_started = time.monotonic()
                emit({'stage': 'authenticate', 'auth_state': 'waiting', 'message': 'Signing in to Steam…'})
                continue
            if phase == 'login':
                if 'timed out waiting for confirmation' in lower or 'error (timeout)' in lower:
                    fail('AUTH_PENDING', 'Steam timed out waiting for your approval. Wait a minute, then try again and '
                         'approve the newest sign-in request in the Steam mobile app. Avoid retrying repeatedly: '
                         'each attempt queues another request. Game files were not modified.')
                if 'password:' in lower or 'password: ' in lower:
                    password_requested = True
                    secret = ask('password')
                    secrets.append(secret)
                    send(secret)
                    secret = ''
                    buffer = ''
                    phase_started = time.monotonic()
                    continue
                if ('code:' in lower or 'code from' in lower or 'enter the current code' in lower):
                    secret = ask('steam_guard')
                    secrets.append(secret)
                    send(secret)
                    secret = ''
                    buffer = ''
                    phase_started = time.monotonic()
                    continue
                if not mobile_approval_notified and (('mobile' in lower and any(x in lower for x in ('confirm', 'approval', 'approve', 'notification', 'app'))) or ('steam guard' in lower and any(x in lower for x in ('confirm', 'approve', 'app')))):
                    emit({'stage': 'authenticate', 'auth_state': 'mobile', 'message': 'Action required: open the Steam mobile app and approve this sign-in request.'})
                    mobile_approval_notified = True
                if re.search(r'Waiting for user info.*?OK', buffer, re.DOTALL | re.IGNORECASE):
                    logged_in = True
                if 'Steam>' in buffer:
                    if not logged_in:
                        fail('AUTH_PENDING', 'SteamCMD returned without a confirmed login. Retry authentication.')
                    if not password_requested:
                        # Some SteamCMD versions silently reuse a login even after
                        # clear_credentials. Retry the cleanup *in the same session*
                        # once, without touching downloaded depots or exposing an
                        # internal cache-error message to users.
                        if session_retry_count < 1:
                            session_retry_count += 1
                            send('logout')
                            phase, buffer = 'logout', ''
                            phase_started = time.monotonic()
                            mobile_approval_notified = False
                            emit({'stage': 'authenticate', 'auth_state': 'waiting',
                                  'message': 'Refreshing Steam sign-in…'})
                            continue
                        fail('AUTH_DENIED', 'SteamCMD could not verify a fresh sign-in for the selected account. Please retry authentication.')
                    phase, buffer = 'download', ''
                    depot = manifest.depots[depot_index]
                    send(f"download_depot 377160 {depot['id']} {depot['manifest']}")
                    emit({'stage': 'download', 'message': f"Downloading depot {depot['id']} ({depot_index + 1}/{len(manifest.depots)})"})
                    continue
            if phase == 'download':
                found = PROGRESS.findall(buffer)
                if found and int(found[-1]) != last_percent and int(found[-1]) <= 100:
                    last_percent = int(found[-1])
                    emit({'stage': 'download', 'percent': last_percent, 'depot': depot_index + 1,
                          'depots': len(manifest.depots),
                          'message': f"Downloading depot {manifest.depots[depot_index]['id']} ({depot_index + 1}/{len(manifest.depots)}): {last_percent}%"})
                if 'depot download complete' in lower:
                    downloaded = True
                if 'Steam>' in buffer:
                    if not downloaded:
                        fail('DEPOT_DOWNLOAD_FAILED', 'SteamCMD did not confirm completion of the current depot.')
                    depot_index += 1
                    buffer, downloaded, last_percent = '', False, -1
                    if depot_index == len(manifest.depots):
                        send('quit')
                        phase = 'quit'
                    else:
                        depot = manifest.depots[depot_index]
                        send(f"download_depot 377160 {depot['id']} {depot['manifest']}")
                        emit({'stage': 'download', 'message': f"Downloading depot {depot['id']} ({depot_index + 1}/{len(manifest.depots)})"})
        if process.poll() or phase != 'quit':
            fail('DEPOT_DOWNLOAD_FAILED', 'SteamCMD exited before all required downloads completed.')
    finally:
        stopped.set()
        if trace:
            trace.close()
        process.stop()
        thread.join(timeout=5)
        process.close()
