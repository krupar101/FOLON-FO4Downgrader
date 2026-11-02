"""Shared FOLON wizard for Windows and Linux. UI never owns deployment state."""
import json
from pathlib import Path
import queue
import sys

from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QUrl
from PyQt5.QtGui import QIcon, QDesktopServices
from PyQt5.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit, QProgressBar, QToolButton,
    QStackedWidget, QVBoxLayout, QWidget, QSizePolicy)

from . import __version__
from .views import FolonPages, Resources
from .engine import Engine
from .errors import DowngradeError, fail


class Worker(QThread):
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(dict)
    progress = pyqtSignal(dict)
    prompt = pyqtSignal(str)

    def __init__(self, request, action, verified_cache=None, close_steam=False):
        super().__init__()
        self.answers = queue.Queue()
        self.engine = Engine(request, self.progress.emit, self.ask)
        self.action = action
        self.close_steam = close_steam
        if verified_cache is not None:
            self.engine.verified_cache = verified_cache

    def ask(self, kind):
        self.prompt.emit(kind)
        while True:
            self.engine.check_cancel()
            try:
                answer = self.answers.get(timeout=0.1)
                if answer is None:
                    fail('CANCELLED', 'Steam login was cancelled.')
                return answer
            except queue.Empty:
                pass

    def run(self):
        if self.close_steam:
            from .platforms import shutdown_steam
            try:
                self.progress.emit({'stage': 'steam_shutdown', 'message': 'Closing Steam…'})
                shutdown_steam(self.engine.check_cancel, lambda message: self.progress.emit(
                    {'stage': 'steam_shutdown', 'message': message}))
            except DowngradeError as error:
                self.failed.emit({'ok': False, 'error_code': error.code, 'message': error.message})
                return
        result = self.engine.run(self.action, confirmed=True)
        (self.succeeded if result['ok'] else self.failed).emit(result)


# These are milestones, not percentages of bytes or elapsed time.
ACTION_STEPS = {
    'preflight': [('preflight', 'Check installation')],
    'setup-steamcmd': [('preflight', 'Check installation'), ('bootstrap_steamcmd', 'Prepare SteamCMD')],
    'download': [('preflight', 'Check installation'), ('download', 'Download depots'),
                 ('verify_download', 'Verify downloads')],
    'verify-download': [('preflight', 'Check installation'), ('verify_download', 'Verify downloads')],
    'deploy': [('preflight', 'Check installation'), ('verify_download', 'Verify downloads'),
               ('prepare_deployment', 'Prepare changes'), ('deploy', 'Install files'),
               ('verify_target', 'Verify game')],
    'cleanup-downloads': [('cleanup_downloads', 'Remove downloads')],
}
STAGE_ALIASES = {'authenticate': 'download', 'steam_shutdown': 'preflight'}


