"""!
@file SerialDataPlotter.py
@brief PyQt5기반 GUI, 시리얼 포트로부터 들어오는 데이터를 실시간으로 그래프에 그리고 로그에 표시하는 기능을 수행
@details 실시간 데이터 시각화: 시리얼 포트로 수신되는 숫자 데이터를 pyqtgraph 라이브러리를 사용해 
           실시간 그래프로 표시. 이를 통해 센서 값, 연산 결과 등의 변화를 직관적으로 파악할 수 있음.
         다중 채널 지원: 콤마(,)로 구분된 여러 개의 숫자 데이터를 동시에 수신하여 
           각각 별개의 그래프(채널)로 그릴 수 있음. 
         시리얼 통신 제어: 사용 가능한 시리얼 포트를 자동으로 검색하고, 
           원하는 포트와 통신 속도(Baudrate)를 선택하여 연결하거나 해제할 수 있음. 
         데이터 로깅 및 송신: 수신된 모든 데이터는 텍스트 로그에 기록되며, 사용자가 직접 텍스트를 
           입력하여 시리얼 포트로 데이터를 전송할 수도 있음. 
         데이터 저장 및 캡처:
           실시간으로 수신되는 데이터를 CSV 파일 형식으로 저장하여 나중에 분석할 수 있음.
           현재 화면에 보이는 그래프를 이미지 파일(PNG, JPG)로 캡처하여 저장할 수 있음.

         주요 변경 사항 (2026-01-15):
           - UI 레이아웃 재구성: 컨트롤 패널 그룹화(Plot Settings, Data Actions), 그래프/로그 영역 스플리터 적용.
           - 그래프 기능 강화: Y축 자동 스케일, X축 범위 조절 슬라이더, 선 굵기 조절, 그래프 업데이트 일시정지(Graph 체크박스) 기능 추가.
           - 축 설정 변경: X축을 시간 대신 샘플 인덱스(Sample Index)로 변경, Y축 라벨 수정.
           - 데이터 로깅 개선: 시스템 메시지는 상태바에, 데이터는 로그 박스에 분리 표시. 로그 지우기 버튼 추가.
           - CSV 저장 개선: 저장 시 메타데이터(기록 시간, 샘플링 레이트 등) 헤더 추가 및 샘플 인덱스 기록.

@author User (JeongWhan Lee)
@date 2025-11-30
@version 1.1.0
"""

import sys
import csv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QInputDialog,
                             QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit, QFileDialog, QMessageBox, QCheckBox, QSlider, QSpinBox, QGroupBox, QSplitter)
from PyQt5.QtCore import QTimer, QDateTime, Qt
import pyqtgraph as pg
import pyqtgraph.exporters
import serial
import serial.tools.list_ports

