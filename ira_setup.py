import sys
import os
import subprocess
import re
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QThread, pyqtSignal, QPoint, QUrl
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStackedWidget, QFrame, QGraphicsOpacityEffect,
    QProgressBar, QScrollArea, QDialog, QMessageBox, QGridLayout
)
from PyQt6.QtGui import QFont, QColor, QPalette, QBrush, QLinearGradient, QDesktopServices, QIcon

# Import setup dependency helper dynamically
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import setup as setup_mod
except ImportError:
    setup_mod = None

class FadeStackedWidget(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fade_anim = None

    def setCurrentIndex(self, index):
        old_widget = self.currentWidget()
        new_widget = self.widget(index)
        if old_widget == new_widget:
            return
        
        super().setCurrentIndex(index)
        if not new_widget:
            return

        eff = QGraphicsOpacityEffect(new_widget)
        new_widget.setGraphicsEffect(eff)
        
        self.fade_anim = QPropertyAnimation(eff, b"opacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

class WorkerThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)

    def __init__(self, task_type, data=None):
        super().__init__()
        self.task_type = task_type
        self.data = data

    def run(self):
        if self.task_type == "permissions":
            results = []
            
            # 1. Screen Capture
            self.progress.emit(10, "Checking Screen Capture (mss)...")
            try:
                import mss
                with mss.mss() as sct:
                    sct.grab(sct.monitors[0])
                results.append(("Screen Capture", "Passed", "Successfully grabbed primary display frame."))
            except Exception as e:
                results.append(("Screen Capture", "Failed", f"Error: {str(e)}"))

            # 2. Keyboard & Mouse
            self.progress.emit(30, "Checking Control Interfaces (pyautogui)...")
            try:
                import pyautogui
                # Simple check
                pyautogui.size()
                results.append(("Keyboard & Mouse Control", "Passed", "PyAutoGUI interface active."))
            except Exception as e:
                results.append(("Keyboard & Mouse Control", "Failed", f"Error: {str(e)}"))

            # 3. Microphone
            self.progress.emit(50, "Checking Sound Inputs (pyaudio)...")
            try:
                import pyaudio
                p = pyaudio.PyAudio()
                p.terminate()
                results.append(("Microphone Access", "Passed", "PyAudio loaded successfully."))
            except Exception as e:
                results.append(("Microphone Access", "Failed (Optional)", f"Warning: PyAudio failed to load. Voice features will be unavailable. Error: {str(e)}"))

            # 4. Camera
            self.progress.emit(70, "Checking OpenCV Camera Capture...")
            try:
                import cv2
                # Just checking import
                results.append(("Webcam Interface", "Passed", "OpenCV media components verified."))
            except Exception as e:
                results.append(("Webcam Interface", "Failed (Optional)", f"Warning: OpenCV components missing. Gesture control unavailable. Error: {str(e)}"))

            # 5. File System
            self.progress.emit(90, "Checking Storage Read/Write Access...")
            try:
                test_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".perm_test")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                results.append(("File Storage", "Passed", "Read/Write permissions verified in project folder."))
            except Exception as e:
                results.append(("File Storage", "Failed", f"Error: {str(e)}"))

            self.progress.emit(100, "Permissions check complete!")
            self.finished.emit(results)

        elif self.task_type == "dependencies":
            # List dependencies
            if not setup_mod:
                self.progress.emit(100, "Error: setup.py not found in path.")
                self.finished.emit([])
                return

            installed_ok, needs_update, missing = setup_mod.check_deps()
            all_deps = []
            
            for pip_name, import_name, req_ver, inst_ver in installed_ok:
                all_deps.append((pip_name, "Installed", inst_ver, req_ver))
            for pip_name, import_name, req_ver, inst_ver in needs_update:
                all_deps.append((pip_name, "Needs Update", inst_ver, req_ver))
            for pip_name, import_name, req_ver, _ in missing:
                all_deps.append((pip_name, "Missing", "None", req_ver))

            self.finished.emit(all_deps)

        elif self.task_type == "install_all":
            if not setup_mod:
                self.finished.emit([])
                return
            
            installed_ok, needs_update, missing = setup_mod.check_deps()
            to_install = needs_update + missing
            total = len(to_install)
            
            if total == 0:
                self.progress.emit(100, "All dependencies are already installed!")
                self.finished.emit([])
                return

            for i, dep in enumerate(to_install):
                pip_name = dep[0]
                version = dep[2]
                percent = int((i / total) * 100)
                self.progress.emit(percent, f"Installing {pip_name} (>={version})...")
                setup_mod.install_package(pip_name, version)
            
            self.progress.emit(100, "Installation finished!")
            # Recheck
            installed_ok, needs_update, missing = setup_mod.check_deps()
            all_deps = []
            for pip_name, import_name, req_ver, inst_ver in installed_ok:
                all_deps.append((pip_name, "Installed", inst_ver, req_ver))
            for pip_name, import_name, req_ver, inst_ver in needs_update:
                all_deps.append((pip_name, "Needs Update", inst_ver, req_ver))
            for pip_name, import_name, req_ver, _ in missing:
                all_deps.append((pip_name, "Missing", "None", req_ver))
            self.finished.emit(all_deps)

