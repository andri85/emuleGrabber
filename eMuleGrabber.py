import sys
import os
import re
import json
import time
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QUrl, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMessageBox,
    QLabel,
    QProgressBar,
    QLineEdit,
    QCheckBox,
    QGroupBox,
    QSpinBox,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


APP_NAME = "eMule eD2K Manager"
VERSION = "1.2"

ED2K_RE = re.compile(
    r"ed2k://\|file\|[^|\r\n]+"
    r"\|\d+\|[0-9a-fA-F]{32}"
    r"\|[^\s<>'\"]*",
    re.IGNORECASE,
)


# ============================================================
# eD2K
# ============================================================

def extract_ed2k(text):
    """Estrae i link ed2k:// da un testo."""

    if not text:
        return []

    links = ED2K_RE.findall(text)

    result = []
    seen = set()

    for link in links:

        link = link.strip()
        link = link.rstrip(".,;)'\"")

        key = link.lower()

        if key not in seen:

            seen.add(key)
            result.append(link)

    return result


def filename_from_link(link):
    """Estrae il nome del file dal link eD2K."""

    try:

        parts = link.split("|")

        if len(parts) >= 3:
            return parts[2]

    except Exception:
        pass

    return link


def send_ed2k(link):
    """
    Apre il link ed2k:// tramite il programma
    associato al protocollo dal sistema operativo.
    """

    try:

        if sys.platform.startswith("win"):

            os.startfile(link)
            return True

        if sys.platform == "darwin":

            subprocess.Popen(
                ["open", link],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            return True

        subprocess.Popen(
            ["xdg-open", link],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return True

    except Exception:

        return False


# ============================================================
# THREAD INVIO
# ============================================================

class SenderThread(QThread):

    progress = Signal(int, int)
    status = Signal(str)
    completed = Signal(int, int, bool)

    def __init__(self, links, delay):

        super().__init__()

        self.links = links
        self.delay = delay
        self.stop_requested = False

    def stop(self):

        self.stop_requested = True

    def run(self):

        sent = 0
        failed = 0
        stopped = False

        total = len(self.links)

        for index, link in enumerate(
            self.links,
            start=1
        ):

            if self.stop_requested:

                stopped = True
                break

            filename = filename_from_link(
                link
            )

            self.status.emit(
                f"Invio {index}/{total}: {filename}"
            )

            try:

                if send_ed2k(link):
                    sent += 1
                else:
                    failed += 1

            except Exception:

                failed += 1

            self.progress.emit(
                index,
                total
            )

            elapsed = 0.0

            while elapsed < self.delay:

                if self.stop_requested:

                    stopped = True
                    break

                time.sleep(0.1)
                elapsed += 0.1

            if stopped:
                break

        self.completed.emit(
            sent,
            failed,
            stopped
        )


# ============================================================
# FINESTRA PRINCIPALE
# ============================================================

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            f"{APP_NAME} {VERSION}"
        )

        self.resize(
            1400,
            900
        )

        self.sender_thread = None

        self.settings_file = (
            Path.home()
            / ".emule_ed2k_manager.json"
        )

        self.clipboard_monitor_enabled = False
        self.last_clipboard = ""

        self.build_ui()
        self.setup_browser()
        self.setup_clipboard()

        self.load_settings()

    # ========================================================
    # INTERFACCIA
    # ========================================================

    def build_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        main_layout = QVBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            8,
            8,
            8,
            8
        )

        main_layout.setSpacing(
            5
        )

        # ====================================================
        # HEADER
        # ====================================================

        header = QHBoxLayout()

        title = QLabel(
            f"🦌 {APP_NAME} {VERSION}"
        )

        title.setStyleSheet(
            """
            QLabel {
                font-size: 21px;
                font-weight: bold;
            }
            """
        )

        header.addWidget(
            title
        )

        header.addStretch()

        self.link_counter = QLabel(
            "Link: 0"
        )

        self.link_counter.setStyleSheet(
            """
            QLabel {
                font-size: 15px;
                font-weight: bold;
            }
            """
        )

        header.addWidget(
            self.link_counter
        )

        main_layout.addLayout(
            header
        )

        # ====================================================
        # BROWSER
        # ====================================================

        browser_group = QGroupBox(
            "🌐 Browser eD2K"
        )

        browser_layout = QVBoxLayout(
            browser_group
        )

        browser_layout.setContentsMargins(
            5,
            5,
            5,
            5
        )

        browser_layout.setSpacing(
            4
        )

        # ----------------------------------------------------
        # NAVIGAZIONE
        # ----------------------------------------------------

        navigation = QHBoxLayout()

        self.back_button = QPushButton(
            "◀"
        )

        self.forward_button = QPushButton(
            "▶"
        )

        self.reload_button = QPushButton(
            "⟳"
        )

        self.home_button = QPushButton(
            "⌂"
        )

        for button in (
            self.back_button,
            self.forward_button,
            self.reload_button,
            self.home_button,
        ):

            button.setFixedSize(
                38,
                30
            )

        self.url_edit = QLineEdit()

        self.url_edit.setPlaceholderText(
            "Inserisci URL del sito..."
        )

        self.go_button = QPushButton(
            "Vai"
        )

        self.go_button.setFixedWidth(
            55
        )

        navigation.addWidget(
            self.back_button
        )

        navigation.addWidget(
            self.forward_button
        )

        navigation.addWidget(
            self.reload_button
        )

        navigation.addWidget(
            self.home_button
        )

        navigation.addWidget(
            self.url_edit,
            1
        )

        navigation.addWidget(
            self.go_button
        )

        browser_layout.addLayout(
            navigation
        )

        # ----------------------------------------------------
        # WEBVIEW GRANDE
        # ----------------------------------------------------

        self.webview = QWebEngineView()

        self.webview.setMinimumHeight(
            480
        )

        browser_layout.addWidget(
            self.webview,
            1
        )

        # ----------------------------------------------------
        # CONTROLLI BROWSER
        # ----------------------------------------------------

        browser_controls = QHBoxLayout()

        self.scan_checkbox = QCheckBox(
            "🔎 Intercetta automaticamente ed2k://"
        )

        self.scan_checkbox.setChecked(
            True
        )

        self.scan_button = QPushButton(
            "🔍 Scansiona pagina"
        )

        self.clear_browser_button = QPushButton(
            "🧹 Pulisci lista"
        )

        browser_controls.addWidget(
            self.scan_checkbox
        )

        browser_controls.addWidget(
            self.scan_button
        )

        browser_controls.addWidget(
            self.clear_browser_button
        )

        browser_controls.addStretch()

        browser_layout.addLayout(
            browser_controls
        )

        main_layout.addWidget(
            browser_group,
            7
        )

        # ====================================================
        # LISTA ED2K
        # ====================================================

        list_group = QGroupBox(
            "📋 Link eD2K intercettati"
        )

        list_layout = QVBoxLayout(
            list_group
        )

        list_layout.setContentsMargins(
            5,
            5,
            5,
            5
        )

        list_layout.setSpacing(
            3
        )

        self.list_widget = QListWidget()

        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )

        self.list_widget.setMinimumHeight(
            90
        )

        self.list_widget.setMaximumHeight(
            150
        )

        list_layout.addWidget(
            self.list_widget
        )

        list_buttons = QHBoxLayout()

        self.paste_button = QPushButton(
            "📋 Incolla"
        )

        self.import_button = QPushButton(
            "📂 Importa"
        )

        self.remove_button = QPushButton(
            "🗑 Rimuovi"
        )

        self.clear_button = QPushButton(
            "✕ Svuota"
        )

        list_buttons.addWidget(
            self.paste_button
        )

        list_buttons.addWidget(
            self.import_button
        )

        list_buttons.addWidget(
            self.remove_button
        )

        list_buttons.addWidget(
            self.clear_button
        )

        list_buttons.addStretch()

        list_layout.addLayout(
            list_buttons
        )

        main_layout.addWidget(
            list_group
        )

        # ====================================================
        # OPZIONI
        # ====================================================

        options_group = QGroupBox(
            "⚙ Opzioni"
        )

        options_layout = QHBoxLayout(
            options_group
        )

        options_layout.setContentsMargins(
            5,
            3,
            5,
            3
        )

        options_layout.addWidget(
            QLabel(
                "Ritardo:"
            )
        )

        self.delay_spin = QSpinBox()

        self.delay_spin.setRange(
            0,
            3600
        )

        self.delay_spin.setValue(
            1
        )

        self.delay_spin.setSuffix(
            " sec"
        )

        options_layout.addWidget(
            self.delay_spin
        )

        self.dedupe_checkbox = QCheckBox(
            "Evita duplicati"
        )

        self.dedupe_checkbox.setChecked(
            True
        )

        options_layout.addWidget(
            self.dedupe_checkbox
        )

        self.clipboard_checkbox = QCheckBox(
            "Monitora automaticamente gli appunti"
        )

        options_layout.addWidget(
            self.clipboard_checkbox
        )

        options_layout.addStretch()

        options_group.setMaximumHeight(
            45
        )

        main_layout.addWidget(
            options_group
        )

        # ====================================================
        # INVIO
        # ====================================================

        send_layout = QHBoxLayout()

        self.send_button = QPushButton(
            "▶ INVIA TUTTO A eMule"
        )

        self.send_selected_button = QPushButton(
            "▶ INVIA SELEZIONATI"
        )

        self.stop_button = QPushButton(
            "■ STOP"
        )

        self.send_button.setMinimumHeight(
            38
        )

        self.send_selected_button.setMinimumHeight(
            38
        )

        self.stop_button.setMinimumHeight(
            38
        )

        self.stop_button.setEnabled(
            False
        )

        send_layout.addWidget(
            self.send_button
        )

        send_layout.addWidget(
            self.send_selected_button
        )

        send_layout.addWidget(
            self.stop_button
        )

        main_layout.addLayout(
            send_layout
        )

        # ====================================================
        # SALVATAGGIO
        # ====================================================

        save_layout = QHBoxLayout()

        self.save_button = QPushButton(
            "💾 Salva lista"
        )

        self.load_button = QPushButton(
            "📁 Carica lista"
        )

        save_layout.addWidget(
            self.save_button
        )

        save_layout.addWidget(
            self.load_button
        )

        save_layout.addStretch()

        main_layout.addLayout(
            save_layout
        )

        # ====================================================
        # PROGRESS
        # ====================================================

        self.progress = QProgressBar()

        self.progress.setMaximumHeight(
            18
        )

        main_layout.addWidget(
            self.progress
        )

        # ====================================================
        # STATO
        # ====================================================

        self.status_label = QLabel(
            "Pronto."
        )

        self.status_label.setMaximumHeight(
            22
        )

        main_layout.addWidget(
            self.status_label
        )

        # ====================================================
        # CONNESSIONI
        # ====================================================

        self.go_button.clicked.connect(
            self.navigate
        )

        self.url_edit.returnPressed.connect(
            self.navigate
        )

        self.back_button.clicked.connect(
            self.webview.back
        )

        self.forward_button.clicked.connect(
            self.webview.forward
        )

        self.reload_button.clicked.connect(
            self.webview.reload
        )

        self.home_button.clicked.connect(
            self.go_home
        )

        self.scan_button.clicked.connect(
            self.scan_current_page
        )

        self.clear_browser_button.clicked.connect(
            self.clear_all
        )

        self.paste_button.clicked.connect(
            self.paste_clipboard
        )

        self.import_button.clicked.connect(
            self.import_files
        )

        self.remove_button.clicked.connect(
            self.remove_selected
        )

        self.clear_button.clicked.connect(
            self.clear_all
        )

        self.send_button.clicked.connect(
            self.send_all
        )

        self.send_selected_button.clicked.connect(
            self.send_selected
        )

        self.stop_button.clicked.connect(
            self.stop_sending
        )

        self.save_button.clicked.connect(
            self.save_list
        )

        self.load_button.clicked.connect(
            self.load_list
        )

        self.clipboard_checkbox.stateChanged.connect(
            self.toggle_clipboard
        )

    # ========================================================
    # BROWSER
    # ========================================================

    def setup_browser(self):

        self.webview.urlChanged.connect(
            self.browser_url_changed
        )

        self.webview.loadFinished.connect(
            self.browser_loaded
        )

        self.go_home()

    def go_home(self):

        self.webview.setUrl(
            QUrl(
                "https://www.google.com"
            )
        )

    def navigate(self):

        address = (
            self.url_edit.text()
            .strip()
        )

        if not address:
            return

        if not re.match(
            r"^[a-zA-Z]+://",
            address
        ):

            address = (
                "https://"
                + address
            )

        self.webview.setUrl(
            QUrl(address)
        )

    def browser_url_changed(
        self,
        url
    ):

        self.url_edit.setText(
            url.toString()
        )

    def browser_loaded(
        self,
        success
    ):

        if not success:

            self.status_label.setText(
                "Errore caricamento pagina."
            )

            return

        self.status_label.setText(
            "Pagina caricata."
        )

        if self.scan_checkbox.isChecked():

            QTimer.singleShot(
                700,
                self.scan_current_page
            )

    # ========================================================
    # SCANSIONE PAGINA
    # ========================================================

    def scan_current_page(self):

        if not self.scan_checkbox.isChecked():
            return

        javascript = """
        (() => {
            return document.documentElement.outerHTML;
        })();
        """

        self.webview.page().runJavaScript(
            javascript,
            self.process_page
        )

    def process_page(
        self,
        html
    ):

        if not html:
            return

        links = extract_ed2k(
            html
        )

        if not links:

            self.status_label.setText(
                "Nessun link ed2k:// trovato."
            )

            return

        before = (
            self.list_widget.count()
        )

        self.add_links(
            links
        )

        added = (
            self.list_widget.count()
            - before
        )

        self.status_label.setText(
            f"Scansione completata: "
            f"{len(links)} trovati, "
            f"{added} nuovi."
        )

    # ========================================================
    # CLIPBOARD
    # ========================================================

    def setup_clipboard(self):

        self.clipboard = (
            QApplication.clipboard()
        )

        self.clipboard_timer = QTimer(
            self
        )

        self.clipboard_timer.setInterval(
            500
        )

        self.clipboard_timer.timeout.connect(
            self.check_clipboard
        )

        self.clipboard_timer.start()

    def toggle_clipboard(
        self,
        state
    ):

        self.clipboard_monitor_enabled = (
            state
            == Qt.CheckState.Checked.value
        )

        self.last_clipboard = (
            self.clipboard.text()
        )

    def check_clipboard(self):

        if not self.clipboard_monitor_enabled:
            return

        text = self.clipboard.text()

        if not text:
            return

        if text == self.last_clipboard:
            return

        self.last_clipboard = text

        links = extract_ed2k(
            text
        )

        if links:

            before = (
                self.list_widget.count()
            )

            self.add_links(
                links
            )

            added = (
                self.list_widget.count()
                - before
            )

            if added:

                self.status_label.setText(
                    f"Appunti: {added} "
                    f"nuovi link."
                )

    def paste_clipboard(self):

        text = self.clipboard.text()

        links = extract_ed2k(
            text
        )

        if not links:

            QMessageBox.information(
                self,
                "Appunti",
                "Nessun link ed2k:// trovato."
            )

            return

        before = (
            self.list_widget.count()
        )

        self.add_links(
            links
        )

        added = (
            self.list_widget.count()
            - before
        )

        self.status_label.setText(
            f"Incollati {added} nuovi link."
        )

    # ========================================================
    # LISTA
    # ========================================================

    def get_links(self):

        links = []

        for index in range(
            self.list_widget.count()
        ):

            item = (
                self.list_widget.item(
                    index
                )
            )

            link = item.data(
                Qt.ItemDataRole.UserRole
            )

            if link:
                links.append(link)

        return links

    def add_links(
        self,
        links
    ):

        existing = set()

        if self.dedupe_checkbox.isChecked():

            existing = {
                link.lower()
                for link in self.get_links()
            }

        added = 0

        for link in links:

            if not link.lower().startswith(
                "ed2k://"
            ):
                continue

            key = link.lower()

            if (
                self.dedupe_checkbox.isChecked()
                and key in existing
            ):
                continue

            name = filename_from_link(
                link
            )

            item = QListWidgetItem(
                name
            )

            item.setToolTip(
                link
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                link
            )

            self.list_widget.addItem(
                item
            )

            existing.add(
                key
            )

            added += 1

        self.update_counter()

        return added

    def update_counter(self):

        self.link_counter.setText(
            f"Link: {self.list_widget.count()}"
        )

    def remove_selected(self):

        selected = (
            self.list_widget.selectedItems()
        )

        for item in selected:

            self.list_widget.takeItem(
                self.list_widget.row(item)
            )

        self.update_counter()

    def clear_all(self):

        self.list_widget.clear()

        self.progress.setValue(
            0
        )

        self.update_counter()

        self.status_label.setText(
            "Lista svuotata."
        )

    # ========================================================
    # IMPORTAZIONE
    # ========================================================

    def import_files(self):

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Importa file eD2K",
            "",
            "eD2K/TXT (*.ed2k *.txt);;Tutti (*.*)"
        )

        if not files:
            return

        total_added = 0

        for filename in files:

            try:

                text = Path(
                    filename
                ).read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                links = extract_ed2k(
                    text
                )

                total_added += (
                    self.add_links(
                        links
                    )
                )

            except Exception as error:

                QMessageBox.warning(
                    self,
                    "Errore",
                    str(error)
                )

        self.status_label.setText(
            f"Importati {total_added} nuovi link."
        )

    # ========================================================
    # INVIO
    # ========================================================

    def send_all(self):

        self.start_sender(
            self.get_links()
        )

    def send_selected(self):

        links = []

        for item in (
            self.list_widget.selectedItems()
        ):

            link = item.data(
                Qt.ItemDataRole.UserRole
            )

            if link:
                links.append(link)

        self.start_sender(
            links
        )

    def start_sender(
        self,
        links
    ):

        if not links:

            QMessageBox.information(
                self,
                "eMule",
                "Nessun link da inviare."
            )

            return

        if self.sender_thread:

            return

        delay = (
            self.delay_spin.value()
        )

        self.send_button.setEnabled(
            False
        )

        self.send_selected_button.setEnabled(
            False
        )

        self.stop_button.setEnabled(
            True
        )

        self.progress.setValue(
            0
        )

        self.sender_thread = SenderThread(
            links,
            delay
        )

        self.sender_thread.progress.connect(
            self.update_progress
        )

        self.sender_thread.status.connect(
            self.status_label.setText
        )

        self.sender_thread.completed.connect(
            self.sender_finished
        )

        self.sender_thread.start()

    def update_progress(
        self,
        current,
        total
    ):

        if total <= 0:
            return

        value = int(
            current
            * 100
            / total
        )

        self.progress.setValue(
            value
        )

    def stop_sending(self):

        if self.sender_thread:

            self.sender_thread.stop()

            self.status_label.setText(
                "Arresto richiesto..."
            )

    def sender_finished(
        self,
        sent,
        failed,
        stopped
    ):

        self.send_button.setEnabled(
            True
        )

        self.send_selected_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            False
        )

        if stopped:

            self.status_label.setText(
                f"Invio interrotto - "
                f"Inviati: {sent}, "
                f"falliti: {failed}."
            )

        else:

            self.progress.setValue(
                100
            )

            self.status_label.setText(
                f"Invio completato - "
                f"Inviati: {sent}, "
                f"falliti: {failed}."
            )

        self.sender_thread = None

    # ========================================================
    # SALVATAGGIO
    # ========================================================

    def save_list(self):

        filename, _ = (
            QFileDialog.getSaveFileName(
                self,
                "Salva lista",
                "links.ed2k",
                "eD2K (*.ed2k);;JSON (*.json)"
            )
        )

        if not filename:
            return

        links = self.get_links()

        try:

            if filename.lower().endswith(
                ".json"
            ):

                Path(filename).write_text(
                    json.dumps(
                        links,
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding="utf-8"
                )

            else:

                Path(filename).write_text(
                    "\n".join(links),
                    encoding="utf-8"
                )

            self.status_label.setText(
                "Lista salvata."
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Errore",
                str(error)
            )

    def load_list(self):

        filename, _ = (
            QFileDialog.getOpenFileName(
                self,
                "Carica lista",
                "",
                "eD2K/JSON (*.ed2k *.txt *.json);;Tutti (*.*)"
            )
        )

        if not filename:
            return

        try:

            if filename.lower().endswith(
                ".json"
            ):

                links = json.loads(
                    Path(filename).read_text(
                        encoding="utf-8"
                    )
                )

            else:

                text = Path(
                    filename
                ).read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                links = extract_ed2k(
                    text
                )

            self.add_links(
                links
            )

            self.status_label.setText(
                "Lista caricata."
            )

        except Exception as error:

            QMessageBox.critical(
                self,
                "Errore",
                str(error)
            )

    # ========================================================
    # SETTINGS
    # ========================================================

    def load_settings(self):

        if not self.settings_file.exists():
            return

        try:

            data = json.loads(
                self.settings_file.read_text(
                    encoding="utf-8"
                )
            )

            delay = int(
                data.get(
                    "delay",
                    1
                )
            )

            self.delay_spin.setValue(
                max(
                    0,
                    min(
                        delay,
                        3600
                    )
                )
            )

            self.dedupe_checkbox.setChecked(
                bool(
                    data.get(
                        "dedupe",
                        True
                    )
                )
            )

        except Exception:
            pass

    def save_settings(self):

        try:

            data = {
                "delay":
                    self.delay_spin.value(),

                "dedupe":
                    self.dedupe_checkbox.isChecked()
            }

            self.settings_file.write_text(
                json.dumps(
                    data,
                    indent=2
                ),
                encoding="utf-8"
            )

        except Exception:
            pass

    # ========================================================
    # CHIUSURA
    # ========================================================

    def closeEvent(
        self,
        event
    ):

        self.save_settings()

        if self.sender_thread:

            self.sender_thread.stop()

            self.sender_thread.wait(
                2000
            )

        event.accept()


# ============================================================
# MAIN
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        APP_NAME
    )

    app.setApplicationVersion(
        VERSION
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()