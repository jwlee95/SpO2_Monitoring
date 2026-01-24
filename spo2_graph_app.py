"""!
@file spo2_graph_app.py
@brief SpO2 데이터 파싱, 표시 및 실시간 그래프를 위한 PyQt5 GUI 애플리케이션
@details 이 애플리케이션은 시리얼 포트에서 SpO2 관련 데이터를 읽어 파싱하고,
         사용자 인터페이스의 텍스트 로그와 실시간 그래프에 표시함.

         주요 변경 사항 (2026-01-11):
         - 데이터 소스 선택 기능 제거 (시리얼 포트 전용으로 변경)
         - Start/Stop 버튼 통합 (Toggle 방식) 및 UI 영문화
         - 그래프 우측에 SpO2, HR(BPM) 표시용 대형 LCD 위젯 추가
         - 그래프 초기화 시 dummy 데이터를 추가하여 즉시 스크롤 효과 적용
         - 그래프 줌/팬 동작 시 Display Points와 스크롤바 동기화 로직 추가
         - 파싱 로직 개선 (결측치 처리 및 상태 코드 파싱 강화)

         주요 변경 사항 (2026-01-12):
         - 듀얼 시리얼 포트 지원 (Main Port: SpO2, Sub Port: O2/CO2)
         - Port 2 데이터(100Hz)를 Port 1(0.5Hz) 주기에 맞춰 평균화 및 동기화
         - 그래프 우측에 O2 Sat, CO2 Sat 표시용 대형 LCD 위젯 추가
         - 그래프 Y축 통합 (0~200) 및 Port 2 데이터(점선) 추가
         - 데이터 로깅 기능 추가 (CSV 저장, Subject No/Comment 입력)
         - CSV 헤더 및 파일명 형식 지정 (Subject_No_YYMMDD_HHMM.csv)

         주요 변경 사항 (2026-01-24):
         - SpO2 EST 라벨을 Est. SpO2로 변경 및 그래프에 빨간색 점선으로 데이터 추가
         - LCD 디스플레이 위젯을 QLabel로 변경하여 폰트 크기 확대 (32pt) 및 가독성 개선

@author User (JeongWhan Lee)
@date 2025-11-30
@version 1.3.0
"""

import sys
import re
import time
import csv
import os
import serial
import serial.tools.list_ports
from collections import deque
import bisect
from itertools import islice

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QComboBox, QPushButton, QTextEdit, QLabel, QLineEdit, QSpinBox,
                             QGroupBox, QStatusBar, QTabWidget, QScrollBar, QLCDNumber, QCheckBox, QGridLayout, QMessageBox, QFileDialog, QDoubleSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, QObject, Qt, QTimer, QDateTime
import pyqtgraph as pg
from sp02_sensor_converter import GasSensorConverter
from spo2_serveringhaus import RespiratoryGasAnalyzer

## @var STATUS_DEFINITIONS 상태 코드 정의 (Table 5-3 기준)
STATUS_DEFINITIONS = {
    "AO": "Alarm off", "AS": "Alarm silence", "BU": "Battery in use", "LB": "Low battery",
    "LM": "Loss of pulse with patient motion", "LP": "Loss of pulse", "ID": "Patient motion detected",
    "MO": "Patient motion", "PH": "Pulse rate upper limit alarm", "PL": "Pulse rate lower limit alarm",
    "PS": "Pulse search", "SD": "Sensor disconnect", "SH": "Saturation rate upper limit alarm",
    "SL": "Saturation rate lower limit alarm", "SO": "Sensor off"
}

def parse_serial_line(line):
    """!
    @brief 시리얼 데이터 한 줄을 파싱하여 SpO2 관련 정보를 추출합니다.
    @param line 파싱할 시리얼 데이터 문자열 한 줄.
    @return 파싱된 데이터가 담긴 딕셔너리 객체. 형식이 맞지 않으면 None을 반환합니다.
    """
    pattern = (
        r"(\d{2}-[A-Za-z]{3}-\d{2})\s+"
        r"(\d{2}:\d{2}:\d{2})\s+"
        r"([-\d]+)\s+([-\d]+)\s+([-\d]+)\s*"
        r"(.*)"   # 상태코드 유무와 상관없이 매칭
    )
    match = re.search(pattern, line)
    if match:
        date_str, time_str, spo2_str, bpm_str, pa_str, status_raw = match.groups()

        def safe_int(val):
            if val == '---':
                return 0
            return int(val) if val.isdigit() else 0

        status_raw = status_raw.strip()
        codes = status_raw.split() if status_raw else []
        status_messages = [STATUS_DEFINITIONS.get(code, f"Unknown Code({code})") for code in codes]
        return {
            "timestamp": f"{date_str} {time_str}",
            "date_device": date_str, "time_device": time_str,
            "spo2": safe_int(spo2_str), "bpm": safe_int(bpm_str), "pa": safe_int(pa_str),
            "raw_spo2": spo2_str, "raw_bpm": bpm_str, "raw_pa": pa_str,
            "status_codes": codes, "status_msg": ", ".join(status_messages) if status_messages else "",
            "raw": line
        }
    return None

class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [QDateTime.fromMSecsSinceEpoch(int(v * 1000)).toString("HH:mm:ss") for v in values]

