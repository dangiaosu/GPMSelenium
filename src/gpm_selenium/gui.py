from __future__ import annotations

import shutil
import sys
import threading
from dataclasses import replace
from pathlib import Path
from queue import Empty, Queue
from threading import Event
from typing import Any, NoReturn

import requests
from PySide6.QtCore import QItemSelectionModel, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gpm_selenium.excel import preview_excel
from gpm_selenium.gpm import GpmClient, GpmGroup, GpmProfile
from gpm_selenium.profile_rows import build_rows_from_profiles, preview_rows_from_profiles
from gpm_selenium.runner import RuntimeConfig, default_runtime_config, run_selected_profiles_batch, run_task_batch
from gpm_selenium.session_cache import load_profiles, save_profiles
from gpm_selenium.store import PlatformStore, RegisteredTask
from gpm_selenium.task_loader import LoadedTask, load_task


class GeometricWolfLogo(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(38, 38)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        base_gradient = QLinearGradient(0, 0, 38, 38)
        base_gradient.setColorAt(0.0, QColor("#f8fafc"))
        base_gradient.setColorAt(1.0, QColor("#64748b"))
        painter.setBrush(base_gradient)
        painter.drawPolygon(
            QPolygonF(
                [
                    self._point(19, 3),
                    self._point(32, 12),
                    self._point(29, 31),
                    self._point(19, 36),
                    self._point(9, 31),
                    self._point(6, 12),
                ]
            )
        )

        painter.setBrush(QColor("#020617"))
        painter.drawPolygon(QPolygonF([self._point(19, 8), self._point(26, 15), self._point(19, 31)]))
        painter.drawPolygon(QPolygonF([self._point(19, 8), self._point(12, 15), self._point(19, 31)]))

        painter.setBrush(QColor("#22c55e"))
        painter.drawEllipse(13, 18, 3, 3)
        painter.drawEllipse(22, 18, 3, 3)

    def _point(self, x: float, y: float) -> object:
        from PySide6.QtCore import QPointF

        return QPointF(x, y)


class GradientTitle(QWidget):
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text: str = text
        self._font: QFont = QFont("Inter", 25, QFont.Weight.Bold)
        metrics = QFontMetrics(self._font)
        self.setFixedSize(metrics.horizontalAdvance(text) + 4, metrics.height() + 6)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(0.52, QColor("#d8dee8"))
        gradient.setColorAt(1.0, QColor("#7c8798"))
        painter.setPen(QPen(QBrush(gradient), 1))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


class BackgroundTabWidget(QTabWidget):
    def __init__(self, background_path: Path) -> None:
        super().__init__()
        self._background: QPixmap = QPixmap(str(background_path))

    def paintEvent(self, event: object) -> None:
        if not self._background.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            pane_top: int = self.tabBar().height() + 10
            pane_rect = QRect(0, pane_top, self.width(), max(1, self.height() - pane_top))
            painter.fillRect(pane_rect, QColor("#020617"))
            scaled = self._background.scaled(
                pane_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x: int = pane_rect.x() + (pane_rect.width() - scaled.width()) // 2
            y: int = pane_rect.y() + (pane_rect.height() - scaled.height()) // 2
            painter.setOpacity(0.36)
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)
            overlay = QLinearGradient(0, pane_rect.y(), 0, pane_rect.bottom())
            overlay.setColorAt(0.0, QColor(2, 6, 23, 76))
            overlay.setColorAt(0.5, QColor(2, 6, 23, 38))
            overlay.setColorAt(1.0, QColor(2, 6, 23, 128))
            painter.fillRect(pane_rect, overlay)
        super().paintEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GPMSelenium")
        self.resize(1180, 760)

        self.base_dir: Path = Path.cwd()
        self.tasks_dir: Path = self.base_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.store: PlatformStore = PlatformStore(self.base_dir / "gpm_selenium.sqlite3")
        self.profile_cache_path: Path = self.base_dir / ".session" / "profiles.json"
        self.event_queue: Queue[tuple[str, dict[str, Any]]] = Queue()
        self.worker_thread: threading.Thread | None = None
        self.stop_event: Event = Event()
        self.active_profile_ids: set[str] = set()
        self.failed_profile_ids: set[str] = set()
        self.profiles: list[GpmProfile] = []
        self.profile_by_id: dict[str, GpmProfile] = {}
        self.groups: list[GpmGroup] = []
        self.tabs: BackgroundTabWidget | None = None

        self.task_list = QListWidget()
        self.script_name_label = QLabel("No script selected")
        self.script_name_label.setObjectName("ScriptTitle")
        self.script_version_label = QLabel("-")
        self.script_version_label.setObjectName("ScriptBadge")
        self.script_success_label = QLabel("SUCCESS")
        self.script_success_label.setObjectName("SuccessBadge")
        self.script_module_label = QLabel("-")
        self.script_module_label.setObjectName("ScriptMeta")
        self.script_columns_label = QLabel("-")
        self.script_columns_label.setObjectName("ScriptColumns")
        self.script_description_label = QLabel("Load or select a script to inspect its contract.")
        self.script_description_label.setObjectName("MutedText")
        self.script_description_label.setWordWrap(True)

        self.profile_search_input = QLineEdit()
        self.profile_group_combo = QComboBox()
        self.profile_group_combo.setMinimumWidth(220)
        self.profile_table = QTableWidget(0, 7)
        self.profile_status_label = QLabel("No profiles loaded")

        self.use_excel_checkbox = QCheckBox("Use Excel input/status")
        self.use_excel_checkbox.setChecked(True)
        self.excel_path_input = QLineEdit()
        self.preview_label = QLabel("No Excel selected")
        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(1, 20)
        self.worker_spin.setValue(3)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(60)
        self.node_timeout_spin = QSpinBox()
        self.node_timeout_spin.setRange(1, 60)
        self.node_timeout_spin.setValue(8)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(1)
        self.debug_artifacts_checkbox = QCheckBox("Save debug artifacts on failure")
        self.debug_artifacts_checkbox.setChecked(False)
        self.window_width_spin = QSpinBox()
        self.window_width_spin.setRange(200, 4000)
        self.window_width_spin.setValue(800)
        self.window_height_spin = QSpinBox()
        self.window_height_spin.setRange(200, 4000)
        self.window_height_spin.setValue(600)
        self.window_scale_spin = QDoubleSpinBox()
        self.window_scale_spin.setRange(0.1, 1.0)
        self.window_scale_spin.setSingleStep(0.1)
        self.window_scale_spin.setValue(0.8)
        self.gpm_url_input = QLineEdit("http://127.0.0.1:19995")
        self.run_status_label = QLabel("Idle")
        self.run_status_label.setObjectName("StatusPill")
        self.run_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.run_status_label.setFixedSize(96, 48)
        self.start_button = QPushButton("Start Run")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self._start_run)
        self.stop_button = QPushButton("Stop Run")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.clicked.connect(self._stop_run)
        self.stop_button.setEnabled(False)
        self.select_failed_button = QPushButton("Chọn lại account lỗi")
        self.select_failed_button.clicked.connect(self._select_failed_accounts)
        self.select_failed_button.setEnabled(False)

        self.run_table = QTableWidget(0, 5)
        self.run_table.setObjectName("RunTable")
        self.run_table.setColumnCount(5)
        self.run_table.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.run_table.viewport().setObjectName("RunTableViewport")
        self.run_table.viewport().setAutoFillBackground(False)
        self.log_output = QTextEdit()
        self.log_output.setObjectName("LogOutput")
        self.log_output.setReadOnly(True)
        self.log_output.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.log_output.viewport().setObjectName("LogOutputViewport")
        self.log_output.viewport().setAutoFillBackground(False)
        self.history_table = QTableWidget(0, 8)

        self._build_ui()
        self._auto_register_tasks()
        self._refresh_tasks()
        self._refresh_history()
        self._load_groups_from_gpm_without_dialog()
        self._load_profiles_from_cache_without_dialog()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._drain_events)
        self.timer.start(200)

    def _build_ui(self) -> None:
        self._apply_design_system()
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 16, 18, 18)
        root_layout.setSpacing(14)
        root_layout.addWidget(self._header_widget())

        self.tabs = BackgroundTabWidget(self.base_dir / "background.jpg")
        self.tabs.setObjectName("MainTabs")
        self.tabs.addTab(self._tasks_tab(), "Scripts")
        self.tabs.addTab(self._profiles_tab(), "Profiles")
        self.tabs.addTab(self._run_tab(), "Run Setup")
        self.tabs.addTab(self._monitor_tab(), "Run Monitor")
        self.tabs.addTab(self._history_tab(), "Run History")
        self.tabs.addTab(self._settings_tab(), "Settings")
        self.tabs.setCurrentIndex(3)
        root_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

    def _header_widget(self) -> QWidget:
        header = QFrame()
        header.setObjectName("AppHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(18)

        left_balance = QWidget()
        left_balance.setObjectName("HeaderBalance")
        left_balance.setFixedSize(96, 48)

        brand_container = QWidget()
        brand_container.setObjectName("HeaderContent")
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(GeometricWolfLogo())
        title = GradientTitle("GPMSelenium")
        author = QLabel("by dangiaosu")
        author.setObjectName("BrandAuthor")
        title_row.addWidget(title)
        title_row.addWidget(author)
        subtitle = QLabel("AI-code automation runtime for GPMLogin profiles, Selenium scripts, Excel status, and run history.")
        subtitle.setObjectName("MutedText")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addLayout(title_row)
        brand_layout.addWidget(subtitle)
        brand_layout.addLayout(self._contact_icon_row())

        layout.addWidget(left_balance)
        layout.addWidget(brand_container, 1)
        layout.addWidget(self.run_status_label, alignment=Qt.AlignmentFlag.AlignTop)
        return header

    def _contact_icon_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(14)
        row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        contacts: list[tuple[str, str, str, bool]] = [
            ("Github", "https://github.com/dangiaosu", "github.png", False),
            ("Telegram Chat", "https://t.me/dangiaosu", "telegram.png", False),
            ("Telegram Channel", "https://t.me/dandoxin", "telegram.png", True),
            ("Facebook", "https://facebook.com/dangiaosu90", "facebook.png", False),
        ]
        for label_text, url, icon_name, show_channel_label in contacts:
            row.addWidget(self._contact_tile(label_text, url, icon_name, show_channel_label))
        return row

    def _contact_tile(self, label_text: str, url: str, icon_name: str, show_channel_label: bool) -> QWidget:
        tile = QWidget()
        tile.setObjectName("ContactTile")
        tile.setFixedSize(62, 62)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._contact_button(label_text, url, icon_name), alignment=Qt.AlignmentFlag.AlignHCenter)
        label = QLabel("C H A N N E L" if show_channel_label else "")
        label.setObjectName("ChannelLabel")
        label.setFixedHeight(14)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return tile

    def _contact_button(self, label_text: str, url: str, icon_name: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("ContactIconButton")
        button.setToolTip(f"{label_text}: {url}")
        button.setFixedSize(54, 44)
        button.setIcon(QIcon(str(self.base_dir / icon_name)))
        button.setIconSize(QSize(25, 25))
        button.clicked.connect(lambda _checked=False, active_url=url: QDesktopServices.openUrl(QUrl(active_url)))
        return button

    def _tasks_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("TransparentPage")
        layout = QHBoxLayout(container)
        layout.setSpacing(14)

        left_panel = QFrame()
        left_panel.setObjectName("TranslucentPanel")
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(12, 12, 12, 12)
        left.setSpacing(10)
        import_button = QPushButton("Load Script")
        import_button.setObjectName("PrimaryButton")
        import_button.clicked.connect(self._import_task)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_tasks)
        button_row = QHBoxLayout()
        button_row.addWidget(import_button)
        button_row.addWidget(refresh_button)
        left.addLayout(button_row)
        left.addWidget(self.task_list)
        self.task_list.currentItemChanged.connect(self._show_task_detail)

        detail_panel = QFrame()
        detail_panel.setObjectName("ScriptDetailPanel")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.addWidget(self.script_name_label, 1)
        title_row.addWidget(self.script_version_label)
        title_row.addWidget(self.script_success_label)
        detail_layout.addLayout(title_row)
        detail_layout.addWidget(self.script_description_label)
        detail_layout.addWidget(self._script_meta_block("Module path", self.script_module_label))
        detail_layout.addWidget(self._script_meta_block("Required Excel columns", self.script_columns_label))
        detail_layout.addStretch(1)

        layout.addWidget(left_panel, 1)
        layout.addWidget(detail_panel, 2)
        return container

    def _script_meta_block(self, title: str, value_label: QLabel) -> QWidget:
        block = QFrame()
        block.setObjectName("ScriptMetaBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("MutedText")
        layout.addWidget(title_label)
        value_label.setWordWrap(True)
        layout.addWidget(value_label)
        return block

    def _profiles_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("TransparentPage")
        layout = QVBoxLayout(container)
        layout.setSpacing(12)

        control_row = QHBoxLayout()
        load_cache_button = QPushButton("Load Session Cache")
        load_cache_button.clicked.connect(self._load_cached_profiles)
        refresh_button = QPushButton("Refresh From GPM")
        refresh_button.clicked.connect(self._refresh_profiles_from_gpm)
        reload_groups_button = QPushButton("Reload Groups")
        reload_groups_button.clicked.connect(self._refresh_groups_from_gpm)
        control_row.addWidget(QLabel("Search"))
        control_row.addWidget(self.profile_search_input, 1)
        control_row.addWidget(QLabel("Group"))
        control_row.addWidget(self.profile_group_combo)
        control_row.addWidget(reload_groups_button)
        control_row.addWidget(refresh_button)
        control_row.addWidget(load_cache_button)

        self.profile_table.setHorizontalHeaderLabels(
            ["Name", "ProfileID", "Group", "Browser", "Version", "Note", "Created"]
        )
        self.profile_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.profile_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.profile_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        layout.addLayout(control_row)
        layout.addWidget(self.profile_status_label)
        layout.addWidget(self.profile_table)
        return container

    def _run_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("TransparentPage")
        layout = QVBoxLayout(container)
        layout.setSpacing(14)

        file_row = QHBoxLayout()
        browse_button = QPushButton("Browse Excel")
        browse_button.clicked.connect(self._browse_excel)
        preview_button = QPushButton("Preview Pending Rows")
        preview_button.clicked.connect(self._preview_excel)
        file_row.addWidget(self.use_excel_checkbox)
        file_row.addWidget(self.excel_path_input, 1)
        file_row.addWidget(browse_button)
        file_row.addWidget(preview_button)

        config_group = QGroupBox("Run Config")
        form = QFormLayout(config_group)
        form.addRow("Workers", self.worker_spin)
        form.addRow("Retry count", self.retry_spin)
        form.addRow("Debug artifacts", self.debug_artifacts_checkbox)
        form.addRow("Node timeout seconds", self.node_timeout_spin)
        form.addRow("Page/result timeout seconds", self.timeout_spin)
        form.addRow("Window width", self.window_width_spin)
        form.addRow("Window height", self.window_height_spin)
        form.addRow("Window scale", self.window_scale_spin)

        action_row = QHBoxLayout()
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.stop_button)
        action_row.addStretch(1)

        layout.addLayout(file_row)
        layout.addWidget(self.preview_label)
        layout.addWidget(config_group)
        layout.addLayout(action_row)
        layout.addStretch(1)
        return container

    def _monitor_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("TransparentPage")
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        action_row = QHBoxLayout()
        action_row.addWidget(self.select_failed_button)
        action_row.addStretch(1)
        self.run_table.setHorizontalHeaderLabels(["Row", "Profile", "ProfileID", "Status", "Success"])
        table_panel = QFrame()
        table_panel.setObjectName("TranslucentPanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(8, 8, 8, 8)
        table_layout.addWidget(self.run_table)
        layout.addLayout(action_row)
        layout.addWidget(table_panel, 2)
        layout.addWidget(QLabel("Logs"))
        log_panel = QFrame()
        log_panel.setObjectName("TranslucentPanel")
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_layout.addWidget(self.log_output)
        layout.addWidget(log_panel, 1)
        return container

    def _history_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("TransparentPage")
        layout = QVBoxLayout(container)
        refresh_button = QPushButton("Refresh History")
        refresh_button.clicked.connect(self._refresh_history)
        self.history_table.setHorizontalHeaderLabels(
            ["Run ID", "Script", "Version", "Input", "Started", "Finished", "Status", "OK/Fail"]
        )
        layout.addWidget(refresh_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.history_table)
        return container

    def _settings_tab(self) -> QWidget:
        container = QWidget()
        container.setObjectName("TransparentPage")
        layout = QVBoxLayout(container)
        group = QGroupBox("GPM")
        form = QFormLayout(group)
        form.addRow("GPM base URL", self.gpm_url_input)
        layout.addWidget(group)
        layout.addStretch(1)
        return container

    def _apply_design_system(self) -> None:
        background_path: str = str(self.base_dir / "background.jpg").replace("\\", "/")
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #020617;
                color: #f8fafc;
                font-family: Arial;
                font-size: 13px;
            }
            #AppHeader, QGroupBox, QTextEdit, QListWidget, QTableWidget {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 14px;
            }
            #AppHeader {
                border: 1px solid #334155;
            }
            #HeaderContent, #HeaderBalance, #ContactTile {
                background: transparent;
                border: 0;
            }
            #TransparentPage {
                border-image: url("__BACKGROUND_PATH__") 0 0 0 0 stretch stretch;
                border: 0;
            }
            #TranslucentPanel {
                background: rgba(2, 6, 23, 34);
                border: 1px solid rgba(148, 163, 184, 58);
                border-radius: 15px;
            }
            #MutedText {
                color: #94a3b8;
            }
            #BrandAuthor {
                background: #052e16;
                border: 1px solid #166534;
                border-radius: 12px;
                color: #86efac;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 700;
            }
            #ContactIconButton {
                background: #111827;
                border: 1px solid #243143;
                border-radius: 13px;
                padding: 8px;
            }
            #ContactIconButton:hover {
                background: #182235;
                border-color: #22c55e;
            }
            #ChannelLabel {
                background: transparent;
                border: 0;
                color: #60a5fa;
                font-size: 8px;
                font-weight: 600;
            }
            #StatusPill {
                background: #111827;
                border: 1px solid #334155;
                border-radius: 16px;
                color: #e2e8f0;
                padding: 8px 14px;
                font-weight: 700;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                border-radius: 14px;
                top: -1px;
                border-image: url("__BACKGROUND_PATH__") 0 0 0 0 stretch stretch;
            }
            QTabBar::tab {
                background: transparent;
                color: #94a3b8;
                border: 0;
                border-bottom: 2px solid transparent;
                padding: 10px 18px 11px 18px;
                margin-right: 6px;
            }
            QTabBar::tab:selected {
                color: #f8fafc;
                border-bottom: 2px solid #22c55e;
            }
            QGroupBox {
                background: rgba(15, 23, 42, 92);
                border: 1px solid rgba(148, 163, 184, 54);
                margin-top: 12px;
                padding: 18px 14px 14px 14px;
                font-weight: 700;
                color: #e2e8f0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox {
                background: #020617;
                border: 1px solid #334155;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 32px;
                padding: 4px 10px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #22c55e;
            }
            QComboBox {
                background: #020617;
                border: 1px solid #334155;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 32px;
                padding: 4px 10px;
            }
            QComboBox:focus {
                border-color: #22c55e;
            }
            QComboBox::drop-down {
                border: 0;
                width: 26px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #94a3b8;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 10px;
                color: #f8fafc;
                selection-background-color: #14532d;
                selection-color: #f8fafc;
                padding: 4px;
            }
            QPushButton {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
                color: #f8fafc;
                min-height: 34px;
                padding: 6px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #26364d;
                border-color: #475569;
            }
            QPushButton:disabled {
                background: #0f172a;
                color: #64748b;
            }
            #PrimaryButton {
                background: #22c55e;
                border-color: #22c55e;
                color: #052e16;
            }
            #PrimaryButton:hover {
                background: #16a34a;
            }
            #ScriptDetailPanel {
                background: rgba(15, 23, 42, 132);
                border: 1px solid rgba(148, 163, 184, 62);
                border-radius: 18px;
            }
            #ScriptTitle {
                color: #f8fafc;
                font-size: 24px;
                font-weight: 800;
            }
            #ScriptBadge, #SuccessBadge {
                border-radius: 13px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 800;
            }
            #ScriptBadge {
                background: rgba(30, 41, 59, 180);
                border: 1px solid #475569;
                color: #cbd5e1;
            }
            #SuccessBadge {
                background: rgba(5, 46, 22, 210);
                border: 1px solid #22c55e;
                color: #bbf7d0;
            }
            #ScriptMetaBlock {
                background: rgba(2, 6, 23, 116);
                border: 1px solid rgba(51, 65, 85, 150);
                border-radius: 14px;
            }
            #ScriptMeta, #ScriptColumns {
                color: #e2e8f0;
                font-size: 13px;
            }
            #DangerButton {
                background: #7f1d1d;
                border-color: #ef4444;
                color: #fee2e2;
            }
            #DangerButton:hover {
                background: #991b1b;
            }
            QHeaderView::section {
                background: #111827;
                color: #cbd5e1;
                border: 0;
                border-bottom: 1px solid #334155;
                padding: 8px;
                font-weight: 700;
            }
            QTableWidget, QTextEdit {
                background: rgba(15, 23, 42, 46);
                border: 1px solid rgba(148, 163, 184, 54);
                border-radius: 14px;
                alternate-background-color: rgba(17, 24, 39, 60);
                selection-background-color: #14532d;
                selection-color: #f8fafc;
                padding: 6px;
            }
            #RunTableViewport, #LogOutputViewport {
                background: rgba(2, 6, 23, 34);
            }
            QListWidget {
                background: rgba(15, 23, 42, 170);
                border: 1px solid #1e293b;
                border-radius: 14px;
                alternate-background-color: #111827;
                selection-background-color: #14532d;
                selection-color: #f8fafc;
                padding: 6px;
            }
            QCheckBox {
                color: #e2e8f0;
                spacing: 8px;
            }
            QLabel {
                color: #f8fafc;
            }
            """.replace("__BACKGROUND_PATH__", background_path)
        )

    def _import_task(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(self, "Select automation script", str(self.base_dir), "Python (*.py)")
        if selected_path == "":
            return
        source = Path(selected_path)
        target = self.tasks_dir / source.name
        shutil.copy2(source, target)
        try:
            task = load_task(target)
            self.store.register_task(task.name, task.version, task.module_path, task.description, task.required_columns)
        except Exception as error:
            QMessageBox.critical(self, "Script load failed", str(error))
            return
        self._refresh_tasks()

    def _refresh_tasks(self) -> None:
        self.task_list.clear()
        for task in self.store.list_tasks():
            item = QListWidgetItem(f"{task.name} v{task.version}")
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.task_list.addItem(item)
        if self.task_list.count() > 0:
            self.task_list.setCurrentRow(0)

    def _auto_register_tasks(self) -> None:
        for module_path in self.tasks_dir.glob("*.py"):
            try:
                task = load_task(module_path)
                self.store.register_task(task.name, task.version, task.module_path, task.description, task.required_columns)
            except Exception:
                continue

    def _show_task_detail(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self.script_name_label.setText("No script selected")
            self.script_version_label.setText("-")
            self.script_success_label.setText("SUCCESS")
            self.script_module_label.setText("-")
            self.script_columns_label.setText("-")
            self.script_description_label.setText("Load or select a script to inspect its contract.")
            return
        task_id = int(current.data(Qt.ItemDataRole.UserRole))
        registered = self.store.get_task(task_id)
        loaded = load_task(Path(registered.module_path))
        self.script_name_label.setText(registered.name)
        self.script_version_label.setText(f"v{registered.version}")
        self.script_success_label.setText(loaded.success_status)
        self.script_module_label.setText(registered.module_path)
        self.script_columns_label.setText(", ".join(registered.required_columns))
        description: str = registered.description.strip()
        self.script_description_label.setText(description if description != "" else "No script description provided.")

    def _browse_excel(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(self, "Select Excel file", str(self.base_dir), "Excel (*.xlsx *.xlsm)")
        if selected_path != "":
            self.excel_path_input.setText(selected_path)
            self.use_excel_checkbox.setChecked(True)

    def _preview_excel(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.warning(self, "Missing script", "Select or load a script first.")
            return
        try:
            selected_profiles = self._selected_profiles()
            excel_path = self._optional_excel_path()
            if len(selected_profiles) > 0:
                preview = preview_rows_from_profiles(selected_profiles, task.required_columns, excel_path)
                self.preview_label.setText(
                    f"Selected profiles: {preview.selected_profiles} | "
                    f"Matched Excel rows: {preview.matched_excel_rows} | "
                    f"Pending: {preview.pending_rows} | Skipped success: {preview.skipped_rows} | "
                    f"Missing data columns: {preview.missing_data_columns}"
                )
                return
            if excel_path is None:
                QMessageBox.warning(self, "Missing input", "Select profiles or enable Excel input.")
                return
            excel_preview = preview_excel(excel_path, task.required_columns)
        except Exception as error:
            QMessageBox.critical(self, "Preview failed", str(error))
            return
        self.preview_label.setText(
            f"Total: {excel_preview.total_rows} | Pending: {excel_preview.pending_rows} | "
            f"Skipped success: {excel_preview.skipped_rows} | Error rows: {excel_preview.error_rows} | "
            f"Missing columns: {excel_preview.missing_columns}"
        )

    def _start_run(self) -> None:
        if self.worker_thread is not None and self.worker_thread.is_alive():
            QMessageBox.warning(self, "Run active", "A run is already active.")
            return
        task = self._selected_task()
        if task is None:
            QMessageBox.warning(self, "Missing script", "Select or load a script first.")
            return

        config = self._runtime_config()
        self.run_table.setRowCount(0)
        self.log_output.clear()
        selected_profiles = self._selected_profiles()
        excel_path = self._optional_excel_path()
        if len(selected_profiles) == 0 and excel_path is None:
            QMessageBox.warning(self, "Missing input", "Select profiles or enable Excel input with a valid file.")
            return
        if len(selected_profiles) > 0:
            try:
                self._validate_selected_profiles_available(selected_profiles)
            except Exception as error:
                QMessageBox.critical(self, "Profile list changed", str(error))
                return
        task_config = self._task_config()
        self.stop_event = Event()
        self.failed_profile_ids.clear()
        self.select_failed_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.run_status_label.setText("Running")
        self.worker_thread = threading.Thread(
            target=self._run_in_thread,
            args=(task, selected_profiles, excel_path, config, task_config, self.stop_event),
            daemon=True,
        )
        self.worker_thread.start()

    def _stop_run(self) -> None:
        if self.worker_thread is None or not self.worker_thread.is_alive():
            return
        self.stop_event.set()
        self.stop_button.setEnabled(False)
        self.run_status_label.setText("Stopping")
        self.log_output.append("stop_requested: active profiles will finish normally; new profiles will not start")

    def _run_in_thread(
        self,
        task: LoadedTask,
        selected_profiles: list[GpmProfile],
        excel_path: Path | None,
        config: RuntimeConfig,
        task_config: dict[str, Any],
        stop_event: Event,
    ) -> None:
        try:
            task_id = self._task_id(task)
            if len(selected_profiles) > 0:
                rows = build_rows_from_profiles(selected_profiles, task.required_columns, excel_path)
                source_label = str(excel_path) if excel_path is not None else "Selected GPM profiles"
                run_selected_profiles_batch(
                    self.store,
                    task_id,
                    task,
                    source_label,
                    rows,
                    excel_path,
                    config,
                    task_config,
                    self._queue_event,
                    stop_event,
                )
            elif excel_path is not None:
                run_task_batch(self.store, task_id, task, excel_path, config, task_config, self._queue_event, stop_event)
            else:
                raise ValueError("No profiles or Excel input selected.")
        except Exception as error:
            self._queue_event("run_error", {"error": str(error)})

    def _queue_event(self, event_name: str, payload: dict[str, Any]) -> None:
        self.event_queue.put((event_name, payload))

    def _drain_events(self) -> None:
        while True:
            try:
                event_name, payload = self.event_queue.get_nowait()
            except Empty:
                break
            self._handle_event(event_name, payload)

    def _handle_event(self, event_name: str, payload: dict[str, Any]) -> None:
        self.log_output.append(f"{event_name}: {payload}")
        if event_name == "profile_started":
            profile_id = str(payload.get("profile_id", "")).strip()
            if profile_id != "":
                self.active_profile_ids.add(profile_id)
        if event_name == "profile_finished":
            profile_id = str(payload.get("profile_id", "")).strip()
            if profile_id != "":
                self.active_profile_ids.discard(profile_id)
        if event_name == "row_retry":
            self.run_status_label.setText("Retrying")
        if event_name == "row_finished":
            profile_id = str(payload.get("profile_id", "")).strip()
            success = bool(payload.get("success", False))
            if profile_id != "" and not success:
                self.failed_profile_ids.add(profile_id)
                self.select_failed_button.setEnabled(True)
            if profile_id != "" and success:
                self.failed_profile_ids.discard(profile_id)
                self.select_failed_button.setEnabled(len(self.failed_profile_ids) > 0)
            row_index = self.run_table.rowCount()
            self.run_table.insertRow(row_index)
            values = [
                str(payload.get("row_number", "")),
                str(payload.get("profile_name", "")),
                str(payload.get("profile_id", "")),
                str(payload.get("status", "")),
                str(payload.get("success", "")),
            ]
            for column, value in enumerate(values):
                self.run_table.setItem(row_index, column, QTableWidgetItem(value))
        if event_name in {"run_finished", "run_error"}:
            self.active_profile_ids.clear()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.run_status_label.setText(str(payload.get("status", "Idle")) if event_name == "run_finished" else "Error")
            self._refresh_history()

    def _refresh_history(self) -> None:
        runs = self.store.list_runs()
        self.history_table.setRowCount(0)
        for run in runs:
            row_index = self.history_table.rowCount()
            self.history_table.insertRow(row_index)
            values = [
                str(run.get("id", "")),
                str(run.get("task_name", "")),
                str(run.get("version", "")),
                str(run.get("excel_path", "")),
                str(run.get("started_at", "")),
                str(run.get("finished_at", "")),
                str(run.get("status", "")),
                f"{run.get('success_count', 0)}/{run.get('failure_count', 0)}",
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row_index, column, QTableWidgetItem(value))

    def _selected_task(self) -> LoadedTask | None:
        current = self.task_list.currentItem()
        if current is None:
            return None
        task_id = int(current.data(Qt.ItemDataRole.UserRole))
        registered = self.store.get_task(task_id)
        return load_task(Path(registered.module_path))

    def _task_id(self, task: LoadedTask) -> int:
        current = self.task_list.currentItem()
        if current is not None:
            return int(current.data(Qt.ItemDataRole.UserRole))
        return self.store.register_task(task.name, task.version, task.module_path, task.description, task.required_columns)

    def _runtime_config(self) -> RuntimeConfig:
        config = default_runtime_config()
        return replace(
            config,
            gpm_base_url=self.gpm_url_input.text().strip(),
            max_workers=int(self.worker_spin.value()),
            page_timeout_seconds=float(self.timeout_spin.value()),
            node_timeout_seconds=float(self.node_timeout_spin.value()),
            window_width=int(self.window_width_spin.value()),
            window_height=int(self.window_height_spin.value()),
            window_scale=float(self.window_scale_spin.value()),
            retry_count=int(self.retry_spin.value()),
        )

    def _task_config(self) -> dict[str, Any]:
        return {"enable_debug_artifacts": self.debug_artifacts_checkbox.isChecked()}

    def _optional_excel_path(self) -> Path | None:
        if not self.use_excel_checkbox.isChecked():
            return None
        raw_path: str = self.excel_path_input.text().strip()
        if raw_path == "":
            return None
        excel_path = Path(raw_path)
        if not excel_path.exists():
            raise ValueError(f"Excel file does not exist; excel_path={excel_path}")
        return excel_path

    def _refresh_profiles_from_gpm(self) -> None:
        try:
            profiles = self._load_current_gpm_profiles(
                self.profile_search_input.text().strip(),
                self._selected_group_id(),
            )
            save_profiles(self.profile_cache_path, profiles)
            self._show_profiles(profiles, "GPM API")
        except Exception as error:
            QMessageBox.critical(self, "Profile refresh failed", str(error))

    def _refresh_groups_from_gpm(self) -> None:
        try:
            groups = self._load_current_gpm_groups()
            self._show_groups(groups)
        except Exception as error:
            QMessageBox.critical(self, "Group refresh failed", str(error))

    def _load_groups_from_gpm_without_dialog(self) -> None:
        try:
            groups = self._load_current_gpm_groups()
        except Exception:
            self._show_groups([])
            return
        self._show_groups(groups)

    def _load_cached_profiles(self) -> None:
        try:
            profiles = load_profiles(self.profile_cache_path)
            self._show_profiles(profiles, "session cache")
        except Exception as error:
            QMessageBox.critical(self, "Profile cache failed", str(error))

    def _load_profiles_from_cache_without_dialog(self) -> None:
        try:
            profiles = load_profiles(self.profile_cache_path)
        except Exception:
            return
        if len(profiles) > 0:
            self._show_profiles(profiles, "session cache")

    def _show_profiles(self, profiles: list[GpmProfile], source_name: str) -> None:
        self.profiles = profiles
        self.profile_by_id = {profile.profile_id: profile for profile in profiles}
        self.profile_table.setRowCount(0)
        for profile in profiles:
            row_index = self.profile_table.rowCount()
            self.profile_table.insertRow(row_index)
            values = [
                profile.name,
                profile.profile_id,
                profile.group_id,
                profile.browser_type,
                profile.browser_version,
                profile.note,
                profile.created_at,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
                self.profile_table.setItem(row_index, column, item)
        self.profile_status_label.setText(
            f"Loaded {len(profiles)} profiles from {source_name}. Use Shift/Ctrl + mouse to select multiple rows."
        )

    def _selected_profiles(self) -> list[GpmProfile]:
        selected_rows: list[int] = sorted({index.row() for index in self.profile_table.selectedIndexes()})
        profiles: list[GpmProfile] = []
        for row_index in selected_rows:
            profile_id_item = self.profile_table.item(row_index, 1)
            if profile_id_item is None:
                continue
            profile_id = profile_id_item.text().strip()
            profile = self.profile_by_id.get(profile_id)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def _select_failed_accounts(self) -> None:
        if len(self.failed_profile_ids) == 0:
            QMessageBox.information(self, "No failed accounts", "Không có account lỗi trong lần chạy hiện tại.")
            return
        self.profile_table.clearSelection()
        selection_model = self.profile_table.selectionModel()
        selected_count: int = 0
        for row_index in range(self.profile_table.rowCount()):
            profile_id_item = self.profile_table.item(row_index, 1)
            if profile_id_item is None:
                continue
            profile_id = profile_id_item.text().strip()
            if profile_id not in self.failed_profile_ids:
                continue
            index = self.profile_table.model().index(row_index, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
            )
            selected_count += 1
        if selected_count == 0:
            QMessageBox.warning(
                self,
                "Failed accounts not visible",
                "Không tìm thấy account lỗi trong bảng Profiles hiện tại. Hãy Refresh From GPM hoặc Load Session Cache rồi chọn lại.",
            )
            return
        if self.tabs is not None:
            self.tabs.setCurrentIndex(1)
        self.profile_status_label.setText(f"Selected {selected_count} failed profiles from the last run.")

    def _load_current_gpm_profiles(self, search: str, group_id: str | None) -> list[GpmProfile]:
        session = requests.Session()
        client = GpmClient(self.gpm_url_input.text().strip(), session, 30.0, 3)
        return client.list_profiles(1, 500, search, 2, group_id)

    def _load_current_gpm_groups(self) -> list[GpmGroup]:
        session = requests.Session()
        client = GpmClient(self.gpm_url_input.text().strip(), session, 30.0, 3)
        return client.list_groups()

    def _show_groups(self, groups: list[GpmGroup]) -> None:
        current_group_id: str | None = self._selected_group_id()
        self.groups = groups
        self.profile_group_combo.blockSignals(True)
        self.profile_group_combo.clear()
        self.profile_group_combo.addItem("All groups", "")
        for group in groups:
            self.profile_group_combo.addItem(group.name, group.group_id)
        if current_group_id is not None:
            index: int = self.profile_group_combo.findData(current_group_id)
            if index >= 0:
                self.profile_group_combo.setCurrentIndex(index)
        self.profile_group_combo.blockSignals(False)

    def _selected_group_id(self) -> str | None:
        raw_group_id: Any = self.profile_group_combo.currentData()
        if raw_group_id is None:
            return None
        group_id: str = str(raw_group_id).strip()
        return group_id if group_id != "" else None

    def _validate_selected_profiles_available(self, selected_profiles: list[GpmProfile]) -> None:
        current_profiles: list[GpmProfile] = self._load_current_gpm_profiles("", self._selected_group_id())
        current_profile_ids: set[str] = {profile.profile_id for profile in current_profiles}
        missing_profiles: list[GpmProfile] = [
            profile for profile in selected_profiles if profile.profile_id not in current_profile_ids
        ]
        if len(missing_profiles) == 0:
            return
        missing_names: str = ", ".join(
            f"{profile.name} ({profile.profile_id})" for profile in missing_profiles[:10]
        )
        raise ValueError(
            "Selected profiles are not present in the current GPM profile list. "
            "GPM folder may have changed. Refresh Profiles, select again, then run. "
            f"Missing profiles: {missing_names}"
        )


def main() -> NoReturn:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
