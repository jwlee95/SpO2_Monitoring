"""!
@file MordernLCD.py
@brief 커스텀 7-segment LCD 위젯 라이브러리
@details PyQt5를 사용하여 세련된 디지털 숫자 디스플레이를 구현함.

         주요 변경 사항 (2026-02-07):
         - 클래스명 변경 (NordernLCD -> MordernLCD)
         - 값이 변경될 때 플래시(Flash) 효과 추가 (흰색으로 번쩍임)
         - 금속 질감의 프레임(Gradient) 및 나사(Screw) 장식 추가
         - 배경에 은은한 격자무늬(Grid) 텍스처 추가
         - 세그먼트 스타일 개선 (둥근 모서리, 두께 조정)
         - 소수점 크기 및 위치 조정

@author JeongWhan Lee
@date 2026-02-07
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QColorDialog, QSlider, QGroupBox)
from PyQt5.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt5.QtGui import QPainter, QColor, QPolygonF, QBrush, QPen, QLinearGradient

class MordernLCD(QWidget):
    """!
    @brief 세련된 7-segment 스타일의 LCD 디스플레이 위젯
    """
    def __init__(self, parent=None):
        """!
        @brief 생성자. 초기 스타일 및 플래시 타이머 설정.
        """
        super().__init__(parent)
        self.text_value = "123.45"
        
        # 스타일 설정
        self.on_color = QColor(0, 255, 255)    # 켜진 세그먼트 색상 (Cyan)
        self.off_color = QColor(30, 30, 30)    # 꺼진 세그먼트 색상 (Dark Gray)
        self.bg_color = QColor(10, 10, 10)     # 배경색 (Almost Black)
        
        # 플래시 효과 변수
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(20) # 50 FPS
        self.flash_timer.timeout.connect(self._update_flash)
        self.flash_intensity = 0.0

        self.setMinimumSize(200, 80)

        # 7-segment 정의 (0:Off, 1:On)
        # 순서: A(상), B(우상), C(우하), D(하), E(좌하), F(좌상), G(중)
        self.segment_map = {
            '0': (1,1,1,1,1,1,0), '1': (0,1,1,0,0,0,0), '2': (1,1,0,1,1,0,1),
            '3': (1,1,1,1,0,0,1), '4': (0,1,1,0,0,1,1), '5': (1,0,1,1,0,1,1),
            '6': (1,0,1,1,1,1,1), '7': (1,1,1,0,0,0,0), '8': (1,1,1,1,1,1,1),
            '9': (1,1,1,1,0,1,1), '-': (0,0,0,0,0,0,1), ' ': (0,0,0,0,0,0,0),
            'E': (1,0,0,1,1,1,1), 'r': (0,0,0,0,1,0,1), 'o': (0,0,1,1,1,0,1),
            'A': (1,1,1,0,1,1,1), 'P': (1,1,0,0,1,1,1), 'L': (0,0,0,1,1,1,0)
        }

    def setText(self, text):
        """!
        @brief 표시할 텍스트(숫자)를 설정하고 플래시 효과를 트리거합니다.
        @param text 표시할 문자열
        """
        new_text = str(text)
        if self.text_value != new_text:
            self.text_value = new_text
            # 값이 바뀌면 플래시 효과 시작
            self.flash_intensity = 1.0
            if not self.flash_timer.isActive():
                self.flash_timer.start()
            self.update()

    def setColor(self, color):
        """!
        @brief 켜진 세그먼트의 기본 색상을 설정합니다.
        @param color QColor 객체 또는 색상값
        """
        self.on_color = QColor(color)
        self.update()

    def setBackgroundColor(self, color):
        """!
        @brief LCD 배경색을 설정합니다.
        @param color QColor 객체 또는 색상값
        """
        self.bg_color = QColor(color)
        self.update()

    def _update_flash(self):
        """!
        @brief 플래시 효과의 강도를 감소시키는 타이머 슬롯입니다.
        """
        self.flash_intensity -= 0.05 # 감쇄 속도 조절
        if self.flash_intensity <= 0:
            self.flash_intensity = 0.0
            self.flash_timer.stop()
        self.update()

    def _get_draw_color(self):
        """!
        @brief 현재 플래시 강도가 적용된 그리기 색상을 반환합니다.
        @return 계산된 QColor
        """
        if self.flash_intensity <= 0:
            return self.on_color
        
        # 흰색(255, 255, 255)과 원래 색상(on_color) 블렌딩
        r = int(self.on_color.red() * (1 - self.flash_intensity) + 255 * self.flash_intensity)
        g = int(self.on_color.green() * (1 - self.flash_intensity) + 255 * self.flash_intensity)
        b = int(self.on_color.blue() * (1 - self.flash_intensity) + 255 * self.flash_intensity)
        return QColor(r, g, b)

    def paintEvent(self, event):
        """!
        @brief 위젯 그리기 이벤트 핸들러. 프레임, 배경, 숫자를 그립니다.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # 1. 금속 프레임 그리기 (그라데이션)
        frame_width = 12
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(90, 90, 90))
        gradient.setColorAt(0.2, QColor(200, 200, 200)) # 상단 하이라이트
        gradient.setColorAt(0.5, QColor(120, 120, 120))
        gradient.setColorAt(1.0, QColor(60, 60, 60))
        
        painter.setPen(QPen(QColor(30, 30, 30), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(0, 0, w, h, 8, 8)
        
        # 2. 나사 그리기 (4군데 모서리)
        screw_offset = frame_width / 2
        screw_centers = [
            QPointF(screw_offset, screw_offset),
            QPointF(w - screw_offset, screw_offset),
            QPointF(screw_offset, h - screw_offset),
            QPointF(w - screw_offset, h - screw_offset)
        ]
        
        painter.setBrush(QBrush(QColor(180, 180, 180))) # 은색
        painter.setPen(QPen(QColor(50, 50, 50), 1))
        r = 3.5 # 나사 반지름
        for c in screw_centers:
            painter.drawEllipse(c, r, r)
            # 십자 나사 모양
            painter.drawLine(QPointF(c.x()-r+1, c.y()), QPointF(c.x()+r-1, c.y()))
            painter.drawLine(QPointF(c.x(), c.y()-r+1), QPointF(c.x(), c.y()+r-1))

        # 3. LCD 화면 영역 (프레임 안쪽)
        screen_rect = QRectF(frame_width, frame_width, w - 2*frame_width, h - 2*frame_width)
        
        painter.setBrush(self.bg_color)
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.drawRoundedRect(screen_rect, 4, 4)
        
        # 클리핑 설정 (이후 그려지는 내용은 화면 영역을 벗어나지 않음)
        painter.setClipRect(screen_rect)
        
        # 4. 격자 무늬 (화면 영역 내부)
        grid_step = 15
        grid_pen = QPen(QColor(30, 30, 30)) # 배경(10,10,10)보다 약간 밝은 색
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        start_grid_x = int(screen_rect.left())
        end_grid_x = int(screen_rect.right())
        start_grid_y = int(screen_rect.top())
        end_grid_y = int(screen_rect.bottom())

        for x in range(start_grid_x, end_grid_x, grid_step):
            painter.drawLine(x, start_grid_y, x, end_grid_y)
        for y in range(start_grid_y, end_grid_y, grid_step):
            painter.drawLine(start_grid_x, y, end_grid_x, y)
        
        # 레이아웃 계산
        margin = 5
        available_w = screen_rect.width() - 2 * margin
        available_h = screen_rect.height() - 2 * margin
        
        if available_w <= 0 or available_h <= 0: return

        # 표시할 문자열 분석 (소수점 등 특수문자 처리)
        display_items = []
        for char in self.text_value:
            if char in ['.', ':', ',']:
                display_items.append({'type': 'dot', 'char': char})
            else:
                display_items.append({'type': 'digit', 'char': char})
        
        if not display_items: return

        # 너비 계산 (숫자는 1.0, 점은 0.3 비율)
        total_units = sum(0.3 if item['type'] == 'dot' else 1.0 for item in display_items)
        if total_units == 0: return

        unit_w = available_w / total_units
        
        # 비율 제한 (숫자가 너무 납작해지지 않도록)
        # 일반적인 7-segment 비율 (W:H = 1:1.8 ~ 1:2)
        max_digit_w = available_h * 0.6
        if unit_w > max_digit_w:
            unit_w = max_digit_w
            
        # 전체 내용을 중앙 정렬하기 위한 시작 X 좌표
        content_width = unit_w * total_units
        start_x = screen_rect.left() + margin + (available_w - content_width) / 2
        start_y = screen_rect.top() + margin
        
        digit_h = available_h

        current_x = start_x
        for item in display_items:
            if item['type'] == 'digit':
                # 숫자 사이에 여백을 주기 위해 너비를 약간 줄여서 그림 (15% 여백)
                spacing = unit_w * 0.15
                draw_w = unit_w - spacing
                draw_x = current_x + (spacing / 2)
                self.draw_digit(painter, item['char'], draw_x, start_y, draw_w, digit_h)
                current_x += unit_w
            else:
                dot_w = unit_w * 0.3 # 점은 좁게
                self.draw_dot(painter, item['char'], current_x, start_y, dot_w, digit_h)
                current_x += dot_w

    def draw_digit(self, painter, char, x, y, w, h):
        """!
        @brief 단일 숫자(7-segment)를 그립니다.
        @param painter QPainter 객체
        @param char 그릴 문자
        @param x, y, w, h 그리기 영역 좌표 및 크기
        """
        # 세그먼트 두께 (약간 두껍게 설정)
        t = min(w, h) * 0.16
        
        # 펜 설정 (둥근 끝, 두껍게)
        pen = QPen()
        pen.setWidthF(t)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        
        # 좌표 계산
        h_half = h / 2
        offset = t / 2
        
        # 세그먼트 간격 (겹침 방지 및 자연스러운 연결)
        gap = t * 0.6
        
        # 세그먼트 라인 좌표 (Start, End)
        # A: Top, B: Top-Right, C: Bot-Right, D: Bot, E: Bot-Left, F: Top-Left, G: Mid
        
        # 가로 세그먼트 (A, G, D)
        x_start = x + offset + gap
        x_end = x + w - offset - gap
        
        lines = [
            (QPointF(x_start, y + offset), QPointF(x_end, y + offset)),           # A
            (QPointF(x + w - offset, y + offset + gap), QPointF(x + w - offset, y + h_half - gap)), # B
            (QPointF(x + w - offset, y + h_half + gap), QPointF(x + w - offset, y + h - offset - gap)), # C
            (QPointF(x_start, y + h - offset), QPointF(x_end, y + h - offset)),   # D
            (QPointF(x + offset, y + h_half + gap), QPointF(x + offset, y + h - offset - gap)), # E
            (QPointF(x + offset, y + offset + gap), QPointF(x + offset, y + h_half - gap)), # F
            (QPointF(x_start, y + h_half), QPointF(x_end, y + h_half))            # G
        ]
        
        # Get state
        state = self.segment_map.get(char.upper(), self.segment_map[' '])
        
        painter.setBrush(Qt.NoBrush)
        
        for i, is_on in enumerate(state):
            if is_on:
                pen.setColor(self._get_draw_color())
            else:
                c = QColor(self.off_color)
                c.setAlpha(50)
                pen.setColor(c)
            
            painter.setPen(pen)
            painter.drawLine(lines[i][0], lines[i][1])

    def draw_dot(self, painter, char, x, y, w, h):
        """!
        @brief 소수점이나 콜론을 그립니다.
        @param painter QPainter 객체
        @param char 그릴 문자 (., :)
        @param x, y, w, h 그리기 영역 좌표 및 크기
        """
        # 소수점 그리기 (크기 조정)
        r = w * 0.25
        cx = x + w / 2
        cy = y + h - r - (h * 0.05) # 바닥에서 약간 띄움
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._get_draw_color())
        
        if char == '.':
            painter.drawEllipse(QPointF(cx, cy), r, r)
        elif char == ':':
            # 콜론은 점 두개
            cy_top = y + h * 0.3
            cy_bot = y + h * 0.7
            painter.drawEllipse(QPointF(cx, cy_top), r, r)
            painter.drawEllipse(QPointF(cx, cy_bot), r, r)

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MordernLCD Widget Test")
        self.setGeometry(100, 100, 600, 400)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # LCD 위젯 인스턴스
        self.lcd = MordernLCD()
        layout.addWidget(self.lcd, 1) # Stretch factor 1 to take up space
        
        # 컨트롤 패널
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout()
        
        # 텍스트 입력
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Text:"))
        self.text_input = QLineEdit("123.45")
        self.text_input.textChanged.connect(self.lcd.setText)
        input_layout.addWidget(self.text_input)
        control_layout.addLayout(input_layout)
        
        # 색상 변경 버튼
        color_layout = QHBoxLayout()
        self.color_btn = QPushButton("Change Color")
        self.color_btn.clicked.connect(self.change_color)
        color_layout.addWidget(self.color_btn)
        
        self.bg_btn = QPushButton("Change Background")
        self.bg_btn.clicked.connect(self.change_bg_color)
        color_layout.addWidget(self.bg_btn)
        control_layout.addLayout(color_layout)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

    def change_color(self):
        color = QColorDialog.getColor(self.lcd.on_color, self, "Select LCD Color")
        if color.isValid():
            self.lcd.setColor(color)

    def change_bg_color(self):
        color = QColorDialog.getColor(self.lcd.bg_color, self, "Select Background Color")
        if color.isValid():
            self.lcd.setBackgroundColor(color)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = TestWindow()
    win.show()
    sys.exit(app.exec_())