class DataProcessor(QObject):
    """!
    @brief 백그라운드에서 데이터 처리를 담당하는 워커 클래스.
    """
    data_received = pyqtSignal(int, dict)
    finished = pyqtSignal()
    status_update = pyqtSignal(str)

    def __init__(self, port, baudrate, source_id):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.source_id = source_id
        self._is_running = True

    def run(self):
        """!
        @brief 선택된 소스에 따라 데이터 처리를 시작합니다.
        """
        self._is_running = True
        self.process_serial()
        self.finished.emit()

    def process_serial(self):
        """!
        @brief 시리얼 포트에서 데이터를 읽고 파싱하여 시그널을 발생시킵니다.
        """
        port = self.port
        baudrate = self.baudrate
        ser = None
        try:
            ser = serial.Serial(port, baudrate, timeout=1)
            self.status_update.emit(f"'{port}' @ {baudrate}bps 연결됨. 데이터 수신 대기 중...")
            while self._is_running:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    parsed_data = parse_serial_line(line)
                    if parsed_data:
                        self.data_received.emit(self.source_id, parsed_data)
                    else:
                        # 파싱 실패 시 원본 데이터 전송
                        self.data_received.emit(self.source_id, {'raw': line})
            self.status_update.emit("시리얼 포트 연결 해제됨.")
        except serial.SerialException as e:
            self.status_update.emit(f"시리얼 오류: {e}")
        finally:
            if ser and ser.is_open:
                ser.close()

    def stop(self):
        """!
        @brief 데이터 처리 루프를 중지시킵니다.
        """
        self._is_running = False

