"""Shared FOLON wizard for Windows and Linux. UI never owns deployment state."""
import json
from pathlib import Path
import queue
import sys

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QApplication, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QPlainTextEdit, QProgressBar,
    QStackedWidget, QVBoxLayout, QWidget)

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
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        self.progress.setRange(0, 4)
        self.progress.setValue(1)
        self.progress.setFormat('Locate Fallout 4')
        layout.addWidget(self.progress)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)
        self.SubmitButton = QPushButton('Continue')
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
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(200)
        self.output.setMaximumHeight(140)
        self.output.hide()
        layout.addWidget(self.output)
        footer = QHBoxLayout()
        footer.addWidget(QLabel(__version__ + ' by FOLON Team'))
        footer.addStretch()
        self.cancel = QPushButton('Cancel')
        self.cancel.clicked.connect(self.cancel_work)
        self.cancel.setEnabled(False)
        footer.addWidget(self.cancel)
        footer.addWidget(self.SubmitButton)
        layout.addLayout(footer)
        self.controls = (self.SubmitButton, self.InstallButton, self.PathButton,
                         self.game, self.UsernameEntry, self.PasswordEntry)
        resources = Path(Resources.resource_path('.'))
        style = (resources / 'FOLON.css').read_text(encoding='utf-8')
        style = style.replace('FOLON-Downgrader-Files/FOLONBackground.png', (resources / 'img/FOLONBackground.png').as_posix())
        style = style.replace('FOLON-Downgrader-Files/check.svg', (resources / 'img/check.svg').as_posix())
        self.setStyleSheet(style)
        self.resize(850, 440)

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
        self.worker = Worker(request, action, self.verified_cache, close_steam)
        self.worker.progress.connect(self.show_progress)
        self.worker.prompt.connect(self.prompt)
        self.worker.succeeded.connect(self.succeeded)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.reset)
        for control in self.controls:
            control.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setRange(0, 0)
        self.worker.start()

    def prompt(self, kind):
        labels = {'username': 'Steam account name', 'password': 'Steam password', 'steam_guard': 'Steam Guard code'}
        if kind in ('username', 'password'):
            field = self.UsernameEntry if kind == 'username' else self.PasswordEntry
            if field.text():
                self.worker.answers.put(field.text())
                field.clear()
                return
        answer, ok = QInputDialog.getText(self, 'Steam authentication', labels[kind],
                        QLineEdit.Normal if kind == 'username' else QLineEdit.Password)
        self.worker.answers.put(answer if ok else None)
        answer = ''

    def show_progress(self, event):
        text = event.get('message', event['stage'].replace('_', ' ').capitalize())
        self.progress.setFormat(text)
        self.output.show()
        self.output.appendPlainText(text)

    def succeeded(self, result):
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

    def failed(self, result):
        self.output.show()
        self.PasswordEntry.clear()
        self.output.appendPlainText(result['error_code'] + ': ' + result['message'])
        if self.worker and self.worker.action == 'verify-download' and not self.args.content_root:
            self.pages.setCurrentIndex(1)
            self.output.appendPlainText('Sign in to Steam to download missing or damaged files.')
        if result.get('retry_required'):
            self.output.appendPlainText('Retry the downgrade, or restore the game using Steam.')

    def reset(self):
        for control in self.controls:
            control.setEnabled(True)
        self.cancel.setEnabled(False)
        self.progress.setRange(0, 4)
        self.progress.setValue(self.pages.currentIndex() + 1)
        index = self.pages.currentIndex()
        self.progress.setFormat(['Locate Fallout 4', 'Login to Steam / download', 'Downgrade Fallout 4', 'Verified'][index])
        self.SubmitButton.setText(['Continue', 'Login to Steam', 'Continue', 'Finish'][index])
        self.SubmitButton.setVisible(index != 2)
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
