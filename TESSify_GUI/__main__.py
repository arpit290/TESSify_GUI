"""PySide6 desktop interface for the existing TESSify package.

Run from the repository parent with ``python -m TESSify_GUI``. Scientific
processing and project persistence come from the installed ``TESSify.Project``.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QRectF, QSettings, QSize, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QProgressBar,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

# Import the engine from the separately installed TESSify package. There is intentionally no mock/fake
# fallback: fabricated graphs or results would be dangerous for scientific use.
_ENGINE_IMPORT_ERROR: Optional[Exception] = None
try:
    from TESSify import GRAPHS_DIR, KIND_DIRS, Project as TESSifyProject, tic_id
    _ENGINE_IMPORT_ERROR = None
except Exception as import_error:  # report the real issue when the UI starts
    TESSifyProject = None  # type: ignore[assignment,misc]
    GRAPHS_DIR = "Graphs"
    KIND_DIRS = {"lc": "LightCurves", "tp": "TargetPixels"}
    tic_id = lambda _name: None  # type: ignore[assignment]
    _ENGINE_IMPORT_ERROR = import_error

APP_ORG = "TESSify"
APP_NAME = "TESSify Desktop"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg"}
PROJECT_NAME_PATTERN = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")

# Logo path: shipped alongside this module.
_LOGO_PATH = str(Path(__file__).with_name("tessify-wordmark.svg"))

# Aperture-mask choices exposed to the GUI; matches lightkurve's accepted values.
APERTURE_MASK_CHOICES = ["all", "pipeline", "threshold"]

# Hover explanations. The wording comes from the README so the GUI and the docs agree.
# Lines are wrapped for display by tooltip_text(); "\n" starts a new line.
TOOLTIPS = {
    # Projects
    "project_create": (
        "Makes a new folder with the project name you enter. "
        "TESSify refuses to overwrite a project that already exists."
    ),
    "project_open": (
        "Restores an existing project folder (it must contain a config.json). "
        "Every stage is resumable, so you pick up where you left off."
    ),
    "project_name": (
        "Name of the new project folder. A folder with this name must not already exist; "
        "if it does, open it as a project instead or pick a new name."
    ),
    "project_parent": "The folder in which the new project folder is created.",

    # Download Data
    "data_type": (
        "• lc: light curve files.\n"
        "• tp: target pixel files. A light curve is built from their pixels using the "
        "aperture mask (see Process Files).\n"
        "A project holds one file type. To work with both, create two projects."
    ),
    "bulk_script": (
        "A bulk download script from the official TESS archive "
        "(archive.stsci.edu/tess/bulk_downloads/bulk_downloads_ffi-tp-lc-dv.html). "
        "Download the script for the file type you want (lc or tp), then choose it here."
    ),
    "download_amount": (
        "How many files to download from the script.\n"
        "Downloading again continues where it stopped: files that are already downloaded "
        "are skipped, and files that failed are retried. To fetch more files from the "
        "same script, download again with a larger amount."
    ),
    "download_workers": "How many files are downloaded at the same time (default is 4).",
    "check_curl": (
        "curl must be available on your PATH. It is used to run the bulk download scripts. "
        "It ships with Windows 10+, macOS, and most Linux distributions."
    ),
    "start_download": (
        "Downloads the files using the settings above. Resumable: running it again "
        "continues where it stopped. Failed downloads are recorded and retried on the "
        "next run instead of crashing the batch."
    ),

    # Process Files
    "process_amount": (
        "How many files to process. It can't usefully exceed the number of files you have "
        "downloaded.\n"
        "Processing cleans each file (removes NaNs, flattens the curve) and saves a plot "
        "of it in the project's Graphs folder. Files that already have a plot are skipped."
    ),
    "process_workers": (
        "How many CPU cores to use (default is 1). Each worker also loads its own copy of "
        "the data, so keep this modest if you are short on memory."
    ),
    "window_length": (
        "Size, in data points, of the smoothing window flatten() uses to remove slow "
        "brightness drift. Must be an odd integer of 3 or more (default is 101).\n"
        "The filter smooths away anything shorter than its window, and a transit is a "
        "short dip. At 101 points (about 3.4 hours for 2-minute data), a long transit can "
        "be partly flattened away. Use a window several times longer than the transits "
        "you are looking for, for example 401 or 1001 for 2-minute data.\n"
        "If the window is too large, slow stellar variability stays in the curve; if it "
        "is too small, real dips get erased. Longer cadences (10 or 30 minutes) need "
        "fewer points to cover the same time span.\n"
        "Applies to lc and tp files. Changing it only affects files processed afterwards."
    ),
    "aperture_mask": (
        "Which pixels are added together to build a light curve from a target pixel file. "
        "Used for tp files only; ignored for lc files.\n"
        "• all (default): adds up every pixel in the cutout, including faint, noisy ones.\n"
        "• pipeline: the pixels chosen by the TESS mission pipeline, usually cleaner.\n"
        "• threshold: only pixels above a brightness threshold.\n"
        "If your target pixel plots look noisy, try pipeline. "
        "Changing it only affects files processed afterwards."
    ),
    "aperture_all": "Adds up every pixel in the cutout, including faint, noisy ones (default).",
    "aperture_pipeline": (
        "The pixels chosen by the TESS mission pipeline, usually cleaner. "
        "Try this if your target pixel plots look noisy."
    ),
    "aperture_threshold": "Only pixels above a brightness threshold.",
    "start_processing": (
        "Cleans each downloaded file (removes NaNs, flattens the curve) and saves a plot "
        "of it in the project's Graphs folder.\n"
        "Files that can't be read (for example, a corrupt download) are skipped, reported, "
        "and listed under process_failed in config.json. Processing again retries them."
    ),

    # Candidate Review
    "review_prev": "Go to the previous graph (Left arrow).",
    "review_next": "Go to the next graph (Right arrow).",
    "review_shortlist": (
        "Shortlist the current graph if you see something of interest, such as a dip that "
        "could indicate an exoplanet (Down arrow). Your shortlist is saved as you go."
    ),
    "review_unshortlist": "Remove the current graph from the shortlist (Up arrow).",
    "review_save": (
        "Saves your shortlist and your position. The next review starts after the last "
        "graph you reached."
    ),
    "review_exit": (
        "Save and exit the review (Escape). The next review starts after the last graph "
        "you reached."
    ),

    # Results & Export
    "export_results": (
        "Saves the shortlisted TIC IDs as a JSON file. The IDs are unique and in the order "
        "you shortlisted them. Any path works."
    ),
}


class ProjectWrapper:
    """Thin GUI adapter around the real, instance-based ``Project`` API."""

    def __init__(self, project_path: str | Path, engine_project: Any):
        self.project_path = str(Path(project_path).expanduser().resolve())
        self.name = Path(self.project_path).name
        self.tessify_proj = engine_project

    @classmethod
    def create(cls, parent_dir: str, name: str) -> "ProjectWrapper":
        if TESSifyProject is None:
            raise RuntimeError(f"The TESSify engine could not be imported: {_ENGINE_IMPORT_ERROR}")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Enter a project name.")
        if clean_name in {".", ".."} or PROJECT_NAME_PATTERN.search(clean_name):
            raise ValueError("The project name contains characters that are invalid in folder names.")
        if clean_name.endswith((" ", ".")):
            raise ValueError("Project names cannot end in a space or period.")

        parent = Path(parent_dir).expanduser().resolve()
        if not parent.is_dir():
            raise NotADirectoryError(f"Parent folder does not exist: {parent}")
        target = parent / clean_name
        if target.exists():
            raise FileExistsError(
                f"The project path already exists:\n{target}\n\nChoose another name or open the existing project."
            )

        project = TESSifyProject()
        project.create(str(target))
        return cls(target, project)

    @classmethod
    def restore(cls, project_path: str) -> "ProjectWrapper":
        if TESSifyProject is None:
            raise RuntimeError(f"The TESSify engine could not be imported: {_ENGINE_IMPORT_ERROR}")
        root = Path(project_path).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Project directory not found: {root}")
        project = TESSifyProject()
        # Let the actual package validate config.json and propagate its error.
        project.restore(str(root))
        return cls(root, project)

    @property
    def state(self):
        state = self.tessify_proj.state
        if state is None:
            raise RuntimeError("No project state is loaded.")
        return state

    def get_graphs_dir(self) -> str:
        return str(Path(self.project_path) / GRAPHS_DIR)

    def get_data_dir(self) -> str:
        kind = self.state.kind
        if kind in KIND_DIRS:
            return str(Path(self.project_path) / KIND_DIRS[kind])
        return self.project_path

    def get_graphs(self) -> list[str]:
        # Use TESSify's recorded processing order rather than guessing IDs or
        # inventing candidates from arbitrary files in the directory.
        return self.tessify_proj.get_review_images()

    def get_downloaded_files(self) -> list[str]:
        kind = self.state.kind
        if kind not in KIND_DIRS:
            return []
        data_dir = Path(self.project_path) / KIND_DIRS[kind]
        return [
            name for name in self.state.downloaded
            if Path(name).name == name and (data_dir / name).is_file()
        ]

    def get_download_count(self) -> int:
        return len(self.state.downloaded)

    def load_review_state(self) -> dict[str, Any]:
        return {
            "shortlist": list(self.state.marked),
            "last_index": int(getattr(self.state, "review_index", 0) or 0),
        }

    def save_review_state(self, state: dict[str, Any]) -> None:
        self.tessify_proj.set_review_state(
            marked=state.get("shortlist"),
            review_index=state.get("last_index"),
        )

    def get_results(self) -> list[str]:
        # Preserve the package contract: unique TIC IDs in shortlist order.
        return self.tessify_proj.getresults()

    def save_results(self, output_path: str) -> None:
        self.tessify_proj.saveresults(output_path)

    def refresh_state(self) -> None:
        """No-op kept as an explicit hook for pages after a background job."""
        # The same Project instance is updated by the engine; no second config
        # read is needed (and reloading could race with a still-running job).


class PipelineWorker(QThread):
    """Run one engine operation off the UI thread and report real progress."""

    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    result_signal = Signal(bool, str)

    def __init__(self, project: ProjectWrapper, operation: str, **kwargs: Any):
        super().__init__()
        self.project = project
        self.operation = operation
        self.kwargs = kwargs
        self.failed_items = 0

    def _progress(self, finished: int, total: int, item: str, error: Exception | None) -> None:
        self.progress_signal.emit(finished, total)
        if not item:
            return
        if error is not None:
            self.failed_items += 1
            self.log_signal.emit(f"{finished}/{total}  FAILED  {item}: {error}")
        else:
            self.log_signal.emit(f"{finished}/{total}  OK      {item}")

    def run(self) -> None:
        try:
            if self.operation == "download":
                kind = self.kwargs["kind"]
                self.log_signal.emit(
                    f"Starting {kind} download: up to {self.kwargs['amount']} files; "
                    f"{self.kwargs['workers']} worker(s)."
                )
                self.project.tessify_proj.download(
                    kind=kind,
                    script_path=self.kwargs["script_path"],
                    amount=self.kwargs["amount"],
                    workers=self.kwargs["workers"],
                    progress_callback=self._progress,
                )
                message = f"Download stage finished. {self.failed_items} download(s) failed." if self.failed_items else "Download stage finished successfully."
            elif self.operation == "process":
                self.log_signal.emit(
                    f"Processing up to {self.kwargs['amount']} files with "
                    f"{self.kwargs['workers']} worker(s)."
                )
                wl = self.kwargs.get("window_length", 101)
                am = self.kwargs.get("aperture_mask", "all")
                self.log_signal.emit(
                    f"  window_length={wl}  aperture_mask={am}"
                )
                self.project.tessify_proj.process(
                    amount=self.kwargs["amount"],
                    workers=self.kwargs["workers"],
                    window_length=wl,
                    aperture_mask=am,
                    progress_callback=self._progress,
                )
                message = f"Processing stage finished. {self.failed_items} file(s) failed." if self.failed_items else "Processing stage finished successfully."
            else:
                raise ValueError(f"Unknown pipeline operation: {self.operation}")
            self.log_signal.emit(message)
            self.result_signal.emit(True, message)
        except Exception as error:
            message = str(error)
            self.log_signal.emit(f"ERROR: {message}")
            self.result_signal.emit(False, message)


# ---- Reusable UI helpers ---------------------------------------------------
def page_title(title: str, subtitle: str | None = None) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 8)
    heading = QLabel(title)
    heading.setObjectName("PageTitle")
    heading.setFont(QFont("Segoe UI", 19, QFont.Bold))
    layout.addWidget(heading)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return widget


def make_log() -> QTextEdit:
    log = QTextEdit()
    log.setReadOnly(True)
    log.document().setMaximumBlockCount(1200)
    log.setPlaceholderText("Job messages will appear here.")
    log.setObjectName("JobLog")
    return log


def add_log_line(log: QTextEdit, text: str) -> None:
    log.append(text)


def open_local_path(path: str | Path) -> bool:
    local = Path(path)
    if not local.exists():
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(local.resolve())))


def tooltip_text(text: str, width: int = 64) -> str:
    """Wrap tooltip text, since Qt does not wrap plain-text tooltips by itself."""
    lines = []
    for line in text.split("\n"):
        indent = "   " if line.startswith("• ") else ""
        lines.append(textwrap.fill(line, width=width, subsequent_indent=indent))
    return "\n".join(lines)


def set_tooltip(key: str, *widgets: QWidget | None) -> None:
    """Show the TOOLTIPS[key] explanation when hovering any of the given widgets."""
    text = tooltip_text(TOOLTIPS[key])
    for widget in widgets:
        if widget is not None:  # e.g. labelForField() can return None
            widget.setToolTip(text)


class SvgLogoLabel(QLabel):
    """Draws an SVG logo as vectors, so it stays sharp at any size or screen density.

    A pixmap is fixed at the resolution it was made at and turns soft when scaled
    or shown on a high-DPI screen. Painting the SVG directly re-renders it at the
    screen's real pixel size every time. The stylesheet (background, rounded
    corners, padding) still applies because this is a QLabel.
    """

    def __init__(self, svg_path: str, max_size: QSize, parent: QWidget | None = None):
        super().__init__(parent)
        self._renderer = QSvgRenderer(svg_path, self)
        self._max_size = max_size
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _fit(self, box: QSize) -> QSize:
        natural = self._renderer.defaultSize()
        if not self._renderer.isValid() or natural.isEmpty():
            return QSize(0, 0)
        return natural.scaled(box, Qt.KeepAspectRatio)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt method name
        self.ensurePolished()
        margins = self.contentsMargins()  # stylesheet margin/border/padding
        logo = self._fit(self._max_size)
        return QSize(
            logo.width() + margins.left() + margins.right(),
            logo.height() + margins.top() + margins.bottom(),
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt event name
        super().paintEvent(event)  # draws the stylesheet background and border
        if not self._renderer.isValid():
            return
        area = self.contentsRect()
        logo = self._fit(area.size())
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform
        )
        self._renderer.render(painter, QRectF(
            area.x() + (area.width() - logo.width()) / 2,
            area.y() + (area.height() - logo.height()) / 2,
            logo.width(), logo.height(),
        ))
        painter.end()


class HomePage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 30)
        layout.addWidget(page_title(
            "Welcome to TESSify",
            "Find and review possible transit-like dips in NASA TESS observations. Analysis runs locally on your computer.",
        ))
        layout.addSpacing(20)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        create = QGroupBox("CREATE A NEW PROJECT")
        create_layout = QVBoxLayout(create)
        create_desc = QLabel("Start a clean workspace for TESS data, generated graphs, and candidate decisions.")
        create_desc.setWordWrap(True)
        create_button = QPushButton("Create Project…")
        create_button.setObjectName("PrimaryButton")
        create_button.clicked.connect(self.main_win.show_create_project_dialog)
        set_tooltip("project_create", create_button)
        create_layout.addWidget(create_desc)
        create_layout.addStretch(1)
        create_layout.addWidget(create_button)

        resume = QGroupBox("OPEN / RESUME A PROJECT")
        resume_layout = QVBoxLayout(resume)
        resume_desc = QLabel("Continue a project saved by TESSify. Downloads, processing state, and shortlist decisions remain resumable.")
        resume_desc.setWordWrap(True)
        open_button = QPushButton("Choose Project Folder…")
        open_button.clicked.connect(self.main_win.open_project_folder)
        set_tooltip("project_open", open_button)
        resume_layout.addWidget(resume_desc)
        resume_layout.addStretch(1)
        resume_layout.addWidget(open_button)
        cards.addWidget(create)
        cards.addWidget(resume)
        layout.addLayout(cards)
        layout.addSpacing(28)

        workflow = QGroupBox("WORKFLOW")
        workflow_layout = QHBoxLayout(workflow)
        workflow_text = QLabel("Project  →  Download data  →  Process FITS files  →  Review graphs  →  Export TIC IDs")
        workflow_text.setWordWrap(True)
        workflow_layout.addWidget(workflow_text)
        layout.addWidget(workflow)
        layout.addStretch(1)


class ProjectOverviewPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 24)
        layout.addWidget(page_title("Project Overview", "Resume any stage of your current TESSify analysis."))

        header = QHBoxLayout()
        self.lbl_name = QLabel("No project open")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.lbl_path = QLabel("Open or create a project to see its details.")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        folder_button = QPushButton("Open Project Folder")
        folder_button.clicked.connect(self.open_project_folder)
        labels = QVBoxLayout()
        labels.addWidget(self.lbl_name)
        labels.addWidget(self.lbl_path)
        header.addLayout(labels, 1)
        header.addWidget(folder_button)
        layout.addLayout(header)
        layout.addSpacing(20)

        actions = QHBoxLayout()
        for text, target in (("Download Data", 2), ("Process Files", 3), ("Candidate Review", 4), ("Results & Export", 5)):
            button = QPushButton(text)
            button.setMinimumHeight(54)
            button.clicked.connect(lambda _checked=False, idx=target: self.main_win.navigate_to(idx))
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addSpacing(18)

        stats = QGroupBox("Project State")
        stats_layout = QVBoxLayout(stats)
        self.lbl_stats = QLabel("No project open.")
        self.lbl_stats.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_stats.setWordWrap(True)
        stats_layout.addWidget(self.lbl_stats)
        layout.addWidget(stats)
        layout.addStretch(1)

    def update_project_info(self, project: ProjectWrapper | None) -> None:
        if project is None:
            self.lbl_name.setText("No project open")
            self.lbl_path.setText("Open or create a project to see its details.")
            self.lbl_stats.setText("No project data to display.")
            return
        self.lbl_name.setText(project.name)
        self.lbl_path.setText(project.project_path)
        state = project.state
        kind_name = {"lc": "Light Curve", "tp": "Target Pixel"}.get(state.kind, "Not selected yet")
        downloads = len(project.get_downloaded_files())
        graphs = len(project.get_graphs())
        results = len(project.get_results())
        failed_downloads = len(state.download_failed)
        failed_processing = len(state.process_failed)
        self.lbl_stats.setText(
            f"Data type: {kind_name}\n"
            f"Download successes recorded: {len(state.downloaded)}  |  Existing input files: {downloads}\n"
            f"Graphs available for review: {graphs}  |  Unique shortlisted TIC IDs: {results}\n"
            f"Recorded download failures: {failed_downloads}  |  Recorded processing failures: {failed_processing}"
        )

    def open_project_folder(self) -> None:
        project = self.main_win.current_project
        if project and not open_local_path(project.project_path):
            QMessageBox.warning(self, "Folder unavailable", "The project folder could not be opened.")


class DownloadPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        self.worker: PipelineWorker | None = None
        self._outcome: tuple[bool, str] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.addWidget(page_title(
            "Download TESS Data",
            "Use a bulk-download script from the TESS archive. A project can contain one file type; use a separate project for the other type.",
        ))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.rb_lc = QRadioButton("Light Curve files (lc)")
        self.rb_tp = QRadioButton("Target Pixel files (tp)")
        self.rb_lc.setChecked(True)
        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.rb_lc)
        self.type_group.addButton(self.rb_tp)
        type_layout = QHBoxLayout()
        type_layout.addWidget(self.rb_lc)
        type_layout.addWidget(self.rb_tp)
        type_layout.addStretch(1)
        form.addRow("Data type", type_layout)
        set_tooltip("data_type", self.rb_lc, self.rb_tp, form.labelForField(type_layout))

        script_row = QHBoxLayout()
        self.txt_script = QLineEdit()
        self.txt_script.setPlaceholderText("Path to the TESS curl script…")
        browse_script = QPushButton("Browse…")
        browse_script.clicked.connect(self.browse_script)
        script_row.addWidget(self.txt_script, 1)
        script_row.addWidget(browse_script)
        form.addRow("Bulk script", script_row)
        set_tooltip("bulk_script", self.txt_script, browse_script, form.labelForField(script_row))

        self.spn_amount = QSpinBox()
        self.spn_amount.setRange(1, 100000)
        self.spn_amount.setValue(100)
        form.addRow("Files to download", self.spn_amount)
        set_tooltip("download_amount", self.spn_amount, form.labelForField(self.spn_amount))
        self.spn_workers = QSpinBox()
        self.spn_workers.setRange(1, 32)
        self.spn_workers.setValue(4)
        form.addRow("Concurrent workers", self.spn_workers)
        set_tooltip("download_workers", self.spn_workers, form.labelForField(self.spn_workers))
        layout.addLayout(form)

        actions = QHBoxLayout()
        check_curl = QPushButton("Check curl")
        check_curl.clicked.connect(self.check_curl)
        set_tooltip("check_curl", check_curl)
        open_data = QPushButton("Open Data Folder")
        open_data.clicked.connect(self.open_data_folder)
        self.btn_start = QPushButton("Start Download")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.clicked.connect(self.start_download)
        set_tooltip("start_download", self.btn_start)
        actions.addWidget(check_curl)
        actions.addWidget(open_data)
        actions.addStretch(1)
        actions.addWidget(self.btn_start)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("Waiting for download…")
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("Activity Log"))
        self.txt_log = make_log()
        layout.addWidget(self.txt_log, 1)

    def refresh_from_project(self) -> None:
        project = self.main_win.current_project
        self.rb_lc.setEnabled(True)
        self.rb_tp.setEnabled(True)
        if not project:
            return
        kind = project.state.kind
        if kind == "lc":
            self.rb_lc.setChecked(True)
            self.rb_tp.setEnabled(False)
        elif kind == "tp":
            self.rb_tp.setChecked(True)
            self.rb_lc.setEnabled(False)
        if project.state.script and not self.txt_script.text().strip():
            self.txt_script.setText(project.state.script)

    def browse_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select TESS bulk download script", "", "Shell scripts (*.sh *.txt);;All files (*)"
        )
        if path:
            self.txt_script.setText(path)

    def check_curl(self) -> None:
        curl_path = shutil.which("curl")
        if curl_path:
            QMessageBox.information(self, "curl is available", f"curl was found at:\n{curl_path}")
        else:
            QMessageBox.warning(
                self, "curl not found",
                "TESSify's current bulk-download workflow requires curl available on PATH. "
                "Install/enable curl for your operating system, restart this app, and check again.",
            )

    def open_data_folder(self) -> None:
        project = self.main_win.current_project
        if project and not open_local_path(project.get_data_dir()):
            QMessageBox.warning(self, "Folder unavailable", "The data folder could not be opened yet.")

    def start_download(self) -> None:
        project = self.main_win.current_project
        if project is None:
            QMessageBox.warning(self, "No project", "Open or create a TESSify project first.")
            return
        script = Path(self.txt_script.text().strip()).expanduser()
        if not script.is_file():
            QMessageBox.warning(self, "Invalid script", "Choose an existing bulk-download script file first.")
            return
        if shutil.which("curl") is None:
            self.check_curl()
            return
        kind = "lc" if self.rb_lc.isChecked() else "tp"
        if project.state.kind not in (None, kind):
            QMessageBox.warning(
                self, "Different data type",
                f"This project already contains {project.state.kind!r} data. Create or open a separate project for {kind!r} files.",
            )
            return
        if not self.main_win.begin_job(2):
            return

        self._outcome = None
        self.btn_start.setEnabled(False)
        self.txt_log.clear()
        self.progress.setRange(0, 0)  # indeterminate until the engine reports real counts
        self.progress.setFormat("Preparing download…")
        self.progress.show()
        worker = PipelineWorker(
            project, "download", kind=kind, script_path=str(script.resolve()),
            amount=self.spn_amount.value(), workers=self.spn_workers.value(),
        )
        self.worker = worker
        worker.log_signal.connect(self.txt_log.append)
        worker.progress_signal.connect(self.update_progress)
        worker.result_signal.connect(self.record_outcome)
        worker.finished.connect(self.thread_finished)
        worker.start()

    def update_progress(self, finished: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(min(finished, max(total, 1)))
        self.progress.setFormat(f"{finished} / {total} commands")

    def record_outcome(self, success: bool, message: str) -> None:
        self._outcome = (success, message)

    def thread_finished(self) -> None:
        worker, self.worker = self.worker, None
        self.btn_start.setEnabled(True)
        self.progress.hide()
        self.main_win.end_job()
        if worker:
            worker.deleteLater()
        self.main_win.refresh_project_views()
        if self._outcome:
            success, message = self._outcome
            if success:
                QMessageBox.information(self, "Download finished", message)
            else:
                QMessageBox.critical(self, "Download failed", message)
        self._outcome = None


class ProcessPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        self.worker: PipelineWorker | None = None
        self._outcome: tuple[bool, str] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.addWidget(page_title(
            "Process Files",
            "Clean and flatten recorded FITS inputs, then save plots to the project's Graphs folder.",
        ))
        form = QFormLayout()
        self.spn_amount = QSpinBox()
        self.spn_amount.setRange(1, 100000)
        self.spn_amount.setValue(100)
        form.addRow("Files to process", self.spn_amount)
        set_tooltip("process_amount", self.spn_amount, form.labelForField(self.spn_amount))
        self.spn_workers = QSpinBox()
        self.spn_workers.setRange(1, max(1, min(os.cpu_count() or 1, 16)))
        self.spn_workers.setValue(1)
        form.addRow("CPU workers", self.spn_workers)
        set_tooltip("process_workers", self.spn_workers, form.labelForField(self.spn_workers))

        # --- Window length (flatten smoothing) ---
        self.spn_window_length = QSpinBox()
        self.spn_window_length.setRange(3, 10001)
        self.spn_window_length.setSingleStep(2)
        self.spn_window_length.setValue(101)
        form.addRow("Window length", self.spn_window_length)
        set_tooltip("window_length", self.spn_window_length, form.labelForField(self.spn_window_length))

        # --- Aperture mask (target-pixel files only) ---
        self.cmb_aperture_mask = QComboBox()
        self.cmb_aperture_mask.addItems(APERTURE_MASK_CHOICES)
        self.cmb_aperture_mask.setCurrentText("all")
        form.addRow("Aperture mask", self.cmb_aperture_mask)
        set_tooltip("aperture_mask", self.cmb_aperture_mask, form.labelForField(self.cmb_aperture_mask))
        for index, choice in enumerate(APERTURE_MASK_CHOICES):
            self.cmb_aperture_mask.setItemData(
                index, tooltip_text(TOOLTIPS[f"aperture_{choice}"]), Qt.ToolTipRole
            )
        self.lbl_aperture_note = QLabel("Aperture mask is only used for Target Pixel (tp) projects.")
        self.lbl_aperture_note.setObjectName("PageSubtitle")
        self.lbl_aperture_note.setWordWrap(True)
        form.addRow("", self.lbl_aperture_note)

        layout.addLayout(form)

        note = QLabel(
            "Memory note: each process can load its own copy of a FITS file. One worker is the safest default; "
            "raise it only if you have enough RAM."
        )
        note.setWordWrap(True)
        note.setObjectName("WarningText")
        layout.addWidget(note)
        actions = QHBoxLayout()
        open_graphs = QPushButton("Open Graphs Folder")
        open_graphs.clicked.connect(self.open_graphs_folder)
        self.btn_start = QPushButton("Start Processing")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.clicked.connect(self.start_processing)
        set_tooltip("start_processing", self.btn_start)
        actions.addWidget(open_graphs)
        actions.addStretch(1)
        actions.addWidget(self.btn_start)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setFormat("Waiting for processing…")
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("Activity Log"))
        self.txt_log = make_log()
        layout.addWidget(self.txt_log, 1)

    def open_graphs_folder(self) -> None:
        project = self.main_win.current_project
        if project:
            Path(project.get_graphs_dir()).mkdir(parents=True, exist_ok=True)
            if not open_local_path(project.get_graphs_dir()):
                QMessageBox.warning(self, "Folder unavailable", "The Graphs folder could not be opened.")

    def start_processing(self) -> None:
        project = self.main_win.current_project
        if project is None:
            QMessageBox.warning(self, "No project", "Open or create a TESSify project first.")
            return
        available = project.get_downloaded_files()
        if not available:
            QMessageBox.warning(
                self, "No input files found",
                "No downloaded FITS files recorded by TESSify are present. Download data first, or restore the files to the project's data folder.",
            )
            return
        window_length = self.spn_window_length.value()
        if window_length < 3 or window_length % 2 == 0:
            QMessageBox.warning(
                self, "Invalid window length",
                "Window length must be an odd integer ≥ 3.",
            )
            return
        aperture_mask = self.cmb_aperture_mask.currentText()
        if not self.main_win.begin_job(3):
            return

        self._outcome = None
        self.btn_start.setEnabled(False)
        self.txt_log.clear()
        self.progress.setRange(0, 0)
        self.progress.setFormat("Preparing processing…")
        self.progress.show()
        worker = PipelineWorker(
            project, "process", amount=self.spn_amount.value(), workers=self.spn_workers.value(),
            window_length=window_length, aperture_mask=aperture_mask,
        )
        self.worker = worker
        worker.log_signal.connect(self.txt_log.append)
        worker.progress_signal.connect(self.update_progress)
        worker.result_signal.connect(self.record_outcome)
        worker.finished.connect(self.thread_finished)
        worker.start()

    def update_progress(self, finished: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(min(finished, max(total, 1)))
        self.progress.setFormat(f"{finished} / {total} files")

    def record_outcome(self, success: bool, message: str) -> None:
        self._outcome = (success, message)

    def thread_finished(self) -> None:
        worker, self.worker = self.worker, None
        self.btn_start.setEnabled(True)
        self.progress.hide()
        self.main_win.end_job()
        if worker:
            worker.deleteLater()
        self.main_win.refresh_project_views()
        if self._outcome:
            success, message = self._outcome
            if not success:
                QMessageBox.critical(self, "Processing failed", message)
            else:
                answer = QMessageBox.question(
                    self, "Processing finished",
                    f"{message}\n\nOpen Candidate Review now?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes:
                    self.main_win.navigate_to(4)
        self._outcome = None


class CandidateReviewPage(QWidget):
    """Integrated Qt graph reviewer backed by TESSify config.json state."""

    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        self.graphs: list[str] = []
        self.current_index = 0
        self.shortlist: list[str] = []
        self._loading_list = False
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        header = QHBoxLayout()
        header.addWidget(page_title("Candidate Review", "Review the generated plots and save shortlist decisions as you go."), 1)
        self.btn_save_exit = QPushButton("Save & Exit Review")
        self.btn_save_exit.clicked.connect(self.save_and_exit)
        set_tooltip("review_exit", self.btn_save_exit)
        header.addWidget(self.btn_save_exit, 0, Qt.AlignTop)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(QLabel("Review Queue"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.on_list_selection)
        left_layout.addWidget(self.list_widget, 1)
        self.lbl_queue_count = QLabel("0 graphs")
        left_layout.addWidget(self.lbl_queue_count)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        self.lbl_info = QLabel("No graph loaded")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setFont(QFont("Segoe UI", 11, QFont.Bold))
        right_layout.addWidget(self.lbl_info)
        self.lbl_image = QLabel("No graphs found yet. Run Process Files first.")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setMinimumSize(250, 220)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_image.setObjectName("GraphCanvas")
        right_layout.addWidget(self.lbl_image, 1)

        controls = QHBoxLayout()
        self.btn_prev = QPushButton("← Previous")
        self.btn_prev.clicked.connect(self.prev_graph)
        self.btn_next = QPushButton("Next →")
        self.btn_next.clicked.connect(self.next_graph)
        self.btn_shortlist = QPushButton("★ Shortlist")
        self.btn_shortlist.setObjectName("PrimaryButton")
        self.btn_shortlist.clicked.connect(self.shortlist_current)
        self.btn_unshortlist = QPushButton("Remove from Shortlist")
        self.btn_unshortlist.clicked.connect(self.unshortlist_current)
        set_tooltip("review_prev", self.btn_prev)
        set_tooltip("review_next", self.btn_next)
        set_tooltip("review_shortlist", self.btn_shortlist)
        set_tooltip("review_unshortlist", self.btn_unshortlist)
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_next)
        controls.addStretch(1)
        controls.addWidget(self.btn_unshortlist)
        controls.addWidget(self.btn_shortlist)
        right_layout.addLayout(controls)

        utility = QHBoxLayout()
        self.btn_open_graph = QPushButton("Open Original Graph")
        self.btn_open_graph.clicked.connect(self.open_current_graph)
        self.btn_save_progress = QPushButton("Save Progress")
        self.btn_save_progress.clicked.connect(self.save_current_state)
        set_tooltip("review_save", self.btn_save_progress)
        self.btn_to_process = QPushButton("Go to Process Files")
        self.btn_to_process.clicked.connect(lambda: self.main_win.navigate_to(3))
        utility.addWidget(self.btn_open_graph)
        utility.addWidget(self.btn_save_progress)
        utility.addStretch(1)
        utility.addWidget(self.btn_to_process)
        right_layout.addLayout(utility)
        self.lbl_keyboard = QLabel("Keyboard: ← previous  •  → next  •  ↓ shortlist  •  ↑ remove  •  Esc save and exit")
        self.lbl_keyboard.setObjectName("PageSubtitle")
        self.lbl_keyboard.setWordWrap(True)
        right_layout.addWidget(self.lbl_keyboard)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([270, 900])
        outer.addWidget(splitter, 1)

        # Shortcuts are scoped to this page and never attached to a text input.
        for key, slot in (
            (Qt.Key_Left, self.prev_graph),
            (Qt.Key_Right, self.next_graph),
            (Qt.Key_Down, self.shortlist_current),
            (Qt.Key_Up, self.unshortlist_current),
            (Qt.Key_Escape, self.save_and_exit),
        ):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    def load_review(self) -> None:
        project = self.main_win.current_project
        if project is None:
            self.graphs = []
            self.shortlist = []
            self.list_widget.clear()
            self.lbl_image.setText("Please open a project first.")
            self.lbl_info.setText("No project open")
            self._update_buttons()
            return

        self.graphs = project.get_graphs()
        self._pixmap_cache.clear()  # refreshed graph files must not reuse stale/broken cached images
        saved_state = project.load_review_state()
        self.shortlist = list(saved_state.get("shortlist", []))
        self.current_index = int(saved_state.get("last_index", 0) or 0)
        self.current_index = min(max(self.current_index, 0), max(0, len(self.graphs) - 1))

        self._loading_list = True
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for filename in self.graphs:
            label = f"★  {filename}" if filename in self.shortlist else filename
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, filename)
            self.list_widget.addItem(item)
        if self.graphs:
            self.list_widget.setCurrentRow(self.current_index)
        self.list_widget.blockSignals(False)
        self._loading_list = False
        self.lbl_queue_count.setText(f"{len(self.graphs)} graph(s) available")
        if not self.graphs:
            self.lbl_image.setPixmap(QPixmap())
            self.lbl_image.setText("No graphs found yet. Run Process Files first.")
            self.lbl_info.setText("Candidate review is empty")
        else:
            self.display_current()
        self._update_buttons()

    def _current_filename(self) -> str | None:
        if 0 <= self.current_index < len(self.graphs):
            return self.graphs[self.current_index]
        return None

    def _get_pixmap(self, path: str) -> QPixmap:
        if path in self._pixmap_cache:
            self._pixmap_cache.move_to_end(path)
            return self._pixmap_cache[path]
        pixmap = QPixmap(path)
        self._pixmap_cache[path] = pixmap
        if len(self._pixmap_cache) > 8:
            self._pixmap_cache.popitem(last=False)
        return pixmap

    def display_current(self) -> None:
        filename = self._current_filename()
        project = self.main_win.current_project
        if filename is None or project is None:
            self.lbl_image.setPixmap(QPixmap())
            self.lbl_image.setText("No graphs found yet. Run Process Files first.")
            self.lbl_info.setText("No graph loaded")
            self._update_buttons()
            return

        full_path = str(Path(project.get_graphs_dir()) / filename)
        identifier = tic_id(filename)
        id_text = f"  |  {identifier}" if identifier else ""
        status_text = "Shortlisted" if filename in self.shortlist else "Not shortlisted"
        self.lbl_info.setText(
            f"Candidate {self.current_index + 1} of {len(self.graphs)}  |  {filename}{id_text}  |  {status_text}"
        )
        pixmap = self._get_pixmap(full_path)
        if pixmap.isNull():
            self.lbl_image.setPixmap(QPixmap())
            self.lbl_image.setText(f"Could not load graph:\n{filename}\nYou can skip to another graph.")
        else:
            self._fit_current_pixmap(pixmap)
        self._update_buttons()

    def _fit_current_pixmap(self, pixmap: QPixmap | None = None) -> None:
        filename = self._current_filename()
        project = self.main_win.current_project
        if filename is None or project is None:
            return
        if pixmap is None:
            pixmap = self._get_pixmap(str(Path(project.get_graphs_dir()) / filename))
        if pixmap.isNull():
            return
        size = self.lbl_image.contentsRect().size()
        width = max(1, size.width() - 8)
        height = max(1, size.height() - 8)
        scaled = pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_image.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt event name
        super().resizeEvent(event)
        filename = self._current_filename()
        project = self.main_win.current_project
        if filename and project:
            pixmap = self._get_pixmap(str(Path(project.get_graphs_dir()) / filename))
            if not pixmap.isNull():
                self._fit_current_pixmap(pixmap)

    def on_list_selection(self, row: int) -> None:
        if self._loading_list or row < 0 or row >= len(self.graphs):
            return
        old_index = self.current_index
        self.current_index = row
        try:
            self.save_current_state(show_errors=True)
        except Exception:
            self.current_index = old_index
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentRow(old_index)
            self.list_widget.blockSignals(False)
            return
        self.display_current()

    def _update_buttons(self) -> None:
        has_graph = self._current_filename() is not None
        self.btn_prev.setEnabled(has_graph and self.current_index > 0)
        self.btn_next.setEnabled(has_graph and self.current_index < len(self.graphs) - 1)
        self.btn_shortlist.setEnabled(has_graph and self._current_filename() not in self.shortlist)
        self.btn_unshortlist.setEnabled(has_graph and self._current_filename() in self.shortlist)
        self.btn_open_graph.setEnabled(has_graph)
        self.btn_save_progress.setEnabled(self.main_win.current_project is not None)
        self.btn_to_process.setEnabled(self.main_win.current_project is not None)
        self.btn_save_exit.setEnabled(self.main_win.current_project is not None)

    def prev_graph(self) -> None:
        if self.current_index > 0:
            self.list_widget.setCurrentRow(self.current_index - 1)

    def next_graph(self) -> None:
        if self.current_index + 1 < len(self.graphs):
            self.list_widget.setCurrentRow(self.current_index + 1)

    def _change_shortlist(self, should_mark: bool) -> None:
        filename = self._current_filename()
        project = self.main_win.current_project
        if filename is None or project is None:
            return
        old_shortlist = list(self.shortlist)
        if should_mark and filename not in self.shortlist:
            self.shortlist.append(filename)
        elif not should_mark and filename in self.shortlist:
            self.shortlist.remove(filename)
        else:
            return
        try:
            project.save_review_state({"shortlist": self.shortlist, "last_index": self.current_index})
        except Exception as error:
            self.shortlist = old_shortlist
            self._refresh_queue_labels()
            QMessageBox.critical(self, "Could not save review state", f"Your change was not saved to disk.\n\n{error}")
            return
        self._refresh_queue_labels()
        self.display_current()
        self.main_win.refresh_project_views()

    def shortlist_current(self) -> None:
        self._change_shortlist(True)

    def unshortlist_current(self) -> None:
        self._change_shortlist(False)

    def _refresh_queue_labels(self) -> None:
        for row, filename in enumerate(self.graphs):
            item = self.list_widget.item(row)
            if item:
                item.setText(f"★  {filename}" if filename in self.shortlist else filename)
                item.setData(Qt.UserRole, filename)

    def save_current_state(self, show_errors: bool = True) -> bool:
        project = self.main_win.current_project
        if project is None:
            return False
        try:
            project.save_review_state({"shortlist": self.shortlist, "last_index": self.current_index})
            self.main_win.set_status("Review progress saved")
            return True
        except Exception as error:
            self.main_win.set_status("Review state could not be saved")
            if show_errors:
                QMessageBox.critical(self, "Save failed", f"Review progress could not be saved.\n\n{error}")
            raise

    def open_current_graph(self) -> None:
        filename = self._current_filename()
        project = self.main_win.current_project
        if filename and project:
            path = Path(project.get_graphs_dir()) / filename
            if not open_local_path(path):
                QMessageBox.warning(self, "Open failed", f"Could not open graph file:\n{path}")

    def save_and_exit(self) -> None:
        if self.save_current_state():
            self.main_win.navigate_to(1 if self.main_win.current_project else 0)


class ResultsExportPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.addWidget(page_title(
            "Results & Export",
            "Export unique TIC IDs using TESSify's existing JSON output contract.",
        ))
        self.lbl_count = QLabel("No project open")
        self.lbl_count.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(self.lbl_count)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "TIC ID", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh Results")
        refresh.clicked.connect(self.load_results)
        review = QPushButton("Open Candidate Review")
        review.clicked.connect(lambda: self.main_win.navigate_to(4))
        folder = QPushButton("Open Project Folder")
        folder.clicked.connect(self.open_project_folder)
        export = QPushButton("Export JSON…")
        export.setObjectName("PrimaryButton")
        export.clicked.connect(self.export_results)
        set_tooltip("export_results", export)
        controls.addWidget(refresh)
        controls.addWidget(review)
        controls.addWidget(folder)
        controls.addStretch(1)
        controls.addWidget(export)
        layout.addLayout(controls)

    def load_results(self) -> None:
        project = self.main_win.current_project
        if project is None:
            self.lbl_count.setText("No project open")
            self.table.setRowCount(0)
            return
        results = project.get_results()
        self.lbl_count.setText(f"{len(results)} unique shortlisted TIC ID(s)")
        self.table.setRowCount(len(results))
        for row, tic in enumerate(results, start=0):
            self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(tic))
            self.table.setItem(row, 2, QTableWidgetItem("Shortlisted"))
        if not results:
            self.table.setRowCount(1)
            self.table.setItem(0, 1, QTableWidgetItem("No candidates shortlisted yet"))
            self.table.setItem(0, 2, QTableWidgetItem("Review candidates to add results"))

    def export_results(self) -> None:
        project = self.main_win.current_project
        if project is None:
            QMessageBox.warning(self, "No project", "Open a project before exporting results.")
            return
        default_path = str(Path(project.project_path) / "shortlisted_tic_ids.json")
        path, _ = QFileDialog.getSaveFileName(self, "Export TIC IDs", default_path, "JSON files (*.json);;All files (*)")
        if not path:
            return
        if not Path(path).suffix:
            path += ".json"
        try:
            project.save_results(path)
        except Exception as error:
            QMessageBox.critical(self, "Export failed", f"TESSify could not write the export.\n\n{error}")
            return
        QMessageBox.information(self, "Export complete", f"Results were exported to:\n{path}")

    def open_project_folder(self) -> None:
        project = self.main_win.current_project
        if project and not open_local_path(project.project_path):
            QMessageBox.warning(self, "Folder unavailable", "The project folder could not be opened.")


class SettingsPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_win = main_window
        self.settings = QSettings(APP_ORG, APP_NAME)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.addWidget(page_title("Settings & Diagnostics", "Preferences apply to this desktop interface; they do not modify scientific project settings."))

        form = QFormLayout()
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["Dark", "Light"])
        self.cmb_theme.setCurrentText(str(self.settings.value("theme", "Dark")))
        form.addRow("Appearance", self.cmb_theme)
        self.spn_download_workers = QSpinBox()
        self.spn_download_workers.setRange(1, 32)
        self.spn_download_workers.setValue(int(self.settings.value("download_workers", 4)))
        form.addRow("Default download workers", self.spn_download_workers)
        set_tooltip("download_workers", self.spn_download_workers, form.labelForField(self.spn_download_workers))
        self.spn_process_workers = QSpinBox()
        self.spn_process_workers.setRange(1, max(1, min(os.cpu_count() or 1, 16)))
        self.spn_process_workers.setValue(int(self.settings.value("process_workers", 1)))
        form.addRow("Default processing workers", self.spn_process_workers)
        set_tooltip("process_workers", self.spn_process_workers, form.labelForField(self.spn_process_workers))
        safety_note = QLabel("Closing or switching projects is blocked while a download or processing job is active, so project state can be saved safely.")
        safety_note.setWordWrap(True)
        form.addRow("Job safety", safety_note)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        save = QPushButton("Save Settings")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self.save_settings)
        defaults = QPushButton("Restore Defaults")
        defaults.clicked.connect(self.restore_defaults)
        buttons.addWidget(save)
        buttons.addWidget(defaults)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addSpacing(18)

        diagnostics = QGroupBox("Environment")
        diagnostics_layout = QVBoxLayout(diagnostics)
        self.lbl_diagnostics = QLabel()
        self.lbl_diagnostics.setWordWrap(True)
        diagnostics_layout.addWidget(self.lbl_diagnostics)
        layout.addWidget(diagnostics)
        layout.addStretch(1)
        self.refresh_diagnostics()

    def refresh_diagnostics(self) -> None:
        curl = shutil.which("curl") or "Not found on PATH"
        engine = "Available" if TESSifyProject is not None else f"Unavailable: {_ENGINE_IMPORT_ERROR}"
        self.lbl_diagnostics.setText(
            f"Python: {sys.version.split()[0]}\n"
            f"PySide6: {__import__('PySide6').__version__}\n"
            f"TESSify engine: {engine}\n"
            f"curl: {curl}"
        )

    def save_settings(self) -> None:
        self.settings.setValue("theme", self.cmb_theme.currentText())
        self.settings.setValue("download_workers", self.spn_download_workers.value())
        self.settings.setValue("process_workers", self.spn_process_workers.value())
        self.settings.sync()
        self.main_win.page_download.spn_workers.setValue(self.spn_download_workers.value())
        self.main_win.page_process.spn_workers.setValue(self.spn_process_workers.value())
        self.main_win.apply_theme(self.cmb_theme.currentText())
        QMessageBox.information(self, "Settings saved", "Desktop preferences were saved.")

    def restore_defaults(self) -> None:
        self.cmb_theme.setCurrentText("Dark")
        self.spn_download_workers.setValue(4)
        self.spn_process_workers.setValue(1)


class HelpAboutPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.addWidget(page_title("Help / About", "A local desktop interface for TESSify."))
        text = QLabel(
            "TESSify helps students, researchers, and citizen scientists inspect possible transit-like dips in NASA TESS observations.\n\n"
            "Workflow\n"
            "1. Create a new project or open a folder containing a TESSify config.json.\n"
            "2. Download Light Curve (lc) or Target Pixel (tp) FITS files using a TESS bulk script. curl must be on PATH.\n"
            "3. Process the downloaded files to generate graphs. Processing requires the package's scientific dependencies.\n"
            "4. Review the graphs. Shortlist and remove candidates; decisions and the current position are saved to config.json.\n"
            "5. Export the unique TIC IDs as JSON using the package's existing results API.\n\n"
            "Keyboard shortcuts in Candidate Review: Left = previous, Right = next, Down = shortlist, Up = remove from shortlist, Esc = save and exit review.\n\n"
            "GitHub: https://github.com/arpit290/TESSify\n\n"
            "The GUI does not fabricate data, candidate IDs, graph counts, or progress percentages."
        )
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(text)
        layout.addStretch(1)


class MainWindow(QMainWindow):
    PROJECT_PAGES = {1, 2, 3, 4, 5}

    def __init__(self) -> None:
        super().__init__()
        self.current_project: ProjectWrapper | None = None
        self.job_running = False
        self.active_job_page: int | None = None
        self.settings = QSettings(APP_ORG, APP_NAME)
        self._build_ui()
        self.apply_theme(str(self.settings.value("theme", "Dark")))
        self.update_navigation_state()
        self.update_project_indicator()

    def _build_ui(self) -> None:
        self.setWindowTitle("TESSify — Exoplanet Transit Candidate Desktop")
        self.setWindowIcon(QIcon(_LOGO_PATH))
        self.resize(1280, 820)
        root = QWidget()
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar_widget = QWidget()
        sidebar_widget.setObjectName("SidebarContainer")
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo at the top of the sidebar — white card so dark text stays readable
        logo_label = SvgLogoLabel(_LOGO_PATH, QSize(224, 60))
        logo_label.setObjectName("SidebarLogo")
        logo_label.setStyleSheet(
            "background: #FFFFFF; border-radius: 10px;"
            "margin: 12px 10px 8px 10px; padding: 10px 6px;"
        )
        sidebar_layout.addWidget(logo_label)

        SIDEBAR_W = 250
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        nav_items = [
            "Home", "Project Overview", "Download Data", "Process Files",
            "Candidate Review", "Results & Export", "Settings", "Help / About",
        ]
        for name in nav_items:
            self.sidebar.addItem(QListWidgetItem(name))
        self.sidebar.currentRowChanged.connect(self.navigate_to)
        sidebar_layout.addWidget(self.sidebar, 1)
        sidebar_widget.setFixedWidth(SIDEBAR_W)
        main_layout.addWidget(sidebar_widget)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("AppHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 8, 20, 8)
        # Header logo (the logo already contains the "TESSify" wordmark)
        header_logo = SvgLogoLabel(_LOGO_PATH, QSize(200, 40))
        header_logo.setStyleSheet(
            "background: #FFFFFF; border-radius: 6px; padding: 4px 8px;"
        )
        header_layout.addWidget(header_logo)
        self.lbl_project = QLabel("No project open")
        self.lbl_project.setObjectName("ProjectIndicator")
        self.lbl_project.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_project = QPushButton("Open Project…")
        open_project.clicked.connect(self.open_project_folder)
        set_tooltip("project_open", open_project)
        header_layout.addStretch(1)
        header_layout.addWidget(self.lbl_project, 1)
        header_layout.addWidget(open_project)
        content_layout.addWidget(header)

        self.stack = QStackedWidget()
        self.page_home = HomePage(self)
        self.page_overview = ProjectOverviewPage(self)
        self.page_download = DownloadPage(self)
        self.page_process = ProcessPage(self)
        self.page_review = CandidateReviewPage(self)
        self.page_results = ResultsExportPage(self)
        self.page_settings = SettingsPage(self)
        self.page_help = HelpAboutPage(self)
        self.page_download.spn_workers.setValue(int(self.settings.value("download_workers", 4)))
        self.page_process.spn_workers.setValue(int(self.settings.value("process_workers", 1)))
        for page in (
            self.page_home, self.page_overview, self.page_download, self.page_process,
            self.page_review, self.page_results, self.page_settings, self.page_help,
        ):
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, 1)
        main_layout.addWidget(content, 1)
        self.statusBar().showMessage("Ready | No active project")
        self.sidebar.setCurrentRow(0)

    def apply_theme(self, theme: str) -> None:
        # TESSify branded palette
        # Primary:  navy #101A35  cyan #26C6F5  blue #347FEA  indigo #7487FF
        # Secondary: deep-blue #263D72  stellar-cyan #36D9F5  soft-indigo #8290FF  gold #FFC857
        # Supporting: cream #FFF4D6  slate #65718D
        if theme.lower() == "light":
            self.setStyleSheet("""
                QWidget { background: #F4F6FB; color: #101A35; font-size: 13px; }
                QMainWindow, QStackedWidget { background: #F4F6FB; }
                #SidebarContainer { background: #E8EDF8; }
                #SidebarLogo { background: #E8EDF8; }
                #Sidebar { background: #E8EDF8; border: none; color: #263D72; font-size: 13px; }
                #Sidebar::item { padding: 12px 14px; }
                #Sidebar::item:selected { background: #D0DCEF; color: #347FEA; font-weight: bold; }
                #Sidebar::item:hover { background: #DDE5F2; }
                #AppHeader { background: #FFFFFF; border-bottom: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26C6F5, stop:1 #7487FF); }
                #ProjectIndicator, #PageSubtitle { color: #65718D; }
                #PageTitle { color: #101A35; }
                QGroupBox { border: 1px solid #C5D0E3; border-radius: 8px; margin-top: 10px; padding: 14px; font-weight: bold; color: #263D72; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #347FEA; }
                QPushButton { background: #E8EDF8; border: 1px solid #C5D0E3; border-radius: 6px; padding: 8px 14px; color: #263D72; }
                QPushButton:hover { background: #D0DCEF; border-color: #7487FF; }
                QPushButton:disabled { color: #A0AAC0; }
                #PrimaryButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26C6F5, stop:1 #7487FF); color: #FFFFFF; border: none; font-weight: bold; border-radius: 6px; padding: 8px 18px; }
                #PrimaryButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #36D9F5, stop:1 #8290FF); }
                QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget, QListWidget { background: #FFFFFF; border: 1px solid #C5D0E3; border-radius: 5px; selection-background-color: #B0DAFD; color: #101A35; }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #26C6F5; }
                QComboBox QAbstractItemView { background: #FFFFFF; color: #101A35; selection-background-color: #D0DCEF; }
                QProgressBar { background: #E8EDF8; border: 1px solid #C5D0E3; border-radius: 5px; text-align: center; color: #263D72; }
                QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26C6F5, stop:1 #7487FF); border-radius: 4px; }
                #JobLog { background: #F8FAFD; color: #263D72; font-family: Consolas, monospace; border: 1px solid #C5D0E3; }
                #GraphCanvas { background: #EEF1F7; border: 1px solid #C5D0E3; border-radius: 6px; }
                #WarningText { color: #B87800; }
                QHeaderView::section { background: #E8EDF8; color: #263D72; border: none; padding: 6px; font-weight: bold; }
                QScrollBar:vertical { background: #F0F3F9; width: 10px; border-radius: 5px; }
                QScrollBar::handle:vertical { background: #C5D0E3; border-radius: 5px; min-height: 30px; }
                QScrollBar::handle:vertical:hover { background: #7487FF; }
                QStatusBar { background: #FFFFFF; color: #65718D; border-top: 1px solid #C5D0E3; }
                QToolTip { background: #FFFFFF; color: #101A35; border: 1px solid #7487FF; padding: 6px; }
            """)
        else:
            self.setStyleSheet("""
                QWidget { background: #101A35; color: #E0E6F0; font-size: 13px; }
                QMainWindow, QStackedWidget { background: #101A35; }
                #SidebarContainer { background: #0C1328; }
                #SidebarLogo { background: #0C1328; }
                #Sidebar { background: #0C1328; border: none; color: #8290FF; font-size: 13px; }
                #Sidebar::item { padding: 12px 14px; }
                #Sidebar::item:selected { background: #1C2A4E; color: #26C6F5; font-weight: bold; }
                #Sidebar::item:hover { background: #162040; }
                #AppHeader { background: #162040; border-bottom: 2px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26C6F5, stop:1 #7487FF); }
                #ProjectIndicator, #PageSubtitle { color: #65718D; }
                #PageTitle { color: #F0F4FF; }
                QGroupBox { border: 1px solid #263D72; border-radius: 8px; margin-top: 10px; padding: 14px; font-weight: bold; color: #8290FF; }
                QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #26C6F5; }
                QPushButton { background: #1C2A4E; border: 1px solid #263D72; border-radius: 6px; padding: 8px 14px; color: #C0CAE0; }
                QPushButton:hover { background: #263D72; border-color: #7487FF; color: #FFFFFF; }
                QPushButton:disabled { color: #45506A; }
                #PrimaryButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26C6F5, stop:1 #7487FF); color: #FFFFFF; border: none; font-weight: bold; border-radius: 6px; padding: 8px 18px; }
                #PrimaryButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #36D9F5, stop:1 #8290FF); }
                QLineEdit, QSpinBox, QComboBox, QTextEdit, QTableWidget, QListWidget { background: #0C1328; border: 1px solid #263D72; border-radius: 5px; selection-background-color: #1C2A4E; color: #E0E6F0; }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #26C6F5; }
                QComboBox QAbstractItemView { background: #0C1328; color: #E0E6F0; selection-background-color: #1C2A4E; }
                QProgressBar { background: #0C1328; border: 1px solid #263D72; border-radius: 5px; text-align: center; color: #8290FF; }
                QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26C6F5, stop:1 #7487FF); border-radius: 4px; }
                #JobLog { background: #080E20; color: #36D9F5; font-family: Consolas, monospace; border: 1px solid #263D72; }
                #GraphCanvas { background: #0C1328; border: 1px solid #263D72; border-radius: 6px; }
                #WarningText { color: #FFC857; }
                QHeaderView::section { background: #162040; color: #8290FF; border: none; padding: 6px; font-weight: bold; }
                QScrollBar:vertical { background: #0C1328; width: 10px; border-radius: 5px; }
                QScrollBar::handle:vertical { background: #263D72; border-radius: 5px; min-height: 30px; }
                QScrollBar::handle:vertical:hover { background: #26C6F5; }
                QStatusBar { background: #0C1328; color: #65718D; border-top: 1px solid #263D72; }
                QToolTip { background: #162040; color: #E0E6F0; border: 1px solid #26C6F5; padding: 6px; }
            """)

    def update_navigation_state(self) -> None:
        for index in range(self.sidebar.count()):
            item = self.sidebar.item(index)
            if index in self.PROJECT_PAGES and self.current_project is None:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEnabled)

    def update_project_indicator(self) -> None:
        project = self.current_project
        self.lbl_project.setText(f"Project: {project.name}  ·  {project.project_path}" if project else "No project open")
        self.update_navigation_state()

    def navigate_to(self, index: int) -> None:
        if index < 0 or index >= self.stack.count():
            return
        if index in self.PROJECT_PAGES and self.current_project is None:
            self._restore_sidebar_selection()
            QMessageBox.information(self, "No active project", "Open or create a project first.")
            return
        if self.job_running and index != self.active_job_page:
            self._restore_sidebar_selection()
            return
        self.stack.setCurrentIndex(index)
        if self.sidebar.currentRow() != index:
            self.sidebar.blockSignals(True)
            self.sidebar.setCurrentRow(index)
            self.sidebar.blockSignals(False)
        if index == 1:
            self.page_overview.update_project_info(self.current_project)
        elif index == 2:
            self.page_download.refresh_from_project()
        elif index == 4:
            self.page_review.load_review()
        elif index == 5:
            self.page_results.load_results()
        elif index == 6:
            self.page_settings.refresh_diagnostics()

    def _restore_sidebar_selection(self) -> None:
        self.sidebar.blockSignals(True)
        self.sidebar.setCurrentRow(self.stack.currentIndex())
        self.sidebar.blockSignals(False)

    def set_status(self, message: str) -> None:
        project_name = self.current_project.name if self.current_project else "No project"
        self.statusBar().showMessage(f"{project_name}  |  {message}")

    def begin_job(self, page_index: int) -> bool:
        if self.current_project is None:
            QMessageBox.warning(self, "No project", "Open or create a project first.")
            return False
        if self.job_running:
            QMessageBox.information(self, "Job already running", "Wait for the current job to finish before starting another.")
            return False
        self.job_running = True
        self.active_job_page = page_index
        self.set_status("Job running…")
        self.update_navigation_state()
        return True

    def end_job(self) -> None:
        self.job_running = False
        self.active_job_page = None
        self.set_status("Ready")
        self.update_navigation_state()
        self.update_project_indicator()

    def refresh_project_views(self) -> None:
        self.page_overview.update_project_info(self.current_project)
        self.page_results.load_results()

    def show_create_project_dialog(self) -> None:
        if self.job_running:
            QMessageBox.information(self, "Job running", "Wait for the current job to finish before switching projects.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Create New TESSify Project")
        dialog.setMinimumWidth(510)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name_input = QLineEdit()
        name_input.setPlaceholderText("e.g. TESS Sector 14 Analysis")
        parent_row = QHBoxLayout()
        parent_input = QLineEdit(str(Path.home()))
        parent_input.setPlaceholderText("Choose the parent folder")
        browse = QPushButton("Browse…")
        def choose_parent() -> None:
            selected = QFileDialog.getExistingDirectory(dialog, "Select Parent Folder", parent_input.text())
            if selected:
                parent_input.setText(selected)
        browse.clicked.connect(choose_parent)
        parent_row.addWidget(parent_input, 1)
        parent_row.addWidget(browse)
        form.addRow("Project name", name_input)
        form.addRow("Parent folder", parent_row)
        set_tooltip("project_name", name_input, form.labelForField(name_input))
        set_tooltip("project_parent", parent_input, browse, form.labelForField(parent_row))
        layout.addLayout(form)
        hint = QLabel("TESSify creates a new folder and never overwrites an existing project.")
        hint.setWordWrap(True)
        hint.setObjectName("PageSubtitle")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Create Project")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        name = name_input.text().strip()
        parent = parent_input.text().strip()
        try:
            project = ProjectWrapper.create(parent, name)
        except Exception as error:
            QMessageBox.critical(self, "Could not create project", str(error))
            return
        self.current_project = project
        self.update_project_indicator()
        self.refresh_project_views()
        self.navigate_to(1)
        self.set_status("Project created")

    def open_project_folder(self) -> None:
        if self.job_running:
            QMessageBox.information(self, "Job running", "Wait for the current job to finish before switching projects.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select Existing TESSify Project Folder", str(Path.home()))
        if not folder:
            return
        try:
            project = ProjectWrapper.restore(folder)
        except Exception as error:
            QMessageBox.critical(self, "Could not open project", f"The folder could not be restored as a TESSify project.\n\n{error}")
            return
        # Replace the active project only after a successful restore.
        self.current_project = project
        self.update_project_indicator()
        self.refresh_project_views()
        self.navigate_to(1)
        self.set_status("Project opened")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt event name
        if self.job_running:
            QMessageBox.warning(
                self, "Job still running",
                "A download or processing job is still running. Let it finish before closing TESSify so project state can be saved safely.",
            )
            event.ignore()
            return
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    if TESSifyProject is None:
        QMessageBox.critical(
            None, "TESSify engine unavailable",
            f"The TESSify package could not be imported.\n\n{_ENGINE_IMPORT_ERROR}\n\n"
            "Run the GUI with python -m TESSify_GUI or the tessify-gui command.",
        )
        return 1
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