class SpO2MonitorApp(QMainWindow):
    """!
    @brief 메인 애플리케이션 윈도우 클래스.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SpO2 데이터 모니터 및 그래프")
        self.setGeometry(100, 100, 900, 700)

        self.worker_thread1 = None
        self.data_processor1 = None
        self.worker_thread2 = None
        self.data_processor2 = None
        self.start_time = 0
        self.updating_from_code = False
        
        # 화면 갱신을 위한 타이머 및 변수 초기화
        self.plot_update_timer = QTimer()
        self.plot_update_timer.timeout.connect(self.update_gui_components)
        self.temp_data_buffer = []
        self.port2_accum = []
        self.last_port2_avg = {'O2_Sat': 0, 'CO2_Sat': 0}
        self.csv_file = None
        self.csv_writer = None

        # --- 가스 분석기 및 변환기 초기화 ---
        self.gas_converter = GasSensorConverter()
        self.gas_analyzer = RespiratoryGasAnalyzer()

        # --- 데이터 저장소 초기화 ---
        self.time_data = deque()
        self.spo2_data = deque()
        self.bpm_data = deque()
        self.pa_data = deque()
        self.o2_sat_data = deque()
        self.co2_sat_data = deque()
        self.est_spo2_data = deque()

        # --- UI 구성 ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 시리얼 설정 그룹
        serial_group = QGroupBox("Serial Settings")
        serial_layout = QGridLayout()
        
        # Port 1 Controls
        self.connection_status_led1 = QLabel()
        self.connection_status_led1.setFixedSize(16, 16)
        self.connection_status_led1.setStyleSheet("background-color: red; border-radius: 8px;")
        self.port1_combo = QComboBox()
        self.baud1_combo = QComboBox()
        self.baud1_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baud1_combo.setCurrentText('115200')

        # Port 2 Controls
        self.connection_status_led2 = QLabel()
        self.connection_status_led2.setFixedSize(16, 16)
        self.connection_status_led2.setStyleSheet("background-color: red; border-radius: 8px;")
        self.port2_combo = QComboBox()
        self.baud2_combo = QComboBox()
        self.baud2_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baud2_combo.setCurrentText('115200')

        self.scan_button = QPushButton("Scan Ports")

        # Layout - Row 0 (Port 1)
        serial_layout.addWidget(self.connection_status_led1, 0, 0)
        serial_layout.addWidget(QLabel("Main Port:"), 0, 1)
        serial_layout.addWidget(self.port1_combo, 0, 2)
        serial_layout.addWidget(QLabel("Baud 1:"), 0, 3)
        serial_layout.addWidget(self.baud1_combo, 0, 4)

        # Layout - Row 1 (Port 2)
        serial_layout.addWidget(self.connection_status_led2, 1, 0)
        serial_layout.addWidget(QLabel("Sub Port:"), 1, 1)
        serial_layout.addWidget(self.port2_combo, 1, 2)
        serial_layout.addWidget(QLabel("Baud 2:"), 1, 3)
        serial_layout.addWidget(self.baud2_combo, 1, 4)

        # Scan Button
        serial_layout.addWidget(self.scan_button, 0, 5, 2, 1)
        
        # Add stretch to push widgets to the left
        serial_layout.setColumnStretch(6, 1)
        
        serial_group.setLayout(serial_layout)

        # Logging Info Group
        logging_group = QGroupBox("Logging Info")
        logging_layout = QGridLayout()
        
        self.subject_no_input = QLineEdit("0000")
        self.comment_input = QLineEdit("설명")

        # Log Directory UI
        self.log_dir = os.getcwd()
        self.log_dir_input = QLineEdit(self.log_dir)
        self.log_dir_input.setReadOnly(True)
        self.change_dir_button = QPushButton("Change")
        self.change_dir_button.clicked.connect(self.change_log_directory)
        
        logging_layout.addWidget(QLabel("Subject No:"), 0, 0)
        logging_layout.addWidget(self.subject_no_input, 0, 1, 1, 2)
        logging_layout.addWidget(QLabel("Comment:"), 1, 0)
        logging_layout.addWidget(self.comment_input, 1, 1, 1, 2)
        logging_layout.addWidget(QLabel("Log Folder:"), 2, 0)
        logging_layout.addWidget(self.log_dir_input, 2, 1)
        logging_layout.addWidget(self.change_dir_button, 2, 2)
        
        logging_group.setLayout(logging_layout)

        # 제어 버튼
        control_layout = QHBoxLayout()
        self.start_button = QPushButton("Start(Connect)")
        self.start_button.setCheckable(True)
        self.clear_button = QPushButton("Clear Screen")
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.clear_button)
        
        # 환경 변수 설정 (체온, 센서 온도, 습도)
        control_layout.addSpacing(15)
        control_layout.addWidget(QLabel("Body Temp(°C):"))
        self.body_temp_spin = QDoubleSpinBox()
        self.body_temp_spin.setRange(30.0, 45.0)
        self.body_temp_spin.setValue(37.0)
        self.body_temp_spin.setSingleStep(0.1)
        control_layout.addWidget(self.body_temp_spin)

        control_layout.addWidget(QLabel("Sensor Temp(°C):"))
        self.sensor_temp_spin = QDoubleSpinBox()
        self.sensor_temp_spin.setRange(-10.0, 60.0)
        self.sensor_temp_spin.setValue(25.0)
        self.sensor_temp_spin.setSingleStep(0.1)
        control_layout.addWidget(self.sensor_temp_spin)

        control_layout.addWidget(QLabel("Sensor Humid(%):"))
        self.sensor_humid_spin = QDoubleSpinBox()
        self.sensor_humid_spin.setRange(0.0, 100.0)
        self.sensor_humid_spin.setValue(60.0)
        self.sensor_humid_spin.setSingleStep(1.0)
        control_layout.addWidget(self.sensor_humid_spin)

        # 값 변경 시 즉시 재계산 연결
        self.body_temp_spin.valueChanged.connect(self.recalculate_current_spo2)
        self.sensor_temp_spin.valueChanged.connect(self.recalculate_current_spo2)
        self.sensor_humid_spin.valueChanged.connect(self.recalculate_current_spo2)

        control_layout.addStretch()

        # Recording Controls
        self.record_led = QLabel()
        self.record_led.setFixedSize(16, 16)
        self.record_led.setStyleSheet("background-color: gray; border-radius: 8px;")
        self.record_button = QPushButton("Start Recording")
        self.record_button.setCheckable(True)
        self.record_button.clicked.connect(self.toggle_recording)
        self.record_button.setEnabled(False)
        control_layout.addWidget(self.record_led)
        control_layout.addWidget(self.record_button)

        # 탭 위젯 생성
        self.tabs = QTabWidget()
        self.tab_log = QWidget()
        self.tab_graph = QWidget()
        self.tabs.addTab(self.tab_log, "Data Log")
        self.tabs.addTab(self.tab_graph, "Real-time Graph")

        # 데이터 로그 탭 UI
        log_layout = QHBoxLayout(self.tab_log)
        
        self.data_display1 = QTextEdit()
        self.data_display1.setReadOnly(True)
        self.data_display1.setFontFamily("Courier")
        self.data_display1.setPlaceholderText("Port 1 Data Log")
        
        self.data_display2 = QTextEdit()
        self.data_display2.setReadOnly(True)
        self.data_display2.setFontFamily("Courier")
        self.data_display2.setPlaceholderText("Port 2 Data Log")

        log_layout.addWidget(self.data_display1, 7)
        log_layout.addWidget(self.data_display2, 3)

        # 그래프 탭 UI
        graph_layout = QVBoxLayout(self.tab_graph)
        
        # 그래프 제어 UI
        graph_control_layout = QHBoxLayout()
        graph_control_layout.addWidget(QLabel("Display Buffer:"))
        self.points_spinbox = QSpinBox()
        self.points_spinbox.setRange(10, 10000)
        self.points_spinbox.setValue(100)
        self.points_spinbox.setSingleStep(10)
        graph_control_layout.addWidget(self.points_spinbox)

        self.buffer_duration_label = QLabel()
        graph_control_layout.addWidget(self.buffer_duration_label)
        self.update_buffer_duration_label(self.points_spinbox.value())

        self.auto_scale_check = QCheckBox("Auto Scale")
        self.auto_scale_check.stateChanged.connect(self.toggle_auto_scale)
        graph_control_layout.addWidget(self.auto_scale_check)

        graph_control_layout.addStretch(1)
        graph_layout.addLayout(graph_control_layout)

        # 그래프 영역 레이아웃 (그래프 + LCD)
        graph_area_layout = QHBoxLayout()

        # 왼쪽: 그래프 및 스크롤바
        plot_area_layout = QVBoxLayout()
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        plot_area_layout.addWidget(self.plot_widget)
        self.scroll_bar = QScrollBar(Qt.Horizontal)
        plot_area_layout.addWidget(self.scroll_bar)
        graph_area_layout.addLayout(plot_area_layout, 1)
        graph_area_layout.addSpacing(30)

        # 오른쪽: LCD 디스플레이
        lcd_layout = QVBoxLayout()
        
        # 공통 스타일 정의 (폰트 크기 32pt로 설정하여 숫자 크게 표시)
        lcd_style = "background-color: black; border: 1px solid gray; font-size: 32pt; font-weight: bold;"
        
        self.est_spo2_lcd = QLabel("0.00")
        self.est_spo2_lcd.setAlignment(Qt.AlignCenter)
        self.est_spo2_lcd.setStyleSheet(lcd_style + " color: yellow;")
        self.est_spo2_lcd.setMinimumHeight(80)

        self.spo2_lcd = QLabel("0")
        self.spo2_lcd.setAlignment(Qt.AlignCenter)
        self.spo2_lcd.setStyleSheet(lcd_style + " color: red;")
        self.spo2_lcd.setMinimumHeight(80)

        self.bpm_lcd = QLabel("0")
        self.bpm_lcd.setAlignment(Qt.AlignCenter)
        self.bpm_lcd.setStyleSheet(lcd_style + " color: green;")
        self.bpm_lcd.setMinimumHeight(80)
        
        self.o2_sat_lcd = QLabel("0.00")
        self.o2_sat_lcd.setAlignment(Qt.AlignCenter)
        self.o2_sat_lcd.setStyleSheet(lcd_style + " color: magenta;")
        self.o2_sat_lcd.setMinimumHeight(80)

        self.co2_sat_lcd = QLabel("0.00")
        self.co2_sat_lcd.setAlignment(Qt.AlignCenter)
        self.co2_sat_lcd.setStyleSheet(lcd_style + " color: cyan;")
        self.co2_sat_lcd.setMinimumHeight(80)

        lcd_layout.addWidget(QLabel("Est. SpO2 (%)"))
        lcd_layout.addWidget(self.est_spo2_lcd)
        lcd_layout.addSpacing(20)
        lcd_layout.addWidget(QLabel("SpO2 (%)"))
        lcd_layout.addWidget(self.spo2_lcd)
        lcd_layout.addSpacing(20)
        lcd_layout.addWidget(QLabel("HR (BPM)"))
        lcd_layout.addWidget(self.bpm_lcd)
        lcd_layout.addSpacing(20)
        lcd_layout.addWidget(QLabel("O2 Sat (P2)"))
        lcd_layout.addWidget(self.o2_sat_lcd)
        lcd_layout.addSpacing(20)
        lcd_layout.addWidget(QLabel("CO2 Sat (P2)"))
        lcd_layout.addWidget(self.co2_sat_lcd)
        lcd_layout.addStretch()
        graph_area_layout.addLayout(lcd_layout)

        graph_layout.addLayout(graph_area_layout)
        self.setup_graph()

        # 상태 표시줄
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 레이아웃에 위젯 추가
        top_layout = QHBoxLayout()
        top_layout.addWidget(serial_group, 2)
        top_layout.addWidget(logging_group, 1)
        
        layout.addLayout(top_layout)
        layout.addLayout(control_layout)
        layout.addWidget(self.tabs)

        # 종료 버튼
        bottom_layout = QHBoxLayout()
        self.about_button = QPushButton("About")
        bottom_layout.addWidget(self.about_button)
        bottom_layout.addStretch(1)
        self.exit_button = QPushButton("Exit")
        bottom_layout.addWidget(self.exit_button)
        layout.addLayout(bottom_layout)

        # --- 시그널 및 슬롯 연결 ---
        self.scan_button.clicked.connect(self.scan_serial_ports)
        self.start_button.clicked.connect(self.toggle_processing)
        self.clear_button.clicked.connect(self.clear_display_and_graph)
        self.about_button.clicked.connect(self.show_about_dialog)
        self.exit_button.clicked.connect(self.close)
        self.scroll_bar.valueChanged.connect(self.update_plot_view)
        self.points_spinbox.valueChanged.connect(self.on_points_changed)

        self.scan_serial_ports()
        self.update_status("준비 완료.")
        
        # 초기 화면 구성을 위해 더미 데이터로 그래프 초기화
        self.clear_display_and_graph()

    def setup_graph(self):
        """!
        @brief 그래프 위젯의 초기 설정을 구성합니다.
        """
        self.plot_widget.setTitle("Real-time Sensor Data", color="k", size="15pt")
        self.plot_widget.setLabel('left', 'Value', color='k')
        self.plot_widget.setLabel('bottom', 'Data Point', color='k')
        
        # 범례(legend)를 추가하고 수평 방향으로 설정합니다.
        self.plot_widget.addLegend(offset=(10, 10)).setColumnCount(3)
        
        self.plot_widget.showGrid(x=True, y=True)

        # Y축의 범위를 0에서 200으로 고정합니다.
        self.plot_widget.setYRange(0, 200)

        self.spo2_curve = self.plot_widget.plot(pen=pg.mkPen(color=(255, 0, 0), width=2), name='<span style="font-size: 12pt">SpO2 (%)</span>')
        self.bpm_curve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 255, 0), width=2), name='<span style="font-size: 12pt">PR (BPM)</span>')
        self.pa_curve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 0, 255), width=2), name='<span style="font-size: 12pt">PA</span>')
        self.est_spo2_curve = self.plot_widget.plot(pen=pg.mkPen(color=(255, 0, 0), width=2, style=Qt.DashLine), name='<span style="font-size: 12pt">Est. SpO2 (%)</span>')
        self.o2_sat_curve = self.plot_widget.plot(pen=pg.mkPen(color=(255, 0, 255), width=2, style=Qt.DashLine), name='<span style="font-size: 12pt">O2 Sat (P2)</span>')
        self.co2_sat_curve = self.plot_widget.plot(pen=pg.mkPen(color=(0, 255, 255), width=2, style=Qt.DashLine), name='<span style="font-size: 12pt">CO2 Sat (P2)</span>')

        # 그래프를 빈 데이터로 초기화하여 오류 방지
        self.spo2_curve.setData([], [])
        self.bpm_curve.setData([], [])
        self.pa_curve.setData([], [])
        self.est_spo2_curve.setData([], [])
        self.o2_sat_curve.setData([], [])
        self.co2_sat_curve.setData([], [])

        # 뷰 범위 변경 시그널 연결 (줌/팬 시 포인트 수 업데이트)
        self.plot_widget.plotItem.sigRangeChanged.connect(self.on_view_range_changed)

    def scan_serial_ports(self):
        self.port1_combo.clear()
        self.port2_combo.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.update_status("사용 가능한 시리얼 포트가 없습니다.")
        else:
            port_names = [port.device for port in ports]
            self.port1_combo.addItems(port_names)
            self.port2_combo.addItems(port_names)
            self.update_status(f"{len(ports)}개의 시리얼 포트를 찾았습니다.")

    def toggle_processing(self):
        if self.start_button.isChecked():
            self.start_processing()
        else:
            self.stop_processing()

    def change_log_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Log Directory", self.log_dir)
        if dir_path:
            self.log_dir = dir_path
            self.log_dir_input.setText(self.log_dir)

    def toggle_recording(self):
        if self.record_button.isChecked():
            # Start Recording
            subject_no = self.subject_no_input.text().strip()
            
            if not subject_no:
                QMessageBox.warning(self, "Warning", "Please enter Subject No.")
                self.record_button.setChecked(False)
                return

            timestamp = QDateTime.currentDateTime().toString("yyMMdd_HHmm")
            filename = f"Subject_{subject_no}_{timestamp}.csv"
            full_path = os.path.join(self.log_dir, filename)
            
            try:
                self.csv_file = open(full_path, 'w', newline='', encoding='utf-8')
                self.csv_writer = csv.writer(self.csv_file)
                self.csv_writer.writerow(["Subject No", subject_no, "Comment", self.comment_input.text().strip(), "Sampling Rate", "2Hz"])
                header = ["Date(Comp)", "Time(Comp)", "CO2(%)", "O2(%)", "EstSpO2", "Date(PulseOx)", "Time(PulseOx)", "SpO2", "HR", "PA", "PulseOx Raw"]
                self.csv_writer.writerow(header)
                
                self.record_button.setText("Stop Recording")
                self.record_led.setStyleSheet("background-color: red; border-radius: 8px;")
                self.update_status(f"Recording started: {full_path}")
            except Exception as e:
                self.update_status(f"Failed to start recording: {e}")
                self.record_button.setChecked(False)
        else:
            # Stop Recording
            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None
                self.csv_writer = None
            
            self.record_button.setText("Start Recording")
            self.record_led.setStyleSheet("background-color: gray; border-radius: 8px;")
            self.update_status("Recording stopped.")

    def start_processing(self):
        self.clear_display_and_graph()
        self.start_time = time.time()
        started_any = False

        # Port 1 Connection
        if self.port1_combo.currentText():
            port1 = self.port1_combo.currentText()
            baud1 = int(self.baud1_combo.currentText())
            
            self.data_processor1 = DataProcessor(port1, baud1, source_id=1)
            self.worker_thread1 = QThread()
            self.data_processor1.moveToThread(self.worker_thread1)
            self.worker_thread1.started.connect(self.data_processor1.run)
            self.data_processor1.finished.connect(self.worker_thread1.quit)
            self.data_processor1.finished.connect(self.data_processor1.deleteLater)
            self.worker_thread1.finished.connect(self.worker_thread1.deleteLater)
            self.worker_thread1.finished.connect(self.on_port1_finished)
            self.data_processor1.data_received.connect(self.update_data)
            self.data_processor1.status_update.connect(self.update_status)
            self.worker_thread1.start()
            self.connection_status_led1.setStyleSheet("background-color: green; border-radius: 8px;")
            started_any = True

        # Port 2 Connection
        if self.port2_combo.currentText():
            port2 = self.port2_combo.currentText()
            baud2 = int(self.baud2_combo.currentText())
            
            self.data_processor2 = DataProcessor(port2, baud2, source_id=2)
            self.worker_thread2 = QThread()
            self.data_processor2.moveToThread(self.worker_thread2)
            self.worker_thread2.started.connect(self.data_processor2.run)
            self.data_processor2.finished.connect(self.worker_thread2.quit)
            self.data_processor2.finished.connect(self.data_processor2.deleteLater)
            self.worker_thread2.finished.connect(self.worker_thread2.deleteLater)
            self.worker_thread2.finished.connect(self.on_port2_finished)
            self.data_processor2.data_received.connect(self.update_data)
            self.data_processor2.status_update.connect(self.update_status)
            self.worker_thread2.start()
            self.connection_status_led2.setStyleSheet("background-color: green; border-radius: 8px;")
            started_any = True

        if not started_any:
            self.update_status("오류: 선택된 시리얼 포트가 없거나 연결할 수 없습니다.")
            self.start_button.setChecked(False)
            return
        
        # 화면 갱신 타이머 시작 (200ms 간격)
        self.plot_update_timer.start(200)
        
        self.start_button.setText("Stop(Disconnect)")
        self.set_controls_enabled(False)
        self.record_button.setEnabled(True)

    def stop_processing(self):
        # Stop Thread 1
        if self.worker_thread1 and self.worker_thread1.isRunning():
            if self.data_processor1:
                self.data_processor1.stop()
            self.worker_thread1.quit()
            self.worker_thread1.wait()
        
        # Stop Thread 2
        if self.worker_thread2 and self.worker_thread2.isRunning():
            if self.data_processor2:
                self.data_processor2.stop()
            self.worker_thread2.quit()
            self.worker_thread2.wait()

        self.plot_update_timer.stop()
        self.update_status("작업 중지됨.")

    def on_port1_finished(self):
        self.connection_status_led1.setStyleSheet("background-color: red; border-radius: 8px;")
        self.worker_thread1 = None
        self.data_processor1 = None
        self.check_processing_finished()

    def on_port2_finished(self):
        self.connection_status_led2.setStyleSheet("background-color: red; border-radius: 8px;")
        self.worker_thread2 = None
        self.data_processor2 = None
        self.check_processing_finished()

    def check_processing_finished(self):
        if not self.worker_thread1 and not self.worker_thread2:
            self.start_button.setChecked(False)
            self.start_button.setText("Start(Connect)")
            self.set_controls_enabled(True)
            
            if self.record_button.isChecked():
                self.record_button.setChecked(False)
                self.toggle_recording()
            self.record_button.setEnabled(False)

    def update_data(self, source_id, data):
        """!
        @brief 수신된 데이터로 로그와 그래프를 모두 업데이트합니다.
        @param data 파싱된 데이터 딕셔너리.
        """
        timestamp = time.time()
        
        if source_id == 2:
            # Port 2: 데이터 버퍼링 (Port 1과 동기화 위해)
            raw_line = data.get('raw', '')
            if raw_line:
                # 숫자 추출 (공백 또는 콤마로 구분된 숫자 가정)
                vals = re.findall(r"[-+]?\d*\.\d+|[-+]?\d+", raw_line)
                if len(vals) >= 2:
                    try:
                        val1 = float(vals[0])
                        val2 = float(vals[1])
                        self.port2_accum.append((val1, val2))
                    except ValueError:
                        pass
        elif source_id == 1:
            self.temp_data_buffer.append((source_id, data, timestamp))
            
            # Port 1 데이터 수신 시, 쌓여있던 Port 2 데이터의 평균 계산 및 출력
            if self.port2_accum:
                count = len(self.port2_accum)
                avg_adc_o2 = sum(v[0] for v in self.port2_accum) / count
                avg_adc_co2 = sum(v[1] for v in self.port2_accum) / count
                
                # 1. ADC -> 가스 농도 변환
                o2_conc = self.gas_converter.get_o2_concentration(avg_adc_o2)
                co2_conc = self.gas_converter.get_co2_concentration(avg_adc_co2)
                
                # 2. 가스 농도 -> SpO2 추정 (UI 입력값 사용)
                spo2_res = self.gas_analyzer.calculate_spo2(
                    sensor_t_c=self.sensor_temp_spin.value(),
                    sensor_rh_pct=self.sensor_humid_spin.value(),
                    o2_pct=o2_conc, co2_pct=co2_conc,
                    body_temp_c=self.body_temp_spin.value()
                )
                est_spo2 = spo2_res['SpO2_Percent']
                
                self.port2_accum.clear()
                self.last_port2_avg = {'O2_Sat': o2_conc, 'CO2_Sat': co2_conc, 'Est_SpO2': est_spo2}
            
            if self.record_button.isChecked() and self.csv_writer:
                self.write_csv_row(data)
            
            self.temp_data_buffer.append((2, self.last_port2_avg, timestamp))

    def write_csv_row(self, data):
        # Date(Comp), Time(Comp)
        now = QDateTime.currentDateTime()
        date_comp = now.toString("yyyy-MM-dd")
        time_comp = now.toString("HH:mm:ss.zzz")

        # CO2(%), O2(%)
        co2 = self.last_port2_avg.get('CO2_Sat', 0)
        o2 = self.last_port2_avg.get('O2_Sat', 0)
        est_spo2_val = self.last_port2_avg.get('Est_SpO2', "")

        # Port 1 Data
        if 'spo2' in data:
            date_pulseox = data['date_device']
            time_pulseox = data['time_device']
            spo2 = data['raw_spo2']
            hr = data['raw_bpm']
            pa = data['raw_pa']
            pulseox_raw = data['raw']
        else:
            # Parsing failed or raw data only
            date_pulseox = ""
            time_pulseox = ""
            spo2 = ""
            hr = ""
            pa = ""
            pulseox_raw = data.get('raw', '')

        row = [date_comp, time_comp, f"{co2:.2f}", f"{o2:.2f}", est_spo2_val, date_pulseox, time_pulseox, spo2, hr, pa, pulseox_raw]
        try:
            self.csv_writer.writerow(row)
            self.csv_file.flush()
        except Exception as e:
            self.update_status(f"CSV Write Error: {e}")

    def recalculate_current_spo2(self):
        """!
        @brief 환경 변수(체온, 온도, 습도) 변경 시 SpO2를 즉시 재계산하여 로그에 표시합니다.
        """
        if not hasattr(self, 'last_port2_avg'):
            return

        o2_conc = self.last_port2_avg.get('O2_Sat', 0)
        co2_conc = self.last_port2_avg.get('CO2_Sat', 0)

        spo2_res = self.gas_analyzer.calculate_spo2(
            sensor_t_c=self.sensor_temp_spin.value(),
            sensor_rh_pct=self.sensor_humid_spin.value(),
            o2_pct=o2_conc, co2_pct=co2_conc,
            body_temp_c=self.body_temp_spin.value()
        )
        est_spo2 = spo2_res['SpO2_Percent']
        self.last_port2_avg['Est_SpO2'] = est_spo2

        # 로그 업데이트
        log_msg = (f"[Update] Body:{self.body_temp_spin.value()}C Env:{self.sensor_temp_spin.value()}C/{self.sensor_humid_spin.value()}% "
                   f"-> Est SpO2: {est_spo2:.2f}%")
        self.data_display2.append(log_msg)

    def update_gui_components(self):
        if not self.temp_data_buffer:
            return

        # 버퍼에 있는 데이터를 가져오고 비움
        current_batch = self.temp_data_buffer[:]
        self.temp_data_buffer.clear()

        has_new_graph_data = False
        latest_data_1 = None
        latest_data_2 = None

        for source_id, data, timestamp in current_batch:
            if source_id == 1:
                # 1. 텍스트 로그 업데이트 (Port 1)
                if 'spo2' in data:
                    display_text = (f"{data['timestamp']:<20} | "
                                    f"SpO2: {data['spo2']:<3} | "
                                    f"PR: {data['bpm']:<3} | "
                                    f"PA: {data['pa']:<3} | "
                                    f"Status: {data['status_msg']}")
                    
                    # 2. 전체 데이터 저장소에 데이터 추가 (Port 1만 그래프 표시)
                    self.spo2_data.append(data['spo2'])
                    self.bpm_data.append(data['bpm'])
                    self.pa_data.append(data['pa'])
                    self.time_data.append(timestamp)
                    has_new_graph_data = True
                    latest_data_1 = data
                else:
                    ts_str = QDateTime.fromMSecsSinceEpoch(int(timestamp * 1000)).toString("HH:mm:ss.zzz")
                    display_text = f"{ts_str} | {data.get('raw', '')}"
                self.data_display1.append(display_text)

            elif source_id == 2:
                # Port 2 데이터 표시 (평균값, 타임스탬프 없음)
                if 'O2_Sat' in data:
                    est_spo2 = data.get('Est_SpO2', 0)
                    display_text = f"O2: {data['O2_Sat']:.2f}% | CO2: {data['CO2_Sat']:.2f}% | Est SpO2: {est_spo2:.2f}%"
                    self.data_display2.append(display_text)
                    self.o2_sat_data.append(data['O2_Sat'])
                    self.co2_sat_data.append(data['CO2_Sat'])
                    self.est_spo2_data.append(est_spo2)
                    latest_data_2 = data
                else:
                    # 예외적인 경우 원본 표시
                    ts_str = QDateTime.fromMSecsSinceEpoch(int(timestamp * 1000)).toString("HH:mm:ss.zzz")
                    display_text = f"{ts_str} | {data.get('raw', '')}"
                    self.data_display2.append(display_text)

        # 3. 최신 데이터로 LCD 업데이트 (Port 1 기준)
        if latest_data_1:
            self.spo2_lcd.setText(str(latest_data_1['spo2']))
            self.bpm_lcd.setText(str(latest_data_1['bpm']))
            
        if latest_data_2:
            self.o2_sat_lcd.setText(f"{latest_data_2['O2_Sat']:.2f}")
            self.co2_sat_lcd.setText(f"{latest_data_2['CO2_Sat']:.2f}")
            if 'Est_SpO2' in latest_data_2:
                self.est_spo2_lcd.setText(f"{latest_data_2['Est_SpO2']:.2f}")

        # 4. 그래프 업데이트 (Port 1 데이터가 있을 때만)
        if has_new_graph_data:
            self.update_plot_view(is_new_data=True)

    def on_points_changed(self, value):
        self.update_plot_view()
        self.scroll_bar.setValue(self.scroll_bar.maximum())
        self.update_buffer_duration_label(value)

    def update_buffer_duration_label(self, value):
        seconds = value * 2
        mm = seconds // 60
        ss = seconds % 60
        self.buffer_duration_label.setText(f"({mm:02d}:{ss:02d})")

    def on_view_range_changed(self, view, ranges):
        """!
        @brief 그래프 뷰 범위가 변경될 때(줌/팬) 호출되어 UI를 동기화합니다.
        """
        if self.updating_from_code:
            return

        if not self.time_data:
            return

        # time_data를 리스트로 변환하여 인덱스 검색
        time_list = list(self.time_data)
        min_x, max_x = ranges[0]
        
        # 현재 뷰 범위에 해당하는 데이터 인덱스 찾기
        start_index = bisect.bisect_left(time_list, min_x)
        end_index = bisect.bisect_right(time_list, max_x)
        
        visible_points = end_index - start_index
        if visible_points < 10: visible_points = 10
        
        self.points_spinbox.blockSignals(True)
        self.points_spinbox.setValue(visible_points)
        self.points_spinbox.blockSignals(False)

        # 스크롤바 범위 업데이트 (setValue 전에 수행하여 클램핑 방지)
        total_points = len(time_list)
        if total_points > visible_points:
            self.scroll_bar.setMaximum(total_points - visible_points)

        self.scroll_bar.blockSignals(True)
        self.scroll_bar.setValue(start_index)
        self.scroll_bar.blockSignals(False)
        
        self.update_plot_view(is_new_data=False)

    def toggle_auto_scale(self, state):
        if state == Qt.Checked:
            self.plot_widget.enableAutoRange(axis='y')
        else:
            self.plot_widget.disableAutoRange(axis='y')
            self.plot_widget.setYRange(0, 200)

    def update_plot_view(self, is_new_data=False):
        """!
        @brief 현재 스크롤 위치와 설정에 맞게 그래프 뷰를 업데이트합니다.
        @param is_new_data 새로운 데이터가 추가되었는지 여부.
        """
        self.updating_from_code = True
        try:
            total_points = len(self.time_data)
            visible_points = self.points_spinbox.value()

            # 스크롤바 범위 및 가시성 설정
            self.scroll_bar.blockSignals(True)
            if total_points > visible_points:
                self.scroll_bar.show()
                was_at_end = self.scroll_bar.value() >= self.scroll_bar.maximum() - 1
                self.scroll_bar.setMaximum(total_points - visible_points)
                if is_new_data and was_at_end:
                    # 자동 스크롤: 스크롤바가 맨 끝에 있을 때만 새 데이터 쪽으로 이동
                    self.scroll_bar.setValue(total_points - visible_points)
            else:
                self.scroll_bar.hide()
                self.scroll_bar.setMaximum(0)
            self.scroll_bar.blockSignals(False)

            start_index = self.scroll_bar.value()
            if total_points <= visible_points:
                start_index = 0
            end_index = start_index + visible_points

            # 현재 뷰에 맞는 데이터 슬라이스 추출 (islice 사용으로 효율성 증대)
            x_slice = list(islice(self.time_data, start_index, end_index))
            spo2_slice = list(islice(self.spo2_data, start_index, end_index))
            bpm_slice = list(islice(self.bpm_data, start_index, end_index))
            pa_slice = list(islice(self.pa_data, start_index, end_index))
            o2_slice = list(islice(self.o2_sat_data, start_index, end_index))
            co2_slice = list(islice(self.co2_sat_data, start_index, end_index))
            est_spo2_slice = list(islice(self.est_spo2_data, start_index, end_index))

            self.spo2_curve.setData(x_slice, spo2_slice, skipFiniteCheck=True)
            self.bpm_curve.setData(x_slice, bpm_slice, skipFiniteCheck=True)
            self.pa_curve.setData(x_slice, pa_slice, skipFiniteCheck=True)
            self.est_spo2_curve.setData(x_slice, est_spo2_slice, skipFiniteCheck=True)
            self.o2_sat_curve.setData(x_slice, o2_slice, skipFiniteCheck=True)
            self.co2_sat_curve.setData(x_slice, co2_slice, skipFiniteCheck=True)
            
            # 오실로스코프 효과: 데이터에 맞춰 X축 범위 이동
            if x_slice:
                self.plot_widget.setXRange(x_slice[0], x_slice[-1], padding=0)
        finally:
            self.updating_from_code = False

    def clear_display_and_graph(self):
        """!
        @brief 데이터 로그와 그래프를 모두 초기화합니다.
        """
        # 1. 텍스트 로그 지우기
        self.data_display1.clear()
        self.data_display2.clear()
        self.port2_accum.clear()

        # 2. 데이터 저장소 비우기
        self.time_data.clear()
        self.spo2_data.clear()
        self.bpm_data.clear()
        self.pa_data.clear()
        self.o2_sat_data.clear()
        self.co2_sat_data.clear()
        self.est_spo2_data.clear()

        # 3. 초기 더미 데이터 채우기 (좌측 스크롤 효과를 위해)
        initial_points = self.points_spinbox.value()
        current_time = time.time()
        for i in range(initial_points):
            t = current_time - ((initial_points - i) * 2)
            self.time_data.append(t)
            self.spo2_data.append(0)
            self.bpm_data.append(0)
            self.pa_data.append(0)
            self.o2_sat_data.append(0)
            self.co2_sat_data.append(0)
            self.est_spo2_data.append(0)

        # 4. 그래프 및 스크롤바 업데이트
        self.update_plot_view(is_new_data=False)
        
        # LCD 초기화
        self.est_spo2_lcd.setText("0.00")
        self.spo2_lcd.setText("0")
        self.bpm_lcd.setText("0")
        self.o2_sat_lcd.setText("0.00")
        self.co2_sat_lcd.setText("0.00")

    def update_status(self, message):
        self.status_bar.showMessage(message)

    def set_controls_enabled(self, enabled):
        self.port1_combo.setEnabled(enabled)
        self.baud1_combo.setEnabled(enabled)
        self.port2_combo.setEnabled(enabled)
        self.baud2_combo.setEnabled(enabled)
        self.scan_button.setEnabled(enabled)

    def show_about_dialog(self):
        QMessageBox.about(self, "About SpO2 Data Monitor",
                          "Breath Gas (CO2/O2), SpO2 Data Monitor & Logger\n"
                          "Version 1.3.0\n\n"
                          "Copyright (c) 2026 JeongWhan Lee\n"
                          "All rights reserved.")

    def closeEvent(self, event):
        self.stop_processing()
        if self.csv_file:
            self.csv_file.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = SpO2MonitorApp()
    window.show()
    sys.exit(app.exec_())