class Window(QWidget, FolonPages):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.worker = None
        self.verified_cache = {}
        self.TabIndex = 1
        self.setObjectName('centralWidget')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle('Downgrader 2.0')
        self.setWindowIcon(QIcon(Resources.resource_path('img/FOLON256.png')))
        self.layout_root = QVBoxLayout(self)
        self.layout_root.setContentsMargins(12, 10, 12, 10)
        self.layout_root.setSpacing(8)
        self.layout_root.addStretch(0)
        self.activity = QWidget()
        self.activity.setObjectName('ActivityPanel')
        activity_layout = QVBoxLayout(self.activity)
        self.activity_title = QLabel('Working…')
        self.activity_title.setObjectName('ActivityTitle')
        activity_layout.addWidget(self.activity_title)
        self.step_row = QHBoxLayout()
        self.step_labels = []
        activity_layout.addLayout(self.step_row)
        self.activity_detail = QLabel('')
        self.activity_detail.setWordWrap(True)
        self.activity_detail.setObjectName('ActivityDetail')
        activity_layout.addWidget(self.activity_detail)
        self.mobile_help = QLabel('Check your Steam mobile app for a sign-in approval request. If a code is needed, an input will appear here. No confirmation is required in the downgrader for mobile approval.')
        self.mobile_help.setObjectName('MobileApprovalHelp')
        self.mobile_help.setWordWrap(True)
        self.mobile_help.hide()
        self.auth_hint_timer = QTimer(self)
        self.auth_hint_timer.setSingleShot(True)
        self.auth_hint_timer.setInterval(3000)
        self.auth_hint_timer.timeout.connect(self.show_delayed_auth_hint)
        activity_layout.addWidget(self.mobile_help)
        # Only show this action area when Steam needs a response from the user.
        self.auth_panel = QWidget()
        self.auth_panel.setObjectName('AuthenticationPanel')
        auth_layout = QVBoxLayout(self.auth_panel)
        self.auth_label = QLabel('Additional Steam verification required')
        self.auth_label.setObjectName('AuthenticationTitle')
        auth_layout.addWidget(self.auth_label)
        auth_row = QHBoxLayout()
        self.auth_entry = QLineEdit()
        self.auth_entry.setMinimumHeight(40)
        self.auth_entry.returnPressed.connect(self.submit_auth)
        self.auth_entry.textChanged.connect(lambda value: self.auth_submit.setEnabled(bool(value.strip())))
        self.auth_submit = QPushButton('Continue sign-in')
        self.auth_submit.setObjectName('PrimaryAction')
        self.auth_submit.clicked.connect(self.submit_auth)
        auth_row.addWidget(self.auth_entry, 1)
        auth_row.addWidget(self.auth_submit)
        auth_layout.addLayout(auth_row)
        self.auth_panel.hide()
        self.auth_kind = None
        activity_layout.addWidget(self.auth_panel)
        self.activity_bar = QProgressBar()
        self.activity_bar.setRange(0, 0)  # No fabricated percentage: real stage completion only.
        self.activity_bar.setTextVisible(False)
        activity_layout.addWidget(self.activity_bar)
        self.log_toggle = QToolButton()
        self.log_toggle.setText('Show technical details  ▾')
        self.log_toggle.setCheckable(True)
        self.log_toggle.setChecked(False)
        self.log_toggle.toggled.connect(self.toggle_log)
        activity_layout.addWidget(self.log_toggle)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(200)
        self.output.setMaximumHeight(104)
        self.output.hide()
        activity_layout.addWidget(self.output)
        self.activity.hide()
        self.layout_root.addWidget(self.activity)
        self.error_banner = QLabel('')
        self.error_banner.setObjectName('ErrorBanner')
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        self.layout_root.addWidget(self.error_banner)
        self.pages = QStackedWidget()
        # No wizard-level scroll container: pages are designed to fit the landscape window.
        self.layout_root.addWidget(self.pages, 1)
        self.layout_root.addStretch(0)
        self.SubmitButton = QPushButton('Continue')
        self.SubmitButton.setObjectName('PrimaryAction')
        self.SubmitButton.clicked.connect(self.continue_action)
        for number in range(1, 5):
            page = QWidget()
            page.setObjectName('Tab')
            setattr(self, 'tab' + str(number), page)
            self.pages.addWidget(page)
            getattr(self, 'tab' + str(number) + 'UI')()
        self.game = self.PathEntry
        if args.game_path:
            self.game.setText(str(args.game_path))
        self.steps = []
        self.active_step = -1
        self._last_ok = False
        footer = QHBoxLayout()
        footer.addWidget(QLabel(__version__ + ' by FOLON Team'))
        footer.addStretch()
        self.cancel = QPushButton('Cancel')
        self.cancel.setObjectName('SecondaryAction')
        self.cancel.clicked.connect(self.cancel_work)
        self.cancel.setEnabled(False)
        self.cancel.hide()  # Cancel is only relevant while a worker is active.
        footer.addWidget(self.cancel)
        footer.addWidget(self.SubmitButton)
        self.layout_root.addLayout(footer)
        self.controls = (self.SubmitButton, self.InstallButton, self.PathButton, self.FindButton, self.storage_button, self.storage_change, self.storage_default, self.storage_open,
                         self.game, self.UsernameEntry, self.PasswordEntry)
        resources = Path(Resources.resource_path('.'))
        style = (resources / 'FOLON.css').read_text(encoding='utf-8')
        style = style.replace('FOLON-Downgrader-Files/FOLONBackground.png', (resources / 'img/FOLONBackground.png').as_posix())
        style = style.replace('FOLON-Downgrader-Files/check.svg', (resources / 'img/check.svg').as_posix())
        self.setStyleSheet(style)
        # Keep exactly the same landscape height through every workflow state.
        # A modest increase over the prior 560px fits login validation and
        # authentication guidance without scroll areas or window jumps.
        self.setMinimumWidth(840)
        self.setFixedHeight(600)
        self.resize(980, 600)
        self.PathEntry.textChanged.connect(self.refresh_storage_status)
        self.refresh_storage_status()

    def set_activity_centered(self, centered):
        top = 1 if centered else 0
        bottom = 1 if centered else 0
        self.layout_root.setStretch(0, top)
        self.layout_root.setStretch(1, 0)
        self.layout_root.setStretch(2, 0)  # Error banner (normally hidden)
        self.layout_root.setStretch(3, 0)  # Wizard pages
        self.layout_root.setStretch(4, bottom)

    def continue_action(self):
        if self.pages.currentIndex() == 0:
            self.run('preflight')
        elif self.pages.currentIndex() == 1:
            self.SteamSubmit()
        elif self.pages.currentIndex() == 3:
            self.close()

    def SubmitPath(self):
        self.run('preflight')

    def GetDirectory(self):
        self.browse()

    def edit_text_changed1(self, text):
        self.SubmitButton.setEnabled(bool(text))

    def edit_text_changed2(self, text):
        self.SubmitButton.setEnabled(bool(self.UsernameEntry.text() and self.PasswordEntry.text()))

    def GoToPassword(self):
        self.PasswordEntry.setFocus()

    def ChangeHiddenPassword(self):
        self.PasswordEntry.setEchoMode(QLineEdit.Password if self.PasswordCheck.isChecked() else QLineEdit.Normal)

    def current_download_root(self):
        from .cli import effective_steamcmd_root
        return effective_steamcmd_root(self.args)

    def change_download_location(self):
        from .storage_settings import save_download_root
        if self.worker and self.worker.isRunning():
            return
        selected = QFileDialog.getExistingDirectory(
            self, 'Choose download storage folder', str(self.current_download_root().parent),
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog)
        if not selected:
            return
        new_root = Path(selected).absolute()
        old_root = self.current_download_root().absolute()
        if new_root == old_root:
            return
        # Prevent selecting installation or our internal state directories.
        from .platforms import data_root
        protected = [data_root() / 'staging', data_root() / 'transactions']
        if self.game.text().strip():
            protected.append(Path(self.game.text().strip()))
        if any(new_root.is_relative_to(p.absolute()) or p.absolute().is_relative_to(new_root)
               for p in protected):
            QMessageBox.warning(self, 'Invalid download folder',
                'Choose a separate folder outside the game installation and application state folders.')
            return
        if QMessageBox.question(self, 'Change download location?',
                f'Use this folder for future SteamCMD downloads?\n\n{new_root}\n\n'
                'Previously downloaded depots will stay in the old location. '
                'Select that folder again to reuse or remove them.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            save_download_root(new_root)
            self.args.steamcmd_root = new_root
        except OSError as error:
            QMessageBox.warning(self, 'Cannot save download location', str(error))
            return
        self.verified_cache.clear()
        self.refresh_storage_status()

    def restore_default_download_location(self):
        from .platforms import data_root
        from .storage_settings import save_download_root
        if self.worker and self.worker.isRunning():
            return
        default_root = data_root() / 'steamcmd'
        if self.current_download_root().absolute() == default_root.absolute():
            return
        if QMessageBox.question(
                self, 'Restore default download location?',
                f'Use the default depot download location?\n\n{default_root}\n\n'
                'Downloads in the previous location will stay there.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            save_download_root(default_root)
            self.args.steamcmd_root = default_root
        except OSError as error:
            QMessageBox.warning(self, 'Cannot restore download location', str(error))
            return
        self.verified_cache.clear()
        self.refresh_storage_status()

    def open_download_location(self):
        root = self.current_download_root()
        # Open the actual depot directory when it exists, otherwise the managed root.
        from .steamcmd import SteamCmdProvider
        folders = [p for p in SteamCmdProvider(root).candidate_roots() if p.is_dir()]
        target = folders[0] if folders else root
        if not target.is_dir():
            QMessageBox.information(self, 'Download folder',
                f'No download folder has been created yet.\n\nSelected location: {root}')
            return
        if sys.platform.startswith('linux'):
            from .folder_opener import open_linux_folder
            opened = open_linux_folder(target)
        else:
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        if not opened:
            QMessageBox.warning(self, 'Cannot open folder', f'Open the download folder manually:\n{target}')

    def _storage_request(self):
        from .cli import make_storage_request
        # Saved depots belong to the application, not a particular selected
        # game path. Discover them even before the user selects Fallout 4.
        self.args.game_path = Path(self.game.text().strip()) if self.game.text().strip() else None
        return make_storage_request(self.args)

    def refresh_storage_status(self, *_):
        from .cleanup import removable_downloads
        try:
            request = self._storage_request()
            usage = removable_downloads(request) if request else {'bytes': 0, 'files': 0}
        except (OSError, DowngradeError):
            usage = {'bytes': 0, 'files': 0}
        self.storage_path.setText(str(self.current_download_root()))
        from .platforms import data_root
        self.storage_default.setEnabled(
            self.current_download_root().absolute() != (data_root() / 'steamcmd').absolute()
            and not (self.worker and self.worker.isRunning()))
        self.storage_path.setToolTip(str(self.current_download_root()))
        count = usage['files']
        self.storage_button.setEnabled(bool(count) and not (self.worker and self.worker.isRunning()))
        if count:
            size = usage['bytes']
            for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
                if size < 1024 or unit == 'TiB':
                    break
                size /= 1024
            self.storage_status.setText(f'Saved Fallout 4 depots: {size:.1f} {unit} ({count} files)')
        else:
            self.storage_status.setText('No saved Fallout 4 depots available to remove.')

    def remove_saved_downloads(self):
        from .cleanup import removable_downloads
        try:
            request = self._storage_request()
            usage = removable_downloads(request) if request else {'bytes': 0, 'files': 0}
        except (OSError, DowngradeError) as error:
            self.error_banner.setText(f'Cannot check downloads: {error}')
            self.error_banner.show()
            return
        if not usage['files']:
            self.refresh_storage_status()
            return
        if QMessageBox.question(
            self, 'Remove downloaded depots?',
            'Remove the saved Fallout 4 depot files, including downloads from interrupted attempts?\n\n'
            'To downgrade again, you will need to download these depot files again.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self.run('cleanup-downloads')

    def SteamSubmit(self):
        self.run('setup-steamcmd')

    def OpenDepotsDialog(self):
        self.run('deploy')

    def OpenDiscord(self):
        from webbrowser import open as open_url
        open_url('https://discord.gg/GtmKaR8')

    def browse(self):
        # Use the bundled Qt chooser so its opaque, readable theme is consistent
        # even when an AppImage cannot access the desktop's native dialog plugin.
        path = QFileDialog.getExistingDirectory(
            self, 'Select Steam Fallout 4', self.game.text(),
            QFileDialog.ShowDirsOnly | QFileDialog.DontUseNativeDialog,
        )
        if path:
            self.game.setText(path)

    def find_games(self):
        from .platforms import discover
        try:
            paths = [str(p) for p in discover()]
            if not paths:
                self.output.appendPlainText('No Steam Fallout 4 installation found. Select its folder with Browse.')
                return
            path, ok = QInputDialog.getItem(self, 'Steam installations', 'Choose Fallout 4:', paths, 0, False)
            if ok:
                self.game.setText(path)
        except (OSError, DowngradeError):
            self.output.appendPlainText('Unable to discover Steam libraries. Select the folder with Browse.')

    def run(self, action):
        from .cli import make_request
        self.args.game_path = Path(self.game.text()) if self.game.text() else None
        try:
            request = make_request(self.args)
        except (OSError, DowngradeError) as error:
            self.output.appendPlainText(str(error) if isinstance(error, DowngradeError) else 'Cannot access the selected directory.')
            return
        close_steam = False
        if action == 'deploy':
            if QMessageBox.question(self, 'Confirm game changes', f'{action.title()}\nGame: {request.game}\nContinue?') != QMessageBox.Yes:
                return
        if action == 'deploy':
            from .platforms import steam_processes
            if steam_processes():
                if QMessageBox.question(self, 'Close Steam', 'Steam must close before changing game files. Close Steam now?') != QMessageBox.Yes:
                    return
                close_steam = True
        self.error_banner.hide()
        self.start_activity(action)
        self.worker = Worker(request, action, self.verified_cache, close_steam)
        self.worker.progress.connect(self.show_progress)
        self.worker.prompt.connect(self.prompt)
        self.worker.succeeded.connect(self.succeeded)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.reset)
        for control in self.controls:
            control.setEnabled(False)
        self.cancel.setEnabled(True)
        self.cancel.show()
        self.pages.hide()
        self.set_activity_centered(True)
        self.worker.start()

    def prompt(self, kind):
        # SteamCMD often asks for credentials already entered on the login page.
        # Pass those through without making the user hunt for a second dialog.
        if kind in ('username', 'password'):
            field = self.UsernameEntry if kind == 'username' else self.PasswordEntry
            if field.text():
                self.activity_detail.setText('Signing in to Steam…')
                self.worker.answers.put(field.text())
                field.clear()
                return
        descriptions = {
            'username': ('Steam username required', 'Enter your Steam account name to continue.', False),
            'password': ('Steam password required', 'Enter your Steam password to continue.', True),
            'steam_guard': ('Steam Guard code required', 'Enter the verification code from Steam to continue.', False),
        }
        title, description, secret = descriptions[kind]
        self.auth_kind = kind
        self.auth_hint_timer.stop()
        self.mobile_help.hide()
        self.auth_label.setText(title)
        self.activity_title.setText('Action required — Steam sign-in')
        self.activity_detail.setText(description)
        self.auth_entry.clear()
        self.auth_entry.setEchoMode(QLineEdit.Password if secret else QLineEdit.Normal)
        self.auth_entry.setPlaceholderText('Enter ' + ('verification code' if kind == 'steam_guard' else kind))
        self.auth_submit.setEnabled(False)
        self.auth_panel.show()
        self.auth_entry.setFocus()

    def submit_auth(self):
        if not self.auth_kind or not self.auth_entry.text().strip() or not self.worker:
            return
        answer = self.auth_entry.text()
        self.auth_entry.clear()
        self.auth_panel.hide()
        self.auth_hint_timer.stop()
        self.mobile_help.hide()
        self.auth_kind = None
        self.activity_title.setText('Downgrader is working')
        self.activity_detail.setText('Signing in to Steam…')
        self.auth_hint_timer.start()
        self.worker.answers.put(answer)
        answer = ''

    def toggle_log(self, expanded):
        self.output.setVisible(expanded)
        self.log_toggle.setText('Hide technical details  ▴' if expanded else 'Show technical details  ▾')

    def start_activity(self, action):
        self.steps = ACTION_STEPS.get(action, [('preflight', 'Working')])
        self.active_step = -1
        while self.step_row.count():
            item = self.step_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.step_labels = []
        for _stage, name in self.steps:
            label = QLabel('○  ' + name)
            label.setObjectName('ActivityStep')
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignCenter)
            self.step_labels.append(label)
            self.step_row.addWidget(label, 1)
        self.auth_panel.hide()
        self.mobile_help.hide()
        self.auth_kind = None
        self.activity_title.setText('Downgrader is working')
        self.activity_detail.setText('Starting…')
        self.activity_bar.setRange(0, 0)
        self.activity.show()
        self.log_toggle.setChecked(False)
        self.render_steps()

    def render_steps(self):
        for i, label in enumerate(self.step_labels):
            if i < self.active_step:
                label.setText('✓  ' + self.steps[i][1])
                label.setProperty('stepState', 'done')
            elif i == self.active_step:
                label.setText('●  ' + self.steps[i][1])
                label.setProperty('stepState', 'active')
            else:
                label.setText('○  ' + self.steps[i][1])
                label.setProperty('stepState', 'pending')
            label.style().unpolish(label)
            label.style().polish(label)

    def show_delayed_auth_hint(self):
        # Only show guidance while this worker is still awaiting Steam login.
        if self.auth_kind is None and self.activity.isVisible() and self.worker and self.worker.isRunning():
            self.mobile_help.show()
            self.activity_title.setText('Steam sign-in — check your phone')
            self.activity_detail.setText('Still waiting for Steam authentication. Check your Steam mobile app for an approval request.')

    def show_progress(self, event):
        stage = event.get('stage', 'working')
        message = event.get('message') or stage.replace('_', ' ').capitalize()
        if not event.get('error_code') and not self.auth_kind:
            if stage == 'authenticate':
                if event.get('auth_state') == 'mobile':
                    # SteamCMD explicitly requested approval; no need to wait.
                    self.auth_hint_timer.stop()
                    self.mobile_help.show()
                    self.activity_title.setText('Steam sign-in — check your phone')
                    self.activity_detail.setText(message)
                else:
                    self.mobile_help.hide()
                    self.activity_title.setText('Downgrader is working')
                    self.activity_detail.setText('Signing in to Steam…')
                    if not self.auth_hint_timer.isActive():
                        self.auth_hint_timer.start()
            else:
                self.auth_hint_timer.stop()
                self.mobile_help.hide()
                self.activity_title.setText('Downgrader is working')
                self.activity_detail.setText(message)
            canonical = STAGE_ALIASES.get(stage, stage)
            for i, (key, _) in enumerate(self.steps):
                if canonical == key and i >= self.active_step:
                    self.active_step = i
                    break
            self.render_steps()
        self.output.appendPlainText(message)

    def finish_activity(self, ok, message):
        self.auth_hint_timer.stop()
        self.mobile_help.hide()
        self.auth_panel.hide()
        self.auth_kind = None
        self.activity_title.setText('Completed successfully' if ok else 'Action stopped')
        self.activity_detail.setText(message)
        self.activity_bar.setRange(0, 1)
        self.activity_bar.setValue(1 if ok else 0)
        if ok:
            self.active_step = len(self.steps)
            self.render_steps()
        else:
            self.log_toggle.setChecked(True)

    def succeeded(self, result):
        self._last_ok = True
        self.finish_activity(True, 'This action completed successfully.')
        action = self.worker.action
        if action == 'preflight':
            if self.args.content_root or result.get('downloads_available'):
                self._next_action = 'verify-download'
            else:
                self.pages.setCurrentIndex(1)
        elif action == 'setup-steamcmd':
            self._next_action = 'download'
        elif action in ('download', 'verify-download'):
            self.pages.setCurrentIndex(2)
        elif action == 'deploy':
            self.pages.setCurrentIndex(3)
            self._offer_cleanup = True
        elif action == 'cleanup-downloads':
            self.output.appendPlainText('Downloaded files removed. Fallout 4 is ready.')
            self.pages.setCurrentIndex(0)

    def failed(self, result):
        self._last_ok = False
        self.finish_activity(False, result.get('message', 'The operation could not finish.'))
        action = self.worker.action if self.worker else None
        code = result.get('error_code', 'UNKNOWN_ERROR')
        message = result.get('message', 'The operation could not finish.')
        self.output.appendPlainText(f'{code}: {message}')
        # Always return to a usable wizard page after an interrupted operation.
        # In particular, SteamCMD login failures must not leave the progress
        # panel stacked above the login form.
        if action in ('setup-steamcmd', 'download') or code in ('AUTH_FAILED', 'STEAM_AUTH_FAILED'):
            target = 1
            self.PasswordEntry.clear()
            guidance = 'Check your Steam credentials or approve the sign-in in the Steam app, then try again.'
        elif action == 'verify-download' and not self.args.content_root:
            target = 1
            guidance = 'Sign in to Steam again to download missing or damaged files.'
        elif action == 'deploy':
            target = 2
            guidance = 'Review the error and retry the downgrade only after the underlying issue is resolved.'
        elif action == 'cleanup-downloads':
            target = 0
            guidance = 'The downgrade succeeded, but cleanup was interrupted. Your installed game is not removed.'
        else:
            target = 0
            guidance = 'Review the selected game directory and try again.'
        self.pages.setCurrentIndex(target)
        self.error_banner.setText(f'Action stopped: {message}\n{guidance}')
        self.error_banner.show()
        self._next_action = None
        self._offer_cleanup = False

    def reset(self):
        completed_action = self.worker.action if self.worker else None
        for control in self.controls:
            control.setEnabled(True)
        self.cancel.setEnabled(False)
        self.cancel.hide()
        self.pages.show()
        self.set_activity_centered(False)
        # The progress view belongs only to an active worker. Errors are shown
        # as a compact banner above the restored wizard page instead.
        self.activity.hide()
        self.log_toggle.setChecked(False)
        self.refresh_storage_status()
        index = self.pages.currentIndex()
        self.SubmitButton.setText(['Continue', 'Login to Steam', 'Continue', 'Finish'][index])
        self.SubmitButton.setVisible(index != 2)
        if index == 1:
            self.SubmitButton.setEnabled(bool(self.UsernameEntry.text() and self.PasswordEntry.text()))
        if getattr(self, '_offer_cleanup', False):
            self._offer_cleanup = False
            answer = QMessageBox.question(
                self, 'Remove downloaded files?',
                'Fallout 4 was downgraded and verified successfully.\n\n'
                'Remove the downloaded game files to free disk space? '
                'You would need to download them again for another downgrade.\n\n'
                'Your installed game will not be removed.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                self.run('cleanup-downloads')
            return
        if getattr(self, '_next_action', None):
            action = self._next_action
            self._next_action = None
            self.run(action)

    def cancel_work(self):
        if self.worker:
            self.worker.engine.cancelled.set()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel_work()
            self.output.appendPlainText('Cancelling; wait for the current safe write boundary, then close again.')
            event.ignore()
        else:
            event.accept()


def launch(args):
    app = QApplication(sys.argv[:1])
    window = Window(args)
    window.show()
    return app.exec()
