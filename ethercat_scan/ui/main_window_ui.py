# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.8.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QSizePolicy,
    QSpacerItem, QSplitter, QVBoxLayout, QWidget)

class Ui_ScanAppQt(object):
    def setupUi(self, ScanAppQt):
        if not ScanAppQt.objectName():
            ScanAppQt.setObjectName(u"ScanAppQt")
        ScanAppQt.resize(1100, 840)
        self.root_layout = QVBoxLayout(ScanAppQt)
        self.root_layout.setSpacing(4)
        self.root_layout.setObjectName(u"root_layout")
        self.root_layout.setContentsMargins(6, 6, 6, 6)
        self.row0 = QHBoxLayout()
        self.row0.setObjectName(u"row0")
        self.hw_group = QGroupBox(ScanAppQt)
        self.hw_group.setObjectName(u"hw_group")
        self.hw_grid = QGridLayout(self.hw_group)
        self.hw_grid.setObjectName(u"hw_grid")
        self.dry_run = QCheckBox(self.hw_group)
        self.dry_run.setObjectName(u"dry_run")
        self.dry_run.setChecked(True)

        self.hw_grid.addWidget(self.dry_run, 0, 0, 1, 4)

        self.label_hw_ifname = QLabel(self.hw_group)
        self.label_hw_ifname.setObjectName(u"label_hw_ifname")

        self.hw_grid.addWidget(self.label_hw_ifname, 1, 0, 1, 1)

        self.ifname = QLineEdit(self.hw_group)
        self.ifname.setObjectName(u"ifname")

        self.hw_grid.addWidget(self.ifname, 1, 1, 1, 3)

        self.label_x_alias = QLabel(self.hw_group)
        self.label_x_alias.setObjectName(u"label_x_alias")

        self.hw_grid.addWidget(self.label_x_alias, 2, 0, 1, 1)

        self.x_alias = QLineEdit(self.hw_group)
        self.x_alias.setObjectName(u"x_alias")

        self.hw_grid.addWidget(self.x_alias, 2, 1, 1, 1)

        self.label_y_alias = QLabel(self.hw_group)
        self.label_y_alias.setObjectName(u"label_y_alias")

        self.hw_grid.addWidget(self.label_y_alias, 2, 2, 1, 1)

        self.y_alias = QLineEdit(self.hw_group)
        self.y_alias.setObjectName(u"y_alias")

        self.hw_grid.addWidget(self.y_alias, 2, 3, 1, 1)

        self.label_x_ppmm = QLabel(self.hw_group)
        self.label_x_ppmm.setObjectName(u"label_x_ppmm")

        self.hw_grid.addWidget(self.label_x_ppmm, 3, 0, 1, 1)

        self.x_ppmm = QLineEdit(self.hw_group)
        self.x_ppmm.setObjectName(u"x_ppmm")

        self.hw_grid.addWidget(self.x_ppmm, 3, 1, 1, 1)

        self.label_y_ppmm = QLabel(self.hw_group)
        self.label_y_ppmm.setObjectName(u"label_y_ppmm")

        self.hw_grid.addWidget(self.label_y_ppmm, 3, 2, 1, 1)

        self.y_ppmm = QLineEdit(self.hw_group)
        self.y_ppmm.setObjectName(u"y_ppmm")

        self.hw_grid.addWidget(self.y_ppmm, 3, 3, 1, 1)

        self.x_reverse = QCheckBox(self.hw_group)
        self.x_reverse.setObjectName(u"x_reverse")

        self.hw_grid.addWidget(self.x_reverse, 4, 1, 1, 1)

        self.y_reverse = QCheckBox(self.hw_group)
        self.y_reverse.setObjectName(u"y_reverse")

        self.hw_grid.addWidget(self.y_reverse, 4, 3, 1, 1)


        self.row0.addWidget(self.hw_group)

        self.pm_group = QGroupBox(ScanAppQt)
        self.pm_group.setObjectName(u"pm_group")
        self.pm_grid = QGridLayout(self.pm_group)
        self.pm_grid.setObjectName(u"pm_grid")
        self.pm_use_real = QCheckBox(self.pm_group)
        self.pm_use_real.setObjectName(u"pm_use_real")

        self.pm_grid.addWidget(self.pm_use_real, 0, 0, 1, 2)

        self.label_pm_resource = QLabel(self.pm_group)
        self.label_pm_resource.setObjectName(u"label_pm_resource")

        self.pm_grid.addWidget(self.label_pm_resource, 1, 0, 1, 1)

        self.pm_resource = QLineEdit(self.pm_group)
        self.pm_resource.setObjectName(u"pm_resource")

        self.pm_grid.addWidget(self.pm_resource, 1, 1, 1, 1)

        self.label_pm_wavelength = QLabel(self.pm_group)
        self.label_pm_wavelength.setObjectName(u"label_pm_wavelength")

        self.pm_grid.addWidget(self.label_pm_wavelength, 2, 0, 1, 1)

        self.pm_wavelength = QLineEdit(self.pm_group)
        self.pm_wavelength.setObjectName(u"pm_wavelength")

        self.pm_grid.addWidget(self.pm_wavelength, 2, 1, 1, 1)

        self.label_pm_hint = QLabel(self.pm_group)
        self.label_pm_hint.setObjectName(u"label_pm_hint")
        self.label_pm_hint.setStyleSheet(u"color: gray;")

        self.pm_grid.addWidget(self.label_pm_hint, 3, 0, 1, 2)


        self.row0.addWidget(self.pm_group)


        self.root_layout.addLayout(self.row0)

        self.row1 = QHBoxLayout()
        self.row1.setObjectName(u"row1")
        self.home_group = QGroupBox(ScanAppQt)
        self.home_group.setObjectName(u"home_group")
        self.home_grid = QGridLayout(self.home_group)
        self.home_grid.setObjectName(u"home_grid")
        self.label_x_home_method = QLabel(self.home_group)
        self.label_x_home_method.setObjectName(u"label_x_home_method")

        self.home_grid.addWidget(self.label_x_home_method, 0, 0, 1, 1)

        self.x_home_method = QComboBox(self.home_group)
        self.x_home_method.addItem("")
        self.x_home_method.addItem("")
        self.x_home_method.addItem("")
        self.x_home_method.addItem("")
        self.x_home_method.setObjectName(u"x_home_method")

        self.home_grid.addWidget(self.x_home_method, 0, 1, 1, 1)

        self.label_x_min = QLabel(self.home_group)
        self.label_x_min.setObjectName(u"label_x_min")

        self.home_grid.addWidget(self.label_x_min, 0, 2, 1, 1)

        self.x_min = QLineEdit(self.home_group)
        self.x_min.setObjectName(u"x_min")

        self.home_grid.addWidget(self.x_min, 0, 3, 1, 1)

        self.label_x_min_tilde = QLabel(self.home_group)
        self.label_x_min_tilde.setObjectName(u"label_x_min_tilde")

        self.home_grid.addWidget(self.label_x_min_tilde, 0, 4, 1, 1)

        self.x_max = QLineEdit(self.home_group)
        self.x_max.setObjectName(u"x_max")

        self.home_grid.addWidget(self.x_max, 0, 5, 1, 1)

        self.label_y_home_method = QLabel(self.home_group)
        self.label_y_home_method.setObjectName(u"label_y_home_method")

        self.home_grid.addWidget(self.label_y_home_method, 1, 0, 1, 1)

        self.y_home_method = QComboBox(self.home_group)
        self.y_home_method.addItem("")
        self.y_home_method.addItem("")
        self.y_home_method.addItem("")
        self.y_home_method.addItem("")
        self.y_home_method.setObjectName(u"y_home_method")

        self.home_grid.addWidget(self.y_home_method, 1, 1, 1, 1)

        self.label_y_min = QLabel(self.home_group)
        self.label_y_min.setObjectName(u"label_y_min")

        self.home_grid.addWidget(self.label_y_min, 1, 2, 1, 1)

        self.y_min = QLineEdit(self.home_group)
        self.y_min.setObjectName(u"y_min")

        self.home_grid.addWidget(self.y_min, 1, 3, 1, 1)

        self.label_y_min_tilde = QLabel(self.home_group)
        self.label_y_min_tilde.setObjectName(u"label_y_min_tilde")

        self.home_grid.addWidget(self.label_y_min_tilde, 1, 4, 1, 1)

        self.y_max = QLineEdit(self.home_group)
        self.y_max.setObjectName(u"y_max")

        self.home_grid.addWidget(self.y_max, 1, 5, 1, 1)


        self.row1.addWidget(self.home_group)

        self.scan_group = QGroupBox(ScanAppQt)
        self.scan_group.setObjectName(u"scan_group")
        self.scan_grid = QGridLayout(self.scan_group)
        self.scan_grid.setObjectName(u"scan_grid")
        self.label_x_start = QLabel(self.scan_group)
        self.label_x_start.setObjectName(u"label_x_start")

        self.scan_grid.addWidget(self.label_x_start, 0, 0, 1, 1)

        self.x_start = QLineEdit(self.scan_group)
        self.x_start.setObjectName(u"x_start")

        self.scan_grid.addWidget(self.x_start, 0, 1, 1, 1)

        self.label_y_start = QLabel(self.scan_group)
        self.label_y_start.setObjectName(u"label_y_start")

        self.scan_grid.addWidget(self.label_y_start, 0, 2, 1, 1)

        self.y_start = QLineEdit(self.scan_group)
        self.y_start.setObjectName(u"y_start")

        self.scan_grid.addWidget(self.y_start, 0, 3, 1, 1)

        self.label_dwell = QLabel(self.scan_group)
        self.label_dwell.setObjectName(u"label_dwell")

        self.scan_grid.addWidget(self.label_dwell, 0, 4, 1, 1)

        self.dwell = QLineEdit(self.scan_group)
        self.dwell.setObjectName(u"dwell")

        self.scan_grid.addWidget(self.dwell, 0, 5, 1, 1)

        self.label_x_stop = QLabel(self.scan_group)
        self.label_x_stop.setObjectName(u"label_x_stop")

        self.scan_grid.addWidget(self.label_x_stop, 1, 0, 1, 1)

        self.x_stop = QLineEdit(self.scan_group)
        self.x_stop.setObjectName(u"x_stop")

        self.scan_grid.addWidget(self.x_stop, 1, 1, 1, 1)

        self.label_y_stop = QLabel(self.scan_group)
        self.label_y_stop.setObjectName(u"label_y_stop")

        self.scan_grid.addWidget(self.label_y_stop, 1, 2, 1, 1)

        self.y_stop = QLineEdit(self.scan_group)
        self.y_stop.setObjectName(u"y_stop")

        self.scan_grid.addWidget(self.y_stop, 1, 3, 1, 1)

        self.label_samples = QLabel(self.scan_group)
        self.label_samples.setObjectName(u"label_samples")

        self.scan_grid.addWidget(self.label_samples, 1, 4, 1, 1)

        self.samples = QLineEdit(self.scan_group)
        self.samples.setObjectName(u"samples")

        self.scan_grid.addWidget(self.samples, 1, 5, 1, 1)

        self.label_x_step = QLabel(self.scan_group)
        self.label_x_step.setObjectName(u"label_x_step")

        self.scan_grid.addWidget(self.label_x_step, 2, 0, 1, 1)

        self.x_step = QLineEdit(self.scan_group)
        self.x_step.setObjectName(u"x_step")

        self.scan_grid.addWidget(self.x_step, 2, 1, 1, 1)

        self.label_y_step = QLabel(self.scan_group)
        self.label_y_step.setObjectName(u"label_y_step")

        self.scan_grid.addWidget(self.label_y_step, 2, 2, 1, 1)

        self.y_step = QLineEdit(self.scan_group)
        self.y_step.setObjectName(u"y_step")

        self.scan_grid.addWidget(self.y_step, 2, 3, 1, 1)

        self.home = QCheckBox(self.scan_group)
        self.home.setObjectName(u"home")

        self.scan_grid.addWidget(self.home, 3, 0, 1, 2)

        self.snake = QCheckBox(self.scan_group)
        self.snake.setObjectName(u"snake")
        self.snake.setChecked(True)

        self.scan_grid.addWidget(self.snake, 3, 2, 1, 2)

        self.show_pos_on_map = QCheckBox(self.scan_group)
        self.show_pos_on_map.setObjectName(u"show_pos_on_map")
        self.show_pos_on_map.setChecked(True)

        self.scan_grid.addWidget(self.show_pos_on_map, 4, 0, 1, 4)


        self.row1.addWidget(self.scan_group)


        self.root_layout.addLayout(self.row1)

        self.row2_buttons = QHBoxLayout()
        self.row2_buttons.setObjectName(u"row2_buttons")
        self.fmove = QHBoxLayout()
        self.fmove.setObjectName(u"fmove")
        self.btn_connect = QPushButton(ScanAppQt)
        self.btn_connect.setObjectName(u"btn_connect")

        self.fmove.addWidget(self.btn_connect)

        self.btn_home = QPushButton(ScanAppQt)
        self.btn_home.setObjectName(u"btn_home")

        self.fmove.addWidget(self.btn_home)

        self.btn_start = QPushButton(ScanAppQt)
        self.btn_start.setObjectName(u"btn_start")

        self.fmove.addWidget(self.btn_start)

        self.btn_stop = QPushButton(ScanAppQt)
        self.btn_stop.setObjectName(u"btn_stop")

        self.fmove.addWidget(self.btn_stop)

        self.btn_selftest = QPushButton(ScanAppQt)
        self.btn_selftest.setObjectName(u"btn_selftest")

        self.fmove.addWidget(self.btn_selftest)


        self.row2_buttons.addLayout(self.fmove)

        self.spacer_buttons_mid = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.row2_buttons.addItem(self.spacer_buttons_mid)

        self.fdata = QHBoxLayout()
        self.fdata.setObjectName(u"fdata")
        self.btn_save = QPushButton(ScanAppQt)
        self.btn_save.setObjectName(u"btn_save")

        self.fdata.addWidget(self.btn_save)

        self.btn_saveplot = QPushButton(ScanAppQt)
        self.btn_saveplot.setObjectName(u"btn_saveplot")

        self.fdata.addWidget(self.btn_saveplot)

        self.btn_savecfg = QPushButton(ScanAppQt)
        self.btn_savecfg.setObjectName(u"btn_savecfg")

        self.fdata.addWidget(self.btn_savecfg)

        self.btn_resetcfg = QPushButton(ScanAppQt)
        self.btn_resetcfg.setObjectName(u"btn_resetcfg")

        self.fdata.addWidget(self.btn_resetcfg)


        self.row2_buttons.addLayout(self.fdata)


        self.root_layout.addLayout(self.row2_buttons)

        self.row3_progress = QHBoxLayout()
        self.row3_progress.setObjectName(u"row3_progress")
        self.lbl_limits = QLabel(ScanAppQt)
        self.lbl_limits.setObjectName(u"lbl_limits")

        self.row3_progress.addWidget(self.lbl_limits)

        self.lbl_status = QLabel(ScanAppQt)
        self.lbl_status.setObjectName(u"lbl_status")

        self.row3_progress.addWidget(self.lbl_status)

        self.spacer_status_progress = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.row3_progress.addItem(self.spacer_status_progress)

        self.progress = QProgressBar(ScanAppQt)
        self.progress.setObjectName(u"progress")
        self.progress.setMaximum(100)

        self.row3_progress.addWidget(self.progress)


        self.root_layout.addLayout(self.row3_progress)

        self.bottom = QHBoxLayout()
        self.bottom.setObjectName(u"bottom")
        self.pos_group = QGroupBox(ScanAppQt)
        self.pos_group.setObjectName(u"pos_group")
        self.pos_group.setMinimumSize(QSize(220, 0))
        self.pos_group.setMaximumSize(QSize(220, 16777215))
        self.pos_grid = QGridLayout(self.pos_group)
        self.pos_grid.setObjectName(u"pos_grid")
        self.label_x_axis = QLabel(self.pos_group)
        self.label_x_axis.setObjectName(u"label_x_axis")

        self.pos_grid.addWidget(self.label_x_axis, 0, 0, 1, 1)

        self.lbl_pos_x = QLabel(self.pos_group)
        self.lbl_pos_x.setObjectName(u"lbl_pos_x")

        self.pos_grid.addWidget(self.lbl_pos_x, 0, 1, 1, 1)

        self.btn_jog_xn = QPushButton(self.pos_group)
        self.btn_jog_xn.setObjectName(u"btn_jog_xn")
        self.btn_jog_xn.setMinimumSize(QSize(28, 0))
        self.btn_jog_xn.setMaximumSize(QSize(28, 16777215))

        self.pos_grid.addWidget(self.btn_jog_xn, 0, 2, 1, 1)

        self.btn_jog_xp = QPushButton(self.pos_group)
        self.btn_jog_xp.setObjectName(u"btn_jog_xp")
        self.btn_jog_xp.setMinimumSize(QSize(28, 0))
        self.btn_jog_xp.setMaximumSize(QSize(28, 16777215))

        self.pos_grid.addWidget(self.btn_jog_xp, 0, 3, 1, 1)

        self.lbl_range_x = QLabel(self.pos_group)
        self.lbl_range_x.setObjectName(u"lbl_range_x")

        self.pos_grid.addWidget(self.lbl_range_x, 1, 1, 1, 1)

        self.ruler_x_holder = QWidget(self.pos_group)
        self.ruler_x_holder.setObjectName(u"ruler_x_holder")

        self.pos_grid.addWidget(self.ruler_x_holder, 2, 0, 1, 4)

        self.label_y_axis = QLabel(self.pos_group)
        self.label_y_axis.setObjectName(u"label_y_axis")

        self.pos_grid.addWidget(self.label_y_axis, 3, 0, 1, 1)

        self.lbl_pos_y = QLabel(self.pos_group)
        self.lbl_pos_y.setObjectName(u"lbl_pos_y")

        self.pos_grid.addWidget(self.lbl_pos_y, 3, 1, 1, 1)

        self.btn_jog_yn = QPushButton(self.pos_group)
        self.btn_jog_yn.setObjectName(u"btn_jog_yn")
        self.btn_jog_yn.setMinimumSize(QSize(28, 0))
        self.btn_jog_yn.setMaximumSize(QSize(28, 16777215))

        self.pos_grid.addWidget(self.btn_jog_yn, 3, 2, 1, 1)

        self.btn_jog_yp = QPushButton(self.pos_group)
        self.btn_jog_yp.setObjectName(u"btn_jog_yp")
        self.btn_jog_yp.setMinimumSize(QSize(28, 0))
        self.btn_jog_yp.setMaximumSize(QSize(28, 16777215))

        self.pos_grid.addWidget(self.btn_jog_yp, 3, 3, 1, 1)

        self.lbl_range_y = QLabel(self.pos_group)
        self.lbl_range_y.setObjectName(u"lbl_range_y")

        self.pos_grid.addWidget(self.lbl_range_y, 4, 1, 1, 1)

        self.ruler_y_holder = QWidget(self.pos_group)
        self.ruler_y_holder.setObjectName(u"ruler_y_holder")

        self.pos_grid.addWidget(self.ruler_y_holder, 5, 0, 1, 4)

        self.label_jog_step = QLabel(self.pos_group)
        self.label_jog_step.setObjectName(u"label_jog_step")

        self.pos_grid.addWidget(self.label_jog_step, 6, 1, 1, 1)

        self.jog_step = QLineEdit(self.pos_group)
        self.jog_step.setObjectName(u"jog_step")
        self.jog_step.setMinimumSize(QSize(56, 0))
        self.jog_step.setMaximumSize(QSize(56, 16777215))

        self.pos_grid.addWidget(self.jog_step, 6, 2, 1, 2)


        self.bottom.addWidget(self.pos_group)

        self.right_split = QSplitter(ScanAppQt)
        self.right_split.setObjectName(u"right_split")
        self.right_split.setOrientation(Qt.Horizontal)
        self.canvas_holder = QWidget(self.right_split)
        self.canvas_holder.setObjectName(u"canvas_holder")
        self.right_split.addWidget(self.canvas_holder)
        self.log_text = QPlainTextEdit(self.right_split)
        self.log_text.setObjectName(u"log_text")
        self.log_text.setMaximumBlockCount(5000)
        self.log_text.setReadOnly(True)
        self.right_split.addWidget(self.log_text)

        self.bottom.addWidget(self.right_split)


        self.root_layout.addLayout(self.bottom)


        self.retranslateUi(ScanAppQt)

        QMetaObject.connectSlotsByName(ScanAppQt)
    # setupUi

    def retranslateUi(self, ScanAppQt):
        ScanAppQt.setWindowTitle(QCoreApplication.translate("ScanAppQt", u"EtherCAT \u53cc\u8f74\u6ed1\u53f0\u626b\u63cf\u91c7\u96c6 (PySide6)", None))
        self.hw_group.setTitle(QCoreApplication.translate("ScanAppQt", u"\u786c\u4ef6\u8fde\u63a5", None))
        self.dry_run.setText(QCoreApplication.translate("ScanAppQt", u"\u6a21\u62df\u8fd0\u884c (dry-run)", None))
        self.label_hw_ifname.setText(QCoreApplication.translate("ScanAppQt", u"\u7f51\u5361", None))
        self.label_x_alias.setText(QCoreApplication.translate("ScanAppQt", u"X \u7ad9\u53f7", None))
        self.x_alias.setText(QCoreApplication.translate("ScanAppQt", u"0", None))
        self.label_y_alias.setText(QCoreApplication.translate("ScanAppQt", u"Y \u7ad9\u53f7", None))
        self.y_alias.setText(QCoreApplication.translate("ScanAppQt", u"1", None))
        self.label_x_ppmm.setText(QCoreApplication.translate("ScanAppQt", u"X \u8109\u51b2/mm", None))
        self.x_ppmm.setText(QCoreApplication.translate("ScanAppQt", u"200", None))
        self.label_y_ppmm.setText(QCoreApplication.translate("ScanAppQt", u"Y \u8109\u51b2/mm", None))
        self.y_ppmm.setText(QCoreApplication.translate("ScanAppQt", u"200", None))
        self.x_reverse.setText(QCoreApplication.translate("ScanAppQt", u"X \u53cd\u5411", None))
        self.y_reverse.setText(QCoreApplication.translate("ScanAppQt", u"Y \u53cd\u5411", None))
        self.pm_group.setTitle(QCoreApplication.translate("ScanAppQt", u"\u529f\u7387\u8ba1 (PM100USB + PD300R)", None))
        self.pm_use_real.setText(QCoreApplication.translate("ScanAppQt", u"\u771f\u5b9e\u529f\u7387\u8ba1 (PM100USB)", None))
        self.label_pm_resource.setText(QCoreApplication.translate("ScanAppQt", u"\u8d44\u6e90\u540d", None))
        self.label_pm_wavelength.setText(QCoreApplication.translate("ScanAppQt", u"\u6ce2\u957f(nm)", None))
        self.label_pm_hint.setText(QCoreApplication.translate("ScanAppQt", u"(\u8d44\u6e90\u540d\u7559\u7a7a\u81ea\u52a8\u641c\u7d22\uff1b\u6ce2\u957f\u7559\u7a7a\u7528\u63a2\u5934\u5f53\u524d\u6821\u51c6)", None))
        self.home_group.setTitle(QCoreApplication.translate("ScanAppQt", u"\u56de\u96f6\u4e0e\u9650\u4f4d (mm\uff0c\u76f8\u5bf9\u539f\u70b9)", None))
        self.label_x_home_method.setText(QCoreApplication.translate("ScanAppQt", u"X \u56de\u96f6\u65b9\u5f0f", None))
        self.x_home_method.setItemText(0, QCoreApplication.translate("ScanAppQt", u"17", None))
        self.x_home_method.setItemText(1, QCoreApplication.translate("ScanAppQt", u"18", None))
        self.x_home_method.setItemText(2, QCoreApplication.translate("ScanAppQt", u"24", None))
        self.x_home_method.setItemText(3, QCoreApplication.translate("ScanAppQt", u"29", None))

        self.label_x_min.setText(QCoreApplication.translate("ScanAppQt", u"X \u8f6f\u9650\u4f4d", None))
        self.label_x_min_tilde.setText(QCoreApplication.translate("ScanAppQt", u"~", None))
        self.label_y_home_method.setText(QCoreApplication.translate("ScanAppQt", u"Y \u56de\u96f6\u65b9\u5f0f", None))
        self.y_home_method.setItemText(0, QCoreApplication.translate("ScanAppQt", u"17", None))
        self.y_home_method.setItemText(1, QCoreApplication.translate("ScanAppQt", u"18", None))
        self.y_home_method.setItemText(2, QCoreApplication.translate("ScanAppQt", u"24", None))
        self.y_home_method.setItemText(3, QCoreApplication.translate("ScanAppQt", u"29", None))

        self.label_y_min.setText(QCoreApplication.translate("ScanAppQt", u"Y \u8f6f\u9650\u4f4d", None))
        self.label_y_min_tilde.setText(QCoreApplication.translate("ScanAppQt", u"~", None))
        self.scan_group.setTitle(QCoreApplication.translate("ScanAppQt", u"\u626b\u63cf\u53c2\u6570 (mm)", None))
        self.label_x_start.setText(QCoreApplication.translate("ScanAppQt", u"X \u8d77\u70b9", None))
        self.x_start.setText(QCoreApplication.translate("ScanAppQt", u"-10", None))
        self.label_y_start.setText(QCoreApplication.translate("ScanAppQt", u"Y \u8d77\u70b9", None))
        self.y_start.setText(QCoreApplication.translate("ScanAppQt", u"-10", None))
        self.label_dwell.setText(QCoreApplication.translate("ScanAppQt", u"\u505c\u7559(s)", None))
        self.dwell.setText(QCoreApplication.translate("ScanAppQt", u"0.1", None))
        self.label_x_stop.setText(QCoreApplication.translate("ScanAppQt", u"X \u7ec8\u70b9", None))
        self.x_stop.setText(QCoreApplication.translate("ScanAppQt", u"10", None))
        self.label_y_stop.setText(QCoreApplication.translate("ScanAppQt", u"Y \u7ec8\u70b9", None))
        self.y_stop.setText(QCoreApplication.translate("ScanAppQt", u"10", None))
        self.label_samples.setText(QCoreApplication.translate("ScanAppQt", u"\u6bcf\u70b9\u91c7\u6837", None))
        self.samples.setText(QCoreApplication.translate("ScanAppQt", u"1", None))
        self.label_x_step.setText(QCoreApplication.translate("ScanAppQt", u"X \u6b65\u957f", None))
        self.x_step.setText(QCoreApplication.translate("ScanAppQt", u"1", None))
        self.label_y_step.setText(QCoreApplication.translate("ScanAppQt", u"Y \u6b65\u957f", None))
        self.y_step.setText(QCoreApplication.translate("ScanAppQt", u"1", None))
        self.home.setText(QCoreApplication.translate("ScanAppQt", u"\u626b\u63cf\u524d\u56de\u96f6", None))
        self.snake.setText(QCoreApplication.translate("ScanAppQt", u"\u86c7\u5f62", None))
        self.show_pos_on_map.setText(QCoreApplication.translate("ScanAppQt", u"\u70ed\u529b\u56fe\u663e\u793a\u4f4d\u7f6e\u6807\u8bb0", None))
        self.btn_connect.setText(QCoreApplication.translate("ScanAppQt", u"\u8fde\u63a5", None))
        self.btn_home.setText(QCoreApplication.translate("ScanAppQt", u"\u56de\u96f6", None))
        self.btn_start.setText(QCoreApplication.translate("ScanAppQt", u"\u5f00\u59cb\u626b\u63cf", None))
        self.btn_stop.setText(QCoreApplication.translate("ScanAppQt", u"\u505c\u6b62", None))
        self.btn_selftest.setText(QCoreApplication.translate("ScanAppQt", u"\u81ea\u68c0", None))
        self.btn_save.setText(QCoreApplication.translate("ScanAppQt", u"\u4fdd\u5b58CSV", None))
        self.btn_saveplot.setText(QCoreApplication.translate("ScanAppQt", u"\u4fdd\u5b58\u70ed\u529b\u56fe", None))
        self.btn_savecfg.setText(QCoreApplication.translate("ScanAppQt", u"\u4fdd\u5b58\u914d\u7f6e", None))
        self.btn_resetcfg.setText(QCoreApplication.translate("ScanAppQt", u"\u6062\u590d\u9ed8\u8ba4", None))
        self.lbl_limits.setText(QCoreApplication.translate("ScanAppQt", u"\u9650\u4f4d: \u2014", None))
        self.lbl_status.setText(QCoreApplication.translate("ScanAppQt", u"\u672a\u8fde\u63a5", None))
        self.pos_group.setTitle(QCoreApplication.translate("ScanAppQt", u"\u5b9e\u65f6\u4f4d\u7f6e\u4e0e\u8f6f\u9650\u4f4d / \u624b\u52a8\u70b9\u52a8", None))
        self.label_x_axis.setText(QCoreApplication.translate("ScanAppQt", u"X", None))
        self.lbl_pos_x.setText(QCoreApplication.translate("ScanAppQt", u"X: 0.000 mm", None))
        self.btn_jog_xn.setText(QCoreApplication.translate("ScanAppQt", u"-", None))
        self.btn_jog_xp.setText(QCoreApplication.translate("ScanAppQt", u"+", None))
        self.lbl_range_x.setText(QCoreApplication.translate("ScanAppQt", u"\u672a\u8bbe\u7f6e", None))
        self.label_y_axis.setText(QCoreApplication.translate("ScanAppQt", u"Y", None))
        self.lbl_pos_y.setText(QCoreApplication.translate("ScanAppQt", u"Y: 0.000 mm", None))
        self.btn_jog_yn.setText(QCoreApplication.translate("ScanAppQt", u"-", None))
        self.btn_jog_yp.setText(QCoreApplication.translate("ScanAppQt", u"+", None))
        self.lbl_range_y.setText(QCoreApplication.translate("ScanAppQt", u"\u672a\u8bbe\u7f6e", None))
        self.label_jog_step.setText(QCoreApplication.translate("ScanAppQt", u"\u70b9\u52a8\u6b65\u957f(mm)", None))
        self.jog_step.setText(QCoreApplication.translate("ScanAppQt", u"1", None))
    # retranslateUi