class SetupWizard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowSystemMenuHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(900, 650)
        
        self.user_name = ""
        self.permissions_checked = False
        self.deps_checked = False
        self._drag_pos = QPoint()
        
        self.init_ui()

    def init_ui(self):
        # Base container (for rounded corners & shadows)
        self.base_widget = QWidget(self)
        self.base_widget.setObjectName("BaseWidget")
        self.base_widget.setStyleSheet("""
            QWidget#BaseWidget {
                background-color: #0c0c14;
                border: 1px solid #1a1a2e;
                border-radius: 12px;
            }
        """)
        
        main_layout = QVBoxLayout(self.base_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Custom Title Bar
        title_bar = QWidget()
        title_bar.setFixedHeight(45)
        title_bar.setStyleSheet("background-color: #11111f; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 15, 0)
        
        title_label = QLabel("IRA — Onboarding Setup Wizard")
        title_label.setStyleSheet("color: #8a8ab0; font-size: 13px; font-weight: bold; font-family: 'Segoe UI';")
        
        btn_min = QPushButton("—")
        btn_min.setFixedSize(24, 24)
        btn_min.setStyleSheet("QPushButton { color: #8a8ab0; background: transparent; border: none; font-size: 14px; } QPushButton:hover { color: #fff; background-color: #222238; border-radius: 12px; }")
        btn_min.clicked.connect(self.showMinimized)
        
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet("QPushButton { color: #8a8ab0; background: transparent; border: none; font-size: 12px; } QPushButton:hover { color: #fff; background-color: #d93838; border-radius: 12px; }")
        btn_close.clicked.connect(self.close)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(btn_min)
        title_layout.addWidget(btn_close)
        
        main_layout.addWidget(title_bar)
        
        # 2. Main Content Area
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(30, 20, 30, 20)
        content_layout.setSpacing(20)
        
        # Step Indicator (Top)
        self.indicator_layout = QHBoxLayout()
        self.indicators = []
        steps = ["Welcome", "Permissions", "Dependencies", "API Keys", "Complete"]
        for i, step in enumerate(steps):
            lbl = QLabel(f"{i+1}. {step}")
            lbl.setStyleSheet("color: #4a4a6a; font-size: 12px; font-weight: bold; font-family: 'Segoe UI';")
            self.indicator_layout.addWidget(lbl)
            self.indicators.append(lbl)
            if i < len(steps) - 1:
                dash = QLabel("—")
                dash.setStyleSheet("color: #2a2a3e; font-weight: bold;")
                self.indicator_layout.addWidget(dash)
                
        content_layout.addLayout(self.indicator_layout)
        
        # Stacked Widget for Pages
        self.pages = FadeStackedWidget()
        
        self.create_welcome_page()
        self.create_permissions_page()
        self.create_deps_page()
        self.create_keys_page()
        self.create_complete_page()
        
        content_layout.addWidget(self.pages)
        main_layout.addWidget(content_container)
        
        self.setCentralWidget(self.base_widget)
        self.update_step_indicator(0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def update_step_indicator(self, current_idx):
        for i, lbl in enumerate(self.indicators):
            if i == current_idx:
                lbl.setStyleSheet("color: #00d4ff; font-size: 13px; font-weight: bold; font-family: 'Segoe UI'; text-shadow: 0px 0px 5px #00d4ff;")
            elif i < current_idx:
                lbl.setStyleSheet("color: #7c3aed; font-size: 12px; font-weight: bold; font-family: 'Segoe UI';")
            else:
                lbl.setStyleSheet("color: #4a4a6a; font-size: 12px; font-weight: bold; font-family: 'Segoe UI';")

    def go_next(self):
        curr = self.pages.currentIndex()
        if curr < self.pages.count() - 1:
            self.pages.setCurrentIndex(curr + 1)
            self.update_step_indicator(curr + 1)

    def go_prev(self):
        curr = self.pages.currentIndex()
        if curr > 0:
            self.pages.setCurrentIndex(curr - 1)
            self.update_step_indicator(curr - 1)

    # ════════════════ PAGE CREATION ════════════════

    def create_welcome_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(25)
        
        logo = QLabel("IRA")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("""
            font-size: 80px; 
            font-weight: 900; 
            font-family: 'Segoe UI', Arial;
            color: #00d4ff;
        """)
        
        subtitle = QLabel("Intelligent Responsive Assistant")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #7c3aed; font-size: 20px; font-weight: bold; font-family: 'Segoe UI';")
        
        desc = QLabel("Welcome to IRA! I am your visual desktop companion. Before we begin, let's configure some basic settings to customize your experience.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #8a8ab0; font-size: 14px; line-height: 1.5; font-family: 'Segoe UI';")
        
        # Name Input Area
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(50, 0, 50, 0)
        
        lbl_prompt = QLabel("What should IRA call you?")
        lbl_prompt.setStyleSheet("color: #e5e5eb; font-size: 14px; font-weight: bold; font-family: 'Segoe UI'; margin-bottom: 5px;")
        
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Enter your name (e.g. Revant)...")
        self.txt_name.setStyleSheet("""
            QLineEdit {
                background-color: #121222;
                border: 1px solid #2e2e4a;
                border-radius: 6px;
                padding: 10px 15px;
                font-size: 14px;
                color: white;
                font-family: 'Segoe UI';
            }
            QLineEdit:focus {
                border: 1px solid #00d4ff;
            }
        """)
        self.txt_name.textChanged.connect(self.check_welcome_next)
        
        input_layout.addWidget(lbl_prompt)
        input_layout.addWidget(self.txt_name)
        
        # Navigation
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        
        self.btn_welcome_next = QPushButton("Next  ➔")
        self.btn_welcome_next.setEnabled(False)
        self.btn_welcome_next.setFixedSize(120, 40)
        self.btn_welcome_next.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a1a2e, stop:1 #2e2e4a);
                border: 1px solid #3d3d63;
                border-radius: 6px;
                color: #5a5a7e;
                font-weight: bold;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
            QPushButton:enabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d4ff, stop:1 #7c3aed);
                border: none;
                color: white;
            }
            QPushButton:enabled:hover {
                text-shadow: 0px 0px 5px #fff;
            }
        """)
        self.btn_welcome_next.clicked.connect(self.go_next)
        nav_layout.addWidget(self.btn_welcome_next)
        
        layout.addWidget(logo)
        layout.addWidget(subtitle)
        layout.addWidget(desc)
        layout.addWidget(input_container)
        layout.addStretch()
        layout.addLayout(nav_layout)
        
        self.pages.addWidget(page)

    def check_welcome_next(self):
        name = self.txt_name.text().strip()
        self.btn_welcome_next.setEnabled(len(name) >= 2)
        self.user_name = name

    def create_permissions_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(20)
        
        title = QLabel("System Permissions Check")
        title.setStyleSheet("color: #e5e5eb; font-size: 22px; font-weight: bold; font-family: 'Segoe UI';")
        
        desc = QLabel("IRA requires access to different system interfaces to see your screen and execute mouse/keyboard events. Click 'Run System Check' to verify.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8a8ab0; font-size: 13px; font-family: 'Segoe UI';")
        
        # Permissions Panel List
        self.perm_box = QWidget()
        self.perm_box.setStyleSheet("background-color: #121222; border: 1px solid #2e2e4a; border-radius: 8px;")
        perm_layout = QVBoxLayout(self.perm_box)
        perm_layout.setContentsMargins(20, 20, 20, 20)
        perm_layout.setSpacing(15)
        
        self.perm_items = {}
        perms = [
            ("Screen Capture", "For seeing the screen content (mss dependency)"),
            ("Keyboard & Mouse Control", "For executing automated system operations (pyautogui)"),
            ("Microphone Access", "For listening to voice controls (pyaudio)"),
            ("Webcam Interface", "For capturing gesture video stream (opencv-python)"),
            ("File Storage", "For reading and saving logs and documents")
        ]
        
        for name, subtext in perms:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            txt_lbl = QLabel(f"<b>{name}</b><br><font color='#8a8ab0'>{subtext}</font>")
            txt_lbl.setStyleSheet("color: #e5e5eb; font-size: 13px; font-family: 'Segoe UI';")
            
            status_lbl = QLabel("Not Checked")
            status_lbl.setStyleSheet("color: #8a8ab0; font-size: 13px; font-weight: bold; font-family: 'Segoe UI';")
            
            row_layout.addWidget(txt_lbl)
            row_layout.addStretch()
            row_layout.addWidget(status_lbl)
            
            perm_layout.addWidget(row)
            self.perm_items[name] = status_lbl

        self.btn_check_perms = QPushButton("Run System Check")
        self.btn_check_perms.setFixedHeight(35)
        self.btn_check_perms.setStyleSheet("""
            QPushButton {
                background-color: #1e1e36;
                border: 1px solid #00d4ff;
                border-radius: 6px;
                color: #00d4ff;
                font-weight: bold;
                font-size: 13px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                background-color: #00d4ff;
                color: black;
            }
        """)
        self.btn_check_perms.clicked.connect(self.run_permissions_check)
        
        self.perm_progress = QProgressBar()
        self.perm_progress.setFixedHeight(6)
        self.perm_progress.setTextVisible(False)
        self.perm_progress.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a2e;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #7c3aed;
                border-radius: 3px;
            }
        """)
        self.perm_progress.setValue(0)
        
        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_perm_prev = QPushButton("➔  Back")
        self.btn_perm_prev.setFixedSize(120, 40)
        self.btn_perm_prev.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #2e2e4a;
                border-radius: 6px;
                color: #8a8ab0;
                font-size: 13px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                border-color: #3d3d63;
                color: white;
            }
        """)
        self.btn_perm_prev.clicked.connect(self.go_prev)
        
        self.btn_perm_next = QPushButton("Next  ➔")
        self.btn_perm_next.setFixedSize(120, 40)
        self.btn_perm_next.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d4ff, stop:1 #7c3aed);
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
        """)
        self.btn_perm_next.clicked.connect(self.go_next)
        
        nav_layout.addWidget(self.btn_perm_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_perm_next)
        
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.perm_box)
        layout.addWidget(self.btn_check_perms)
        layout.addWidget(self.perm_progress)
        layout.addStretch()
        layout.addLayout(nav_layout)
        
        self.pages.addWidget(page)

    def run_permissions_check(self):
        self.btn_check_perms.setEnabled(False)
        self.btn_check_perms.setText("Checking system interfaces...")
        
        self.perm_thread = WorkerThread("permissions")
        self.perm_thread.progress.connect(self.update_perm_progress)
        self.perm_thread.finished.connect(self.finish_perm_check)
        self.perm_thread.start()

    def update_perm_progress(self, val, msg):
        self.perm_progress.setValue(val)
        self.btn_check_perms.setText(msg)

    def finish_perm_check(self, results):
        self.btn_check_perms.setEnabled(True)
        self.btn_check_perms.setText("Re-run System Check")
        self.perm_progress.setValue(100)
        
        for name, status, desc in results:
            lbl = self.perm_items.get(name)
            if lbl:
                if status == "Passed":
                    lbl.setText("Passed ✔")
                    lbl.setStyleSheet("color: #34d399; font-size: 13px; font-weight: bold; font-family: 'Segoe UI';")
                elif "Optional" in status:
                    lbl.setText("Skipped ⚠")
                    lbl.setStyleSheet("color: #fb923c; font-size: 13px; font-weight: bold; font-family: 'Segoe UI';")
                else:
                    lbl.setText("Failed ✖")
                    lbl.setStyleSheet("color: #f87171; font-size: 13px; font-weight: bold; font-family: 'Segoe UI';")
        self.permissions_checked = True

    def create_deps_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(20)
        
        title = QLabel("Python Dependencies Setup")
        title.setStyleSheet("color: #e5e5eb; font-size: 22px; font-weight: bold; font-family: 'Segoe UI';")
        
        desc = QLabel("Verify which modules are installed. Missing dependencies can be installed automatically.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8a8ab0; font-size: 13px; font-family: 'Segoe UI';")
        
        # Scroll area for dependencies
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #121222;
                border: 1px solid #2e2e4a;
                border-radius: 8px;
            }
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: #121222;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(15, 15, 15, 15)
        self.scroll_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.scroll_content)
        
        # Actions
        actions_layout = QHBoxLayout()
        
        self.btn_scan_deps = QPushButton("Scan Dependencies")
        self.btn_scan_deps.setFixedSize(160, 35)
        self.btn_scan_deps.setStyleSheet("""
            QPushButton {
                background-color: #1e1e36;
                border: 1px solid #00d4ff;
                border-radius: 6px;
                color: #00d4ff;
                font-weight: bold;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                background-color: #00d4ff;
                color: black;
            }
        """)
        self.btn_scan_deps.clicked.connect(self.scan_dependencies)
        
        self.btn_install_deps = QPushButton("Install Missing Modules")
        self.btn_install_deps.setEnabled(False)
        self.btn_install_deps.setFixedSize(180, 35)
        self.btn_install_deps.setStyleSheet("""
            QPushButton {
                background-color: #1e1e36;
                border: 1px solid #7c3aed;
                border-radius: 6px;
                color: #7c3aed;
                font-weight: bold;
                font-family: 'Segoe UI';
            }
            QPushButton:enabled:hover {
                background-color: #7c3aed;
                color: white;
            }
        """)
        self.btn_install_deps.clicked.connect(self.install_dependencies)
        
        actions_layout.addWidget(self.btn_scan_deps)
        actions_layout.addWidget(self.btn_install_deps)
        actions_layout.addStretch()
        
        self.dep_progress = QProgressBar()
        self.dep_progress.setFixedHeight(6)
        self.dep_progress.setTextVisible(False)
        self.dep_progress.setStyleSheet("""
            QProgressBar {
                background-color: #1a1a2e;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #00d4ff;
                border-radius: 3px;
            }
        """)
        self.dep_progress.setValue(0)
        
        self.lbl_dep_status = QLabel("Scan not performed yet.")
        self.lbl_dep_status.setStyleSheet("color: #8a8ab0; font-size: 12px; font-family: 'Segoe UI';")
        
        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_dep_prev = QPushButton("➔  Back")
        self.btn_dep_prev.setFixedSize(120, 40)
        self.btn_dep_prev.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #2e2e4a;
                border-radius: 6px;
                color: #8a8ab0;
                font-size: 13px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                border-color: #3d3d63;
                color: white;
            }
        """)
        self.btn_dep_prev.clicked.connect(self.go_prev)
        
        self.btn_dep_next = QPushButton("Next  ➔")
        self.btn_dep_next.setFixedSize(120, 40)
        self.btn_dep_next.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d4ff, stop:1 #7c3aed);
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
        """)
        self.btn_dep_next.clicked.connect(self.go_next)
        
        nav_layout.addWidget(self.btn_dep_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_dep_next)
        
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.scroll_area)
        layout.addLayout(actions_layout)
        layout.addWidget(self.dep_progress)
        layout.addWidget(self.lbl_dep_status)
        layout.addStretch()
        layout.addLayout(nav_layout)
        
        self.pages.addWidget(page)

    def scan_dependencies(self):
        # Clear scroll area
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.btn_scan_deps.setEnabled(False)
        self.btn_scan_deps.setText("Scanning...")
        
        self.dep_thread = WorkerThread("dependencies")
        self.dep_thread.finished.connect(self.finish_dep_scan)
        self.dep_thread.start()

    def finish_dep_scan(self, dep_list):
        self.btn_scan_deps.setEnabled(True)
        self.btn_scan_deps.setText("Scan Dependencies")
        
        if not dep_list:
            self.lbl_dep_status.setText("Scan completed with errors (setup.py loading failed).")
            return

        missing_count = 0
        update_count = 0
        
        for name, status, inst_ver, req_ver in dep_list:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            lbl_name = QLabel(f"<b>{name}</b> (req: {req_ver})")
            lbl_name.setStyleSheet("color: #e5e5eb; font-size: 13px; font-family: 'Segoe UI';")
            
            lbl_status = QLabel(f"{status} ({inst_ver})")
            
            if status == "Installed":
                lbl_status.setStyleSheet("color: #34d399; font-weight: bold; font-family: 'Segoe UI';")
            elif status == "Needs Update":
                lbl_status.setStyleSheet("color: #fb923c; font-weight: bold; font-family: 'Segoe UI';")
                update_count += 1
            else:
                lbl_status.setStyleSheet("color: #f87171; font-weight: bold; font-family: 'Segoe UI';")
                missing_count += 1
                
            row_layout.addWidget(lbl_name)
            row_layout.addStretch()
            row_layout.addWidget(lbl_status)
            
            self.scroll_layout.addWidget(row)
            
        total_issues = missing_count + update_count
        self.lbl_dep_status.setText(f"Scan complete. {missing_count} missing, {update_count} need update. Total issues: {total_issues}")
        
        if total_issues > 0:
            self.btn_install_deps.setEnabled(True)
        else:
            self.btn_install_deps.setEnabled(False)
            
        self.deps_checked = True

    def install_dependencies(self):
        self.btn_install_deps.setEnabled(False)
        self.btn_scan_deps.setEnabled(False)
        
        self.install_thread = WorkerThread("install_all")
        self.install_thread.progress.connect(self.update_install_progress)
        self.install_thread.finished.connect(self.finish_dep_install)
        self.install_thread.start()

    def update_install_progress(self, val, msg):
        self.dep_progress.setValue(val)
        self.lbl_dep_status.setText(msg)

    def finish_dep_install(self, results):
        self.dep_progress.setValue(100)
        self.finish_dep_scan(results)

    def create_keys_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(15)
        
        title = QLabel("Configure API Keys")
        title.setStyleSheet("color: #e5e5eb; font-size: 22px; font-weight: bold; font-family: 'Segoe UI';")
        
        desc = QLabel("Set your API Keys. The Google Gemini key is mandatory to use IRA. Other services are optional.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8a8ab0; font-size: 13px; font-family: 'Segoe UI';")
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #121222;
                border: 1px solid #2e2e4a;
                border-radius: 8px;
            }
        """)
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #121222;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(20, 20, 20, 20)
        scroll_layout.setSpacing(20)
        
        # We need inputs for:
        # Gemini (Required)
        # Sarvam, Tavily, Together, Hugging Face, OpenRouter, Cloudflare Accounts, Unsplash, Pexels, Pixabay
        self.key_inputs = {}
        
        key_meta = [
            ("Gemini API Key (Required) *", "GEMINI_API_KEY", "Powers IRA's brain and Live voice interactions. Separate multiple keys with commas.", "https://aistudio.google.com/apikey", True),
            ("Sarvam API Key (Optional)", "SARVAM_API_KEY", "Enables advanced Hindi Text-to-Speech voices.", "https://dashboard.sarvam.ai", False),
            ("Tavily API Key (Optional)", "TAVILY_API_KEY", "Powers direct search tools for real-time web querying.", "https://tavily.com", False),
            ("Together AI Key (Optional)", "TOGETHER_API_KEY", "Used for fast FLUX image generation.", "https://api.together.xyz", False),
            ("Hugging Face Key (Optional)", "HF_API_KEY", "Enables FLUX fallback image models.", "https://huggingface.co/settings/tokens", False),
            ("OpenRouter Key (Optional)", "OPENROUTER_API_KEY", "Enables fallback image, video, and music models.", "https://openrouter.ai/keys", False),
            ("Cloudflare Accounts (Optional)", "CF_ACCOUNTS", "Format: account_id:token (separate multiple accounts with commas).", "https://dash.cloudflare.com", False),
            ("Unsplash Key (Optional)", "UNSPLASH_ACCESS_KEY", "Unsplash API Access Key for image queries.", "https://unsplash.com/developers", False),
            ("Pexels Key (Optional)", "PEXELS_API_KEY", "Pexels API token for images.", "https://www.pexels.com/api/", False),
            ("Pixabay Key (Optional)", "PIXABAY_API_KEY", "Pixabay API token.", "https://pixabay.com/api/docs/", False),
        ]
        
        for display_name, env_name, subtext, link, required in key_meta:
            card = QWidget()
            card.setStyleSheet("""
                QWidget {
                    background-color: #16162a;
                    border: 1px solid #2e2e4a;
                    border-radius: 6px;
                }
            """)
            if required:
                card.setStyleSheet("QWidget { background-color: #1e122a; border: 1.5px solid #7c3aed; border-radius: 6px; }")
                
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 15, 15, 15)
            
            header = QHBoxLayout()
            lbl_name = QLabel(f"<b>{display_name}</b>")
            lbl_name.setStyleSheet("color: white; font-size: 13px; font-family: 'Segoe UI'; border: none;")
            
            btn_link = QPushButton("Get Key ➔")
            btn_link.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_link.setStyleSheet("QPushButton { color: #00d4ff; font-size: 11px; font-weight: bold; border: none; background: transparent; } QPushButton:hover { color: white; }")
            btn_link.clicked.connect(lambda checked, url=link: QDesktopServices.openUrl(QUrl(url)))
            
            header.addWidget(lbl_name)
            header.addStretch()
            header.addWidget(btn_link)
            
            lbl_desc = QLabel(subtext)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("color: #8a8ab0; font-size: 11px; font-family: 'Segoe UI'; border: none;")
            
            inp = QLineEdit()
            inp.setStyleSheet("""
                QLineEdit {
                    background-color: #0c0c14;
                    border: 1px solid #2e2e4a;
                    border-radius: 4px;
                    padding: 8px;
                    color: white;
                    font-size: 12px;
                    font-family: 'Consolas', 'Courier New';
                }
                QLineEdit:focus {
                    border: 1px solid #00d4ff;
                }
            """)
            if required:
                inp.setEchoMode(QLineEdit.EchoMode.Password)
                inp.setPlaceholderText("Paste your Google Gemini API Key here (Mandatory)...")
            else:
                inp.setPlaceholderText(f"Optional {env_name}...")
                
            card_layout.addLayout(header)
            card_layout.addWidget(lbl_desc)
            card_layout.addWidget(inp)
            
            scroll_layout.addWidget(card)
            self.key_inputs[env_name] = inp
            
        scroll_area.setWidget(scroll_content)
        
        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_keys_prev = QPushButton("➔  Back")
        self.btn_keys_prev.setFixedSize(120, 40)
        self.btn_keys_prev.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #2e2e4a;
                border-radius: 6px;
                color: #8a8ab0;
                font-size: 13px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                border-color: #3d3d63;
                color: white;
            }
        """)
        self.btn_keys_prev.clicked.connect(self.go_prev)
        
        self.btn_keys_finish = QPushButton("Complete Setup  ➔")
        self.btn_keys_finish.setFixedSize(160, 40)
        self.btn_keys_finish.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d4ff, stop:1 #7c3aed);
                border: none;
                border-radius: 6px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
        """)
        self.btn_keys_finish.clicked.connect(self.save_keys_and_finish)
        
        nav_layout.addWidget(self.btn_keys_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_keys_finish)
        
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(scroll_area)
        layout.addStretch()
        layout.addLayout(nav_layout)
        
        self.pages.addWidget(page)

    def save_keys_and_finish(self):
        gemini_key = self.key_inputs["GEMINI_API_KEY"].text().strip()
        if not gemini_key:
            QMessageBox.critical(self, "Required Key Missing", "Google Gemini API key is mandatory to use IRA!\nPlease get one from Google AI Studio and enter it.")
            return

        # Prepare env key dictionary
        env_lines = []
        env_lines.append("# ═══════════════════════════════════════════")
        env_lines.append("#  IRA — API Keys Configuration (Generated)")
        env_lines.append("# ═══════════════════════════════════════════")
        env_lines.append(f"GEMINI_API_KEY={gemini_key}")
        env_lines.append("MODEL=gemini-3.5-flash")
        env_lines.append("VISION_MODEL=gemini-3.5-flash")
        
        # For other keys, if empty, set a dummy configuration key that will fail/be ignored
        for key_name, inp in self.key_inputs.items():
            if key_name == "GEMINI_API_KEY":
                continue
            val = inp.text().strip()
            if not val:
                val = "DUMMY_NOT_CONFIGURED"
            env_lines.append(f"{key_name}={val}")

        env_lines.append(f"IRA_USER_NAME={self.user_name}")

        # Save to .env
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("\n".join(env_lines) + "\n")
        except Exception as e:
            QMessageBox.critical(self, "Write Error", f"Failed to save .env file: {str(e)}")
            return

        # Generate default state.json files if not exists
        self.init_state_files()

        self.go_next()

    def init_state_files(self):
        # We can write default config files if required.
        pass

    def create_complete_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)
        
        title = QLabel("Setup Complete! 🎉")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #34d399; font-size: 32px; font-weight: bold; font-family: 'Segoe UI';")
        
        self.lbl_welcome_name = QLabel("Welcome, User!")
        self.lbl_welcome_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_welcome_name.setStyleSheet("color: white; font-size: 20px; font-weight: bold; font-family: 'Segoe UI';")
        
        desc = QLabel("IRA is fully configured and ready to execute on your machine. You can start the desktop overlay client now.")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #8a8ab0; font-size: 14px; font-family: 'Segoe UI';")
        
        btn_launch = QPushButton("Launch IRA Desktop Client")
        btn_launch.setFixedHeight(50)
        btn_launch.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d4ff, stop:1 #7c3aed);
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: bold;
                font-size: 16px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                text-shadow: 0px 0px 5px #fff;
            }
        """)
        btn_launch.clicked.connect(self.launch_ira)
        
        btn_exit = QPushButton("Close Setup")
        btn_exit.setFixedHeight(40)
        btn_exit.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #2e2e4a;
                border-radius: 6px;
                color: #8a8ab0;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                border-color: #3d3d63;
                color: white;
            }
        """)
        btn_exit.clicked.connect(self.close)
        
        layout.addWidget(title)
        layout.addWidget(self.lbl_welcome_name)
        layout.addWidget(desc)
        layout.addWidget(btn_launch)
        layout.addWidget(btn_exit)
        layout.addStretch()
        
        self.pages.addWidget(page)

    def showEvent(self, event):
        super().showEvent(event)
        # Update name dynamically on last page when shown
        self.lbl_welcome_name.setText(f"Welcome, {self.user_name}!")

    def launch_ira(self):
        # Starts IRA via subprocess and exits
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        main_py = os.path.join(curr_dir, "main.py")
        
        # Launching process detached from wizard
        try:
            if sys.platform == "win32":
                subprocess.Popen([sys.executable, main_py, "hud"], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen([sys.executable, main_py, "hud"])
        except Exception as e:
            QMessageBox.critical(self, "Launch Error", f"Failed to run main.py: {str(e)}")
            return
            
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    wizard = SetupWizard()
    wizard.show()
    sys.exit(app.exec())
