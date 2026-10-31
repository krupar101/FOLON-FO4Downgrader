"""Original FOLON page layouts, separated from the platform-specific backend.

Derived from WindowsDowngrader.py at c53629d (repository MIT license).
"""
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QSize
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
    def tab1UI(self):  # GUI
        Settings = Util.Read_Settings()
        layout = QFormLayout()

        Header = QLabel("Please select your Fallout 4 folder.")
        Header.setFont(QFont("Overseer", 30))
        layout.addRow(Header)
        layout.addRow(
            QLabel(
                "<p>To downgrade Fallout 4 we need its Steam installation folder.</p>"
            )
        )
        layout.addRow(
            QLabel(
                "<p>The folder <b>should</b> be the one containing a Fallout4.exe file.</p>"
            )
        )

        hbox = QHBoxLayout()
        hboxwidget = QWidget()

        self.PathEntry = QLineEdit()
        self.PathEntry.returnPressed.connect(self.SubmitPath)
        self.PathEntry.setObjectName("InsideTextBox")
        if Settings["SteamPath"] != "":
            self.PathEntry.setText(Settings["SteamPath"])
            self.SubmitButton.setEnabled(True)
        else:
            self.SubmitButton.setEnabled(False)
        self.PathEntry.textChanged.connect(self.edit_text_changed1)

        self.PathButton = QPushButton()
        self.PathButton.setIcon(QIcon(Util.resource_path("img/folder.svg")))
        self.PathButton.setObjectName("PathButton")
        self.PathButton.pressed.connect(self.GetDirectory)

        hbox.addWidget(self.PathEntry)
        hbox.addWidget(self.PathButton)
        hboxwidget.setObjectName("TextBox")
        hboxwidget.setLayout(hbox)

        layout.addRow(QLabel("Fallout 4 Path:"), hboxwidget)

        self.tab1.setLayout(layout)

    def tab2UI(self):  # GUI
        self.FinishedLogging = False
        self.SteamGuardCode = ""

        layout = QFormLayout()

        Header = QLabel("Please log into Steam before downgrading Fallout 4.")
        Header.setFont(QFont("Overseer", 30))
        layout.addRow(Header)
        layout.addRow(
            QLabel(
                "<p>To downgrade Fallout 4 we will need to download files via Steam, please login to do so.</p>"
            )
        )
        layout.addRow(
            QLabel("<p>Your password is sent directly to SteamCMD and is not saved by this app.</p>")
        )

        self.UsernameEntry = QLineEdit()
        self.UsernameEntry.returnPressed.connect(self.GoToPassword)
        self.UsernameEntry.textChanged.connect(self.edit_text_changed2)
        self.UsernameEntry.setObjectName("TextBox")

        self.PasswordEntry = QLineEdit()
        self.PasswordEntry.setEchoMode(QLineEdit.EchoMode.Password)
        self.PasswordEntry.returnPressed.connect(self.SteamSubmit)
        self.PasswordEntry.textChanged.connect(self.edit_text_changed2)
        self.PasswordEntry.setObjectName("TextBox")

        self.PasswordCheck = QCheckBox()
        self.PasswordCheck.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.PasswordCheck.setChecked(True)
        self.PasswordCheck.stateChanged.connect(self.ChangeHiddenPassword)

        CheckBoxes = QWidget()
        CheckLayout = QHBoxLayout()

        CheckLayout.addWidget(QLabel("Password hidden:"))
        CheckLayout.addWidget(self.PasswordCheck)

        self.SteamGuardCheck = QCheckBox()
        self.SteamGuardCheck.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.SteamGuardCheck.setChecked(True)

        CheckLayout.addWidget(QLabel("<p>Using <b>mobile</b> Steam Guard:</p>"))
        CheckLayout.addWidget(self.SteamGuardCheck)

        CheckLayout.addStretch()

        CheckBoxes.setLayout(CheckLayout)

        layout.addRow("Username:", self.UsernameEntry)
        layout.addRow("Password:", self.PasswordEntry)
        layout.addRow(CheckBoxes)

        Box = QHBoxLayout()

        AlertIcon = QLabel()
        AlertIcon.setPixmap(QPixmap(Util.resource_path("img/alert.svg")))

        AlertLabel = QLabel(
            "<a style='color:White' href='https://github.com/Fallout-London/FOLON-FO4Downgrader/blob/main/Manually.md'>You can also do this process manually if you'd like.</a>"
        )
        AlertLabel.setOpenExternalLinks(True)

        Box.addWidget(AlertIcon)
        Box.addWidget(AlertLabel)
        Box.addStretch()

        layout.addRow(Box)

        self.tab2.setLayout(layout)

    def tab3UI(self):  # GUI
        self.Downloaded = 0
        self.DownloadFailed = False
        layout = QFormLayout()
        layout.addRow(
            QLabel(
                "<p>The following button can take quite a while, please <b>be patient</b>.</p>"
            )
        )

        self.InstallButton = QPushButton(
            text="Downgrade Fallout 4 \n(This will take a long time)"
        )
        self.InstallButton.setObjectName("InstallButton")
        self.InstallButton.setFont(QFont("Overseer", 25))
        self.InstallButton.pressed.connect(self.OpenDepotsDialog)
        layout.addRow(self.InstallButton)

        self.tab3.setLayout(layout)

    def tab4UI(self):  # GUI
        layout = QGridLayout()

        TextLayout = QVBoxLayout()
        Header = QLabel("Done Downgrading")
        Header.setFont(QFont("Overseer", 30))
        TextLayout.addWidget(Header)
        TextLayout.addWidget(
            QLabel("<p>Thanks for using the Downgrader,</p>"),
        )
        TextLayout.addWidget(
            QLabel("<p>if you found any issues or just wanna chat.</p>")
        )
        TextLayout.addWidget(
            QLabel("<p>Join the Discord server!</p>"),
        )
        layout.addLayout(TextLayout, 0, 0)

        icon = QIcon(Util.resource_path("img/FOLON256.png"))
        self.DiscordButton = QPushButton()
        self.DiscordButton.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.DiscordButton.setIcon(icon)
        self.DiscordButton.setIconSize(QSize(200, 200))

        self.DiscordButton.pressed.connect(self.OpenDiscord)

        layout.addWidget(self.DiscordButton, 0, 1, 1, 1)

        separator_horizontal = QHSeparationLine()
        layout.addWidget(separator_horizontal, 1, 0, 1, 2)

        self.tab4.setLayout(layout)
