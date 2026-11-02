"""Original FOLON page layouts, separated from the platform-specific backend.

Derived from WindowsDowngrader.py at c53629d (repository MIT license).
"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QFont, QPixmap
from QLines import QHSeparationLine
from pathlib import Path
import sys


class Resources:
    @staticmethod
    def resource_path(name):
        return str(Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / name)

    @staticmethod
    def Read_Settings():
        return {'SteamPath': ''}


Util = Resources


class FolonPages:
    def _title_label(self, text):
        label = QLabel(text)
        label.setObjectName('PageTitle')
        label.setWordWrap(True)
        label.setFont(QFont('Overseer', 26))
        return label

    def _lead_label(self, text):
        label = QLabel(text)
        label.setObjectName('PageLead')
        label.setWordWrap(True)
        return label

    def _hint_label(self, text):
        label = QLabel(text)
        label.setObjectName('HintText')
        label.setWordWrap(True)
        return label

    def _card(self):
        card = QWidget()
        card.setObjectName('ContentCard')
        return card

    def tab1UI(self):
        settings = Util.Read_Settings()
        page_layout = QVBoxLayout()
        page_layout.setSpacing(10)

        page_layout.addWidget(self._title_label('Select your Fallout 4 folder'))
        page_layout.addWidget(self._lead_label(
            'Choose the Steam installation folder for Fallout 4. This should be the folder that contains Fallout4.exe.'
        ))

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        card_layout.addWidget(self._hint_label('Game folder'))

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.PathEntry = QLineEdit()
        self.PathEntry.returnPressed.connect(self.SubmitPath)
        self.PathEntry.setObjectName('InsideTextBox')
        self.PathEntry.setPlaceholderText('Select the folder containing Fallout4.exe')
        self.PathEntry.setMinimumHeight(max(40, self.PathEntry.fontMetrics().height() + 20))
        if settings['SteamPath'] != '':
            self.PathEntry.setText(settings['SteamPath'])
            self.SubmitButton.setEnabled(True)
        else:
            self.SubmitButton.setEnabled(False)
        self.PathEntry.textChanged.connect(self.edit_text_changed1)

        self.PathButton = QPushButton('Browse')
        self.PathButton.setIcon(QIcon(Util.resource_path('img/folder.svg')))
        self.PathButton.setObjectName('SecondaryAction')
        self.PathButton.pressed.connect(self.GetDirectory)

        self.FindButton = QPushButton('Auto-detect')
        self.FindButton.setObjectName('SecondaryAction')
        self.FindButton.pressed.connect(self.find_games)

        input_row.addWidget(self.PathEntry, 1)
        input_row.addWidget(self.PathButton)
        input_row.addWidget(self.FindButton)
        card_layout.addLayout(input_row)
        card_layout.addWidget(self._hint_label('Tip: if you use Steam, auto-detect will try to find the correct installation automatically.'))

        page_layout.addWidget(card)

        storage_card = self._card()
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setSpacing(5)
        storage_layout.addWidget(self._hint_label('Download storage'))
        # Match the game-folder selector: a path field followed by two actions.
        # It is read-only because changing the SteamCMD root needs validation
        # and confirmation before the new path is saved.
        storage_path_row = QHBoxLayout()
        storage_path_row.setSpacing(8)
        self.storage_path = QLineEdit()
        self.storage_path.setObjectName('InsideTextBox')
        self.storage_path.setReadOnly(True)
        self.storage_path.setPlaceholderText('Depot download location')
        self.storage_path.setMinimumHeight(max(40, self.storage_path.fontMetrics().height() + 20))
        storage_path_row.addWidget(self.storage_path, 1)
        self.storage_change = QPushButton('Change path')
        self.storage_change.setObjectName('SecondaryAction')
        self.storage_change.clicked.connect(self.change_download_location)
        storage_path_row.addWidget(self.storage_change)
        self.storage_default = QPushButton('Restore default')
        self.storage_default.setObjectName('SecondaryAction')
        self.storage_default.clicked.connect(self.restore_default_download_location)
        storage_path_row.addWidget(self.storage_default)
        storage_layout.addLayout(storage_path_row)

        # Management actions are kept in their own row below the location.
        management_row = QHBoxLayout()
        management_row.setSpacing(8)
        self.storage_status = self._hint_label('Checking saved Fallout 4 depots…')
        self.storage_status.setObjectName('StorageStatus')
        self.storage_status.setWordWrap(True)
        management_row.addWidget(self.storage_status, 1)
        self.storage_open = QPushButton('Open depot folder')
        self.storage_open.setObjectName('SecondaryAction')
        self.storage_open.clicked.connect(self.open_download_location)
        management_row.addWidget(self.storage_open)
        self.storage_button = QPushButton('Remove depots')
        self.storage_button.setObjectName('SecondaryAction')
        self.storage_button.setEnabled(False)
        self.storage_button.clicked.connect(self.remove_saved_downloads)
        management_row.addWidget(self.storage_button)
        storage_layout.addLayout(management_row)
        page_layout.addWidget(storage_card)
        page_layout.addStretch(1)
        self.tab1.setLayout(page_layout)

    def tab2UI(self):
        self.FinishedLogging = False
        self.SteamGuardCode = ''

        page_layout = QVBoxLayout()
        page_layout.setSpacing(10)
        page_layout.addWidget(self._title_label('Sign in to Steam'))
        page_layout.addWidget(self._lead_label(
            'The downgrader needs Steam access to download the required depot files. Your credentials are only passed to SteamCMD and are not stored by this app.'
        ))

        card = self._card()
        form = QFormLayout(card)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)

        self.UsernameEntry = QLineEdit()
        self.UsernameEntry.returnPressed.connect(self.GoToPassword)
        self.UsernameEntry.textChanged.connect(self.edit_text_changed2)
        self.UsernameEntry.setPlaceholderText('Steam username')
        self.UsernameEntry.setMinimumHeight(max(40, self.UsernameEntry.fontMetrics().height() + 20))

        self.PasswordEntry = QLineEdit()
        self.PasswordEntry.setEchoMode(QLineEdit.EchoMode.Password)
        self.PasswordEntry.returnPressed.connect(self.SteamSubmit)
        self.PasswordEntry.textChanged.connect(self.edit_text_changed2)
        self.PasswordEntry.setPlaceholderText('Steam password')
        self.PasswordEntry.setMinimumHeight(max(40, self.PasswordEntry.fontMetrics().height() + 20))

        self.PasswordCheck = QCheckBox('Hide password')
        self.PasswordCheck.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.PasswordCheck.setChecked(True)
        self.PasswordCheck.stateChanged.connect(self.ChangeHiddenPassword)

        options = QWidget()
        options_row = QHBoxLayout(options)
        options_row.setContentsMargins(0, 0, 0, 0)
        options_row.setSpacing(18)
        options_row.addWidget(self.PasswordCheck)
        options_row.addStretch(1)

        form.addRow('Username', self.UsernameEntry)
        form.addRow('Password', self.PasswordEntry)
        form.addRow('', options)

        page_layout.addWidget(card)
        page_layout.addWidget(self._hint_label(
            'Steam Guard: if verification is required, enter the code when prompted or approve the sign-in in your Steam mobile app.'
        ))

        info = self._card()
        info_layout = QHBoxLayout(info)
        info_layout.setSpacing(10)
        alert_icon = QLabel()
        alert_icon.setPixmap(QPixmap(Util.resource_path('img/alert.svg')))
        info_layout.addWidget(alert_icon, 0, Qt.AlignTop)
        manual = QLabel(
            "<a style='color:#d8c1fa' href='https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/Manually.md'>Prefer a manual route? Read the manual downgrade guide.</a>"
        )
        manual.setOpenExternalLinks(True)
        manual.setWordWrap(True)
        info_layout.addWidget(manual, 1)
        page_layout.addWidget(info)
        page_layout.addStretch(1)

        self.tab2.setLayout(page_layout)

    def tab3UI(self):
        self.Downloaded = 0
        self.DownloadFailed = False
        page_layout = QVBoxLayout()
        page_layout.setSpacing(10)

        page_layout.addWidget(self._title_label('Ready to downgrade Fallout 4'))
        page_layout.addWidget(self._lead_label(
            'When you continue, the downgrader will apply the prepared files to your Fallout 4 installation and verify the result.'
        ))

        card = self._card()
        card_layout = QVBoxLayout(card)
        summary = QLabel(
            '<ul>'
            '<li>Prepare the target files</li>'
            '<li>Install the downgrade</li>'
            '<li>Verify the game files</li>'
            '</ul>'
        )
        summary.setWordWrap(True)
        card_layout.addWidget(summary)
        card_layout.addWidget(self._hint_label('This can take several minutes. Keep the window open until the process finishes.'))
        page_layout.addWidget(card)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.InstallButton = QPushButton('Start downgrade')
        self.InstallButton.setObjectName('InstallButton')
        self.InstallButton.setMinimumWidth(240)
        self.InstallButton.pressed.connect(self.OpenDepotsDialog)
        button_row.addWidget(self.InstallButton)
        button_row.addStretch(1)
        page_layout.addLayout(button_row)
        page_layout.addStretch(1)

        self.tab3.setLayout(page_layout)

    def tab4UI(self):
        page_layout = QVBoxLayout()
        page_layout.setSpacing(10)

        page_layout.addWidget(self._title_label('Downgrade complete'))
        page_layout.addWidget(self._lead_label(
            'Fallout 4 has been downgraded successfully. You can now close the downgrader or visit the community if you want help, updates, or troubleshooting.'
        ))

        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        card_layout.addWidget(self._hint_label('Next steps'))
        next_steps = QLabel(
            '<ul>'
            '<li>Launch the game normally or continue with your Fallout London setup.</li>'
            '<li>If you kept the downloaded depots, you can reuse them later.</li>'
            '<li>If you run into problems, open the technical details or ask the community.</li>'
            '</ul>'
        )
        next_steps.setWordWrap(True)
        card_layout.addWidget(next_steps)
        page_layout.addWidget(card)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.DiscordButton = QPushButton('Open Discord community')
        self.DiscordButton.setObjectName('SecondaryAction')
        self.DiscordButton.setIcon(QIcon(Util.resource_path('img/FOLON256.png')))
        self.DiscordButton.setIconSize(QSize(20, 20))
        self.DiscordButton.pressed.connect(self.OpenDiscord)
        action_row.addWidget(self.DiscordButton)
        action_row.addStretch(1)
        page_layout.addLayout(action_row)
        page_layout.addStretch(1)

        self.tab4.setLayout(page_layout)