## @class SerialDataPlotter
#  @brief 실시간으로 시리얼 데이터를 받아 그래프로 그리고 CSV 파일로 저장하는 메인 애플리케이션 클래스입니다.
class SerialDataPlotter(QMainWindow):
    ## @brief 클래스 생성자입니다. UI를 초기화하고 필요한 변수들을 설정합니다.
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-time Serial Data Plotter") 
        self.setGeometry(100, 100, 1200, 800)

        # --- Variable Initialization ---
        ## @var serial_port
        #  @brief pyserial 객체
        self.serial_port = None
        ## @var is_saving
        #  @brief CSV 저장(버퍼링) 상태 플래그
        self.is_saving = False
        ## @var csv_buffer
        #  @brief CSV로 저장할 데이터를 임시 보관하는 버퍼
        self.csv_buffer = []
        ## @var data_x
        #  @brief 그래프의 x축 데이터 (시간)
        self.data_x = []
        ## @var data_y
        #  @brief 그래프의 y축 데이터 (값). 다채널 지원을 위해 리스트의 리스트 형태.
        self.data_y = []
        ## @var start_time
        #  @brief 데이터 수신 시작 시간
        self.start_time = 0
        ## @var plot_items
        #  @brief 다채널 그래프의 각 PlotDataItem을 저장하는 리스트
        self.plot_items = []
        ## @var plot_pens
        #  @brief 각 채널 그래프의 색상을 지정하는 펜 리스트
        self.plot_pens = ['y', 'c', 'm', 'r', 'g', 'b', 'w']
        ## @var x_window_size
        #  @brief 그래프 X축 표시 범위 (데이터 포인트 수)
        self.x_window_size = 5000
        ## @var line_width
        #  @brief 그래프 선 굵기
        self.line_width = 2
        
        # --- Saving Metadata ---
        self.save_sample_index = 0
        self.recording_start_timestamp = QDateTime.currentDateTime()
        self.adc_resolution = "12-bit"
        self.input_voltage = "3.3V"

        ## @var data_packets_received
        #  @brief 속도 계산을 위해 마지막 업데이트 이후 수신된 데이터 패킷 수
        self.data_packets_received = 0
        ## @var last_rate_update_time
        #  @brief 마지막으로 속도를 계산한 시간
        self.last_rate_update_time = 0

        # --- Main Widget and Layout Setup ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Title Label ---
        title_label = QLabel("Real-time Serial Data Plotter - KKU-BME v0.1")
        title_label.setStyleSheet("""
            font-family: 'Times New Roman', serif;
            font-size: 24px;
            font-weight: bold;
            font-style: italic;
            padding-left: 10px;
        """)
        title_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(title_label)

        # --- Top Control Panel (Connection) ---
        conn_layout = QHBoxLayout()

        # Serial Port Selection
        self.port_combo = QComboBox()
        conn_layout.addWidget(QLabel("Serial Port:"))
        conn_layout.addWidget(self.port_combo)

        # Scan Button
        self.scan_button = QPushButton("Scan")
        self.scan_button.clicked.connect(self.scan_serial_ports)
        conn_layout.addWidget(self.scan_button)
        
        # Baudrate Selection
        self.baud_rate_combo = QComboBox()
        common_baud_rates = ["9600", "19200", "38400", "57600", "115200"]
        self.baud_rate_combo.addItems(common_baud_rates)
        self.baud_rate_combo.setCurrentText("115200")
        conn_layout.addWidget(QLabel("Baudrate:"))
        conn_layout.addWidget(self.baud_rate_combo)

        # Connect/Disconnect Button
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_button)
        
        # Connection Status LED
        self.connection_status_led = QLabel()
        self.connection_status_led.setFixedSize(16, 16)
        self.connection_status_led.setStyleSheet("background-color: red; border-radius: 8px;")
        conn_layout.addWidget(self.connection_status_led)

        # Rate Display
        self.rate_label = QLabel("Rate: 0.0 Hz")
        self.rate_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #AAAAFF; margin-left: 10px;")
        conn_layout.addWidget(self.rate_label)

        conn_layout.addStretch() # Add spacer
        main_layout.addLayout(conn_layout)

        # --- Second Control Panel (Settings & Actions) ---
        settings_layout = QHBoxLayout()

        # Group 1: Plot Settings
        plot_group = QGroupBox("Plot Settings")
        plot_group_layout = QHBoxLayout()
        plot_group.setLayout(plot_group_layout)

        # X-Axis Range Slider
        self.x_range_label = QLabel(f"X Range: {self.x_window_size}")
        plot_group_layout.addWidget(self.x_range_label)
        self.x_range_slider = QSlider(Qt.Horizontal)
        self.x_range_slider.setRange(100, 10000)
        self.x_range_slider.setValue(self.x_window_size)
        self.x_range_slider.setFixedWidth(100)
        self.x_range_slider.valueChanged.connect(self.update_x_range)
        plot_group_layout.addWidget(self.x_range_slider)

        # Auto Scale Y Checkbox
        self.auto_scale_y_cb = QCheckBox("Auto Scale Y")
        self.auto_scale_y_cb.setChecked(True)
        self.auto_scale_y_cb.stateChanged.connect(self.toggle_auto_scale_y)
        plot_group_layout.addWidget(self.auto_scale_y_cb)

        # Line Width SpinBox
        plot_group_layout.addWidget(QLabel("Width:"))
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(self.line_width)
        self.line_width_spin.valueChanged.connect(self.update_line_width)
        plot_group_layout.addWidget(self.line_width_spin)

        # Graph Update Checkbox
        self.graph_update_cb = QCheckBox("Graph")
        self.graph_update_cb.setChecked(False)
        plot_group_layout.addWidget(self.graph_update_cb)

        settings_layout.addWidget(plot_group)

        # Group 2: Data Actions
        action_group = QGroupBox("Data Actions")
        action_group_layout = QHBoxLayout()
        action_group.setLayout(action_group_layout)

        # CSV Save Button
        self.save_button = QPushButton("Start Saving")
        self.save_button.clicked.connect(self.toggle_saving)
        self.save_button.setEnabled(False)
        action_group_layout.addWidget(self.save_button)

        # Clear Plot Button
        self.clear_button = QPushButton("Clear Plot")
        self.clear_button.clicked.connect(self.clear_plot)
        action_group_layout.addWidget(self.clear_button)

        # Capture Plot Button
        self.capture_button = QPushButton("Capture Plot")
        self.capture_button.clicked.connect(self.capture_plot_as_image)
        action_group_layout.addWidget(self.capture_button)

        settings_layout.addWidget(action_group)
        settings_layout.addStretch()

        main_layout.addLayout(settings_layout)

        # --- Splitter for Graph and Log ---
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)

        # --- Graph Widget ---
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground((60, 60, 60))
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setLabel('left', 'ADC Values(a.u.)')
        self.plot_widget.setLabel('bottom', 'Sample Index(n)')
        self.legend = self.plot_widget.addLegend()
        splitter.addWidget(self.plot_widget)

        # --- Right Side Widget (Log + Input) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Clear Log Button
        self.clear_log_button = QPushButton("Clear Log")
        self.clear_log_button.clicked.connect(self.clear_log)
        right_layout.addWidget(self.clear_log_button)

        # --- Log Text Box ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        right_layout.addWidget(self.log_box)

        # --- Serial Send Input ---
        self.send_input = QLineEdit()
        self.send_input.setPlaceholderText("Type a message and press Enter to send")
        self.send_input.returnPressed.connect(self.send_serial_data)
        self.send_input.setEnabled(False) # Initially disabled
        right_layout.addWidget(self.send_input)

        splitter.addWidget(right_widget)

        # Set initial size ratio (6.5 : 3.5)
        splitter.setSizes([650, 350])
        splitter.setStretchFactor(0, 65)
        splitter.setStretchFactor(1, 35)

        # --- Bottom Layout (Exit Button) ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        # Exit Button
        self.exit_button = QPushButton("Quit")
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setStyleSheet("font-size: 16px; font-weight: bold; color: white; background-color: #555555; border-radius: 10px; padding: 5px 15px;")
        bottom_layout.addWidget(self.exit_button)

        main_layout.addLayout(bottom_layout)

        # --- Status Bar ---
        self.statusBar().showMessage("Ready")

        # --- Data Reception Timer ---
        self.data_timer = QTimer()
        self.data_timer.timeout.connect(self.read_serial_data)

        # --- Rate Update Timer ---
        self.rate_update_timer = QTimer()
        self.rate_update_timer.timeout.connect(self.update_rate_display)


        # Initial scan for ports after all widgets are created
        self.scan_serial_ports()
        self.update_led_status(False)

    ## @brief 연결 상태 LED의 색상을 업데이트합니다.
    #  @param connected True이면 green, False이면 red
    def update_led_status(self, connected):
        if connected:
            self.connection_status_led.setStyleSheet("background-color: green; border-radius: 8px;")
        else:
            self.connection_status_led.setStyleSheet("background-color: red; border-radius: 8px;")

    ## @brief 사용 가능한 시리얼 포트를 스캔하여 콤보박스에 추가합니다.
    def scan_serial_ports(self):
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
        
        # 이전에 선택했던 포트가 여전히 존재하면, 그 포트를 다시 선택
        index = self.port_combo.findText(current_port)
        if index != -1:
            self.port_combo.setCurrentIndex(index)
        
        if not ports:
            self.log_message("No available serial ports found.")
        else:
            self.log_message("Updated serial port list.")


    ## @brief 시리얼 포트 연결 또는 해제를 토글합니다.
    def toggle_connection(self):
        if self.serial_port is None or not self.serial_port.is_open:
            self.connect_serial()
        else:
            self.disconnect_serial()

    ## @brief 시리얼 포트 연결을 처리합니다.
    def connect_serial(self):
        port_name = self.port_combo.currentText()
        baud_rate = self.baud_rate_combo.currentText()

        if not port_name:
            self.log_message("Error: Please select a port.")
            return
        if not baud_rate.isdigit():
            self.log_message("Error: Baudrate must be a number.")
            return

        try:
            self.serial_port = serial.Serial(port_name, int(baud_rate), timeout=0.1)
            self.data_timer.start(50) # 50ms interval for reading data
            self.connect_button.setText("Disconnect")
            self.save_button.setEnabled(True)
            self.send_input.setEnabled(True)
            self.update_led_status(True)
            self.log_message(f"Connected to {port_name} at {baud_rate} bps.")
            # Reset and start rate calculation
            self.data_packets_received = 0
            self.last_rate_update_time = QDateTime.currentDateTime().toMSecsSinceEpoch() / 1000.0
            self.rate_update_timer.start(1000) # Update rate every 1 second
        except serial.SerialException as e:
            self.log_message(f"Error: {e}")
            self.update_led_status(False)

    ## @brief 시리얼 포트 연결을 해제합니다.
    def disconnect_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.data_timer.stop()
            if self.is_saving:
                self.stop_saving() # 버퍼링 중이었다면 저장 여부를 물음
            self.rate_update_timer.stop()
            self.rate_label.setText("Rate: 0.0 Hz")
            self.serial_port.close()
            self.connect_button.setText("Connect")
            self.save_button.setEnabled(False)
            self.send_input.setEnabled(False)
            self.log_message("Disconnected.")
            self.update_led_status(False)

    ## @brief 시리얼 데이터를 읽고 처리합니다.
    def read_serial_data(self):
        if self.serial_port and self.serial_port.is_open:
            while self.serial_port.in_waiting > 0:
                try:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        self.log_box.append(f"> {line}")
                        self.data_packets_received += 1
                        self.update_plot(line)
                        if self.is_saving:
                            self.buffer_csv_data(line)
                except UnicodeDecodeError:
                    self.log_message("UnicodeDecodeError: Could not decode received data.")
    
    ## @brief 입력된 텍스트를 시리얼 포트로 전송합니다.
    def send_serial_data(self):
        if self.serial_port and self.serial_port.is_open:
            data_to_send = self.send_input.text()
            if not data_to_send:
                return # Do not send empty messages
            
            # Add newline character, as many devices expect it
            data_with_newline = data_to_send + '\n'
            try:
                self.serial_port.write(data_with_newline.encode('utf-8'))
                self.log_box.append(f"Sent: {data_to_send}")
                self.send_input.clear()
            except serial.SerialException as e:
                self.log_message(f"Error sending data: {e}")
        else:
            self.log_message("Cannot send data: Not connected.")

    ## @brief 수신된 데이터로 그래프를 업데이트합니다.
    #  @param data_line 수신된 데이터 한 줄 (문자열)
    def update_plot(self, data_line):
        if not self.graph_update_cb.isChecked():
            return

        try:
            # 쉼표로 구분된 데이터 파싱 및 숫자 변환
            values = []
            for part in data_line.split(','):
                try:
                    values.append(float(part.strip()))
                except ValueError:
                    # 숫자로 변환할 수 없는 부분은 무시합니다.
                    pass
            
            # 유효한 숫자 데이터가 없으면 무시
            if not values:
                self.log_message(f"Ignoring non-numeric data: {data_line}")
                return

            num_channels = len(values)

            # --- X축 업데이트 (Sample Index) ---
            if not self.data_x:
                new_x = 0
            else:
                new_x = self.data_x[-1] + 1
            self.data_x.append(new_x)

            # --- 동적 채널/플롯 생성 ---
            while num_channels > len(self.plot_items):
                new_channel_index = len(self.plot_items)
                color_code = self.plot_pens[new_channel_index % len(self.plot_pens)]
                pen = pg.mkPen(color=color_code, width=self.line_width)
                name = f'Value {new_channel_index + 1}'
                plot_item = self.plot_widget.plot(pen=pen, name=name)
                
                # 범례 항목에 더블 클릭 이벤트 연결
                self.make_legend_item_editable(plot_item, name)
                self.plot_items.append(plot_item)
                self.data_y.append([])

            # --- Y축 데이터 추가 ---
            for i in range(num_channels):
                self.data_y[i].append(values[i])
            
            # 데이터가 수신되지 않은 채널은 이전 값으로 채움
            for i in range(num_channels, len(self.plot_items)):
                if self.data_y[i]:
                    self.data_y[i].append(self.data_y[i][-1])
                else:
                    self.data_y[i].append(0)

            # --- 데이터 포인트 수 제한 ---
            max_points = self.x_window_size
            if len(self.data_x) > max_points:
                self.data_x = self.data_x[-max_points:]
                # 모든 채널의 y 데이터도 길이에 맞게 잘라줌
                for i in range(len(self.data_y)):
                    self.data_y[i] = self.data_y[i][-max_points:]

            # --- 모든 플롯 아이템 업데이트 ---
            for i in range(len(self.plot_items)):
                if len(self.data_x) == len(self.data_y[i]):
                    self.plot_items[i].setData(self.data_x, self.data_y[i])

            # --- 오실로스코프 모드: 스케일 변경 시에도 최신 데이터 추적 ---
            if self.data_x:
                view_box = self.plot_widget.getPlotItem().getViewBox()
                # X축 AutoRange가 해제된 경우(사용자 줌/팬)에만 수동으로 스크롤 처리
                if not view_box.autoRangeEnabled()[0]:
                    x_range = view_box.viewRange()[0]
                    width = x_range[1] - x_range[0]
                    latest_x = self.data_x[-1]
                    self.plot_widget.setXRange(latest_x - width, latest_x, padding=0)

        except Exception as e:
            # 예상치 못한 다른 오류 처리
            self.log_message(f"An error occurred in update_plot: {str(e)}")
            pass

    ## @brief 그래프 범례 항목을 더블 클릭하여 편집할 수 있도록 설정합니다.
    #  @param plot_item 편집 대상 PlotDataItem
    #  @param name 현재 항목의 이름
    def make_legend_item_editable(self, plot_item, name):
        # 범례에서 해당 plot_item에 대한 label을 찾습니다.
        for sample, label in self.legend.items:
            if sample.item is plot_item:
                # LabelItem에 마우스 더블 클릭 이벤트를 연결합니다.
                label.mouseDoubleClickEvent = lambda event, p=plot_item, l=label: self.rename_legend_item(p, l)

    ## @brief 범례 항목의 이름을 변경하는 대화상자를 엽니다.
    #  @param plot_item 이름을 변경할 PlotDataItem
    #  @param label_item 이름을 변경할 LabelItem
    def rename_legend_item(self, plot_item, label_item):
        current_name = plot_item.name()
        text, ok = QInputDialog.getText(self, "Rename Legend", "Enter new name:", text=current_name)
        if ok and text:
            # PlotDataItem과 Legend의 이름을 모두 업데이트합니다.
            plot_item.opts['name'] = text
            self.legend.removeItem(label_item.text) # 이전 이름으로 아이템 제거
            self.legend.addItem(plot_item, text) # 새 이름으로 아이템 추가
            self.log_message(f"Renamed '{current_name}' to '{text}'.")

    ## @brief Y축 자동 스케일 기능을 토글합니다.
    def toggle_auto_scale_y(self, state):
        if state == Qt.Checked:
            self.plot_widget.enableAutoRange(axis='y')
        else:
            self.plot_widget.disableAutoRange(axis='y')

    ## @brief X축 표시 범위(데이터 포인트 수)를 업데이트합니다.
    def update_x_range(self, value):
        self.x_window_size = value
        self.x_range_label.setText(f"X Range: {value}")

    ## @brief 그래프 선 굵기를 업데이트합니다.
    def update_line_width(self, value):
        self.line_width = value
        for i, item in enumerate(self.plot_items):
            color_code = self.plot_pens[i % len(self.plot_pens)]
            item.setPen(pg.mkPen(color=color_code, width=self.line_width))

    ## @brief CSV 저장을 시작하거나 정지합니다.
    def toggle_saving(self):
        if not self.is_saving:
            self.start_saving()
        else:
            self.stop_saving()

    ## @brief CSV 데이터 저장을 위해 내부 버퍼링을 시작합니다.
    def start_saving(self):
        self.csv_buffer.clear()
        self.save_sample_index = 0
        self.recording_start_timestamp = QDateTime.currentDateTime()
        self.is_saving = True
        self.save_button.setText("Stop Saving")
        self.log_message("Started buffering data for CSV export.")

    ## @brief 버퍼링된 데이터를 CSV 파일로 저장하고 저장을 중지합니다.
    def stop_saving(self):
        self.is_saving = False
        self.save_button.setText("Start Saving")
        self.log_message("Stopped buffering data.")

        if not self.csv_buffer:
            self.log_message("No data to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV File", "", "CSV Files (*.csv)")
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # --- Metadata Header ---
                    recording_end_timestamp = QDateTime.currentDateTime()
                    duration_sec = self.recording_start_timestamp.msecsTo(recording_end_timestamp) / 1000.0
                    total_samples = len(self.csv_buffer)
                    avg_rate = total_samples / duration_sec if duration_sec > 0 else 0.0

                    writer.writerow([f"# Recording Time: {self.recording_start_timestamp.toString('yyyy-MM-dd hh:mm:ss')}"])
                    writer.writerow([f"# ADC Resolution: {self.adc_resolution}"])
                    writer.writerow([f"# Input Voltage: {self.input_voltage}"])
                    writer.writerow([f"# Sampling Rate: {avg_rate:.2f} Hz"])
                    writer.writerow([])

                    if self.csv_buffer:
                        num_values = len(self.csv_buffer[0]) - 1
                        header = ['Sample Index'] + [f'Value{i+1}' for i in range(num_values)]
                        writer.writerow(header)
                    writer.writerows(self.csv_buffer)
                self.log_message(f"Data successfully saved to {file_path}.")
            except Exception as e:
                self.log_message(f"Error saving file: {e}")
        else:
            self.log_message("Save operation cancelled.")
        
        self.csv_buffer.clear()


    ## @brief 수신된 데이터를 내부 버퍼에 추가합니다.
    #  @param data_line 수신된 데이터 한 줄 (문자열)
    def buffer_csv_data(self, data_line):
        try:
            values = data_line.split(',')
            # 들어온 데이터가 숫자인지 확인 후 버퍼에 추가
            [float(v) for v in values]
            self.csv_buffer.append([self.save_sample_index] + values)
            self.save_sample_index += 1
        except (ValueError, IndexError):
            # 숫자가 아닌 데이터는 CSV 버퍼에 추가하지 않음
            pass

    ## @brief 그래프 데이터를 초기화합니다.
    def clear_plot(self):
        self.data_x.clear()
        self.data_y.clear()
        self.plot_widget.clear()
        self.plot_items.clear() # plot_items 리스트도 비웁니다.
        self.legend = self.plot_widget.addLegend() # 범례를 재생성합니다.
        self.start_time = 0
        self.log_box.clear()
        self.log_message("Plot cleared.")

    ## @brief 로그 텍스트 박스의 내용을 지웁니다.
    def clear_log(self):
        self.log_box.clear()

    ## @brief 현재 그래프를 이미지 파일로 저장합니다.
    def capture_plot_as_image(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Plot as Image", "", "PNG Image (*.png);;JPEG Image (*.jpg)")
        if file_path:
            try:
                exporter = pg.exporters.ImageExporter(self.plot_widget.getPlotItem())
                exporter.export(file_path)
                self.log_message(f"Plot captured and saved to {file_path}.")
            except Exception as e:
                self.log_message(f"Error saving plot image: {e}")
        else:
            self.log_message("Plot capture cancelled.")


    ## @brief 로그 박스에 메시지를 추가합니다.
    #  @param message 로그에 추가할 메시지
    def log_message(self, message):
        self.statusBar().showMessage(message)

    ## @brief 창이 닫힐 때 호출되는 이벤트 핸들러입니다. 시리얼 연결을 안전하게 해제합니다.
    def closeEvent(self, event):
        if self.serial_port and self.serial_port.is_open:
            reply = QMessageBox.question(self, 'Disconnect Confirmation',
                                         "Serial port is connected. Do you want to disconnect and exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.disconnect_serial()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    ## @brief 주기적으로 데이터 수신 속도를 계산하고 UI를 업데이트합니다.
    def update_rate_display(self):
        current_time = QDateTime.currentDateTime().toMSecsSinceEpoch() / 1000.0
        elapsed_time = current_time - self.last_rate_update_time

        if elapsed_time > 0:
            rate = self.data_packets_received / elapsed_time
            self.rate_label.setText(f"Rate: {rate:.1f} Hz")
        
        # Reset for the next interval
        self.data_packets_received = 0
        self.last_rate_update_time = current_time


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = SerialDataPlotter()
    main_win.show()
    sys.exit(app.exec_())