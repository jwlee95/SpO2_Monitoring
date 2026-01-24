# SpO2 Monitoring Application

SpO2(산소 포화도) 및 호흡 가스 센서 데이터를 수집, 분석하고 실시간으로 표시하는 PyQt5 기반 GUI 애플리케이션입니다.

## 📋 프로젝트 개요

이 프로젝트는 다음 기능을 제공합니다:
- **실시간 SpO2 데이터 모니터링**: 시리얼 포트에서 SpO2 센서 데이터 수신 및 파싱
- **듀얼 센서 지원**: SpO2 센서(Port 1)와 호흡 가스 센서(Port 2) 동시 모니터링
- **실시간 그래프**: SpO2, 심박수(BPM), O2, CO2 농도 시각화
- **데이터 로깅**: CSV 형식으로 측정 데이터 저장
- **센서 데이터 변환**: ADC 값을 실제 가스 농도로 변환

## 🗂️ 파일 구조

| 파일명 | 설명 |
|--------|------|
| `spo2_gui_app.py` | 기본 SpO2 데이터 파싱 및 GUI 애플리케이션 |
| `spo2_graph_app.py` | 실시간 그래프 표시 기능이 추가된 메인 애플리케이션 (최신) |
| `sp02_sensor_converter.py` | ADC 값을 가스 농도(O2, CO2)로 변환하는 유틸리티 클래스 |
| `spo2_processing01.py` | SpO2 데이터 처리 및 분석 모듈 |
| `spo2_serveringhaus.py` | 호흡 가스 분석기(RespiratoryGasAnalyzer) 클래스 |
| `spo2_test2.txt` | 테스트 데이터 파일 |

## 🚀 주요 기능

### 1. SpO2 모니터링 (`spo2_graph_app.py`)
- **버전**: 1.3.0
- 시리얼 포트에서 SpO2, 심박수(HR/BPM), 맥박 진폭(PA) 수신
- 상태 코드 파싱 (Alarm, Battery status, Sensor status 등)
- 실시간 그래프에 데이터 시각화

### 2. 듀얼 센서 지원
- **Main Port (Port 1)**: SpO2 센서 (0.5Hz)
- **Sub Port (Port 2)**: O2/CO2 센서 (100Hz)
- 두 센서의 데이터를 시간 동기화하여 표시

### 3. 데이터 로깅
- CSV 형식으로 자동 저장
- 파일명 형식: `Subject_No_YYMMDD_HHMM.csv`
- 피검자 정보 및 코멘트 입력 가능

### 4. 센서 데이터 변환 (`sp02_sensor_converter.py`)
- **O2 센서**: ADC 값 → 0~100% 농도
- **CO2 센서**: ADC 값 → 0~15% 농도
- 감쇄율 적용 및 전압 변환

## 🔧 필수 환경

### 라이브러리
```
PyQt5  >= 5.15.0
pyserial >= 3.5 
pyqtgraph >= 0.13.0
```

### 하드웨어
- SpO2 센서 (시리얼 포트)
- O2/CO2 센서 (선택사항)

## 💾 상태 코드 정의

| 코드 | 의미 |
|------|------|
| AO | Alarm off |
| BU | Battery in use |
| LB | Low battery |
| LP | Loss of pulse |
| MO | Patient motion |
| PS | Pulse search |
| SD | Sensor disconnect |
| SH | Saturation upper limit alarm |
| SL | Saturation lower limit alarm |

## 📝 CSV 데이터 형식

```
Timestamp, SpO2(%), HR(BPM), PA, Status, O2_Sat(%), CO2_Sat(%), Comment
2026-01-23 14:30:45, 98, 72, 45, Alarm off, 21.0, 4.5, Normal
...
```

## 🎯 최근 변경사항 (v1.3.0)

- ✅ 듀얼 시리얼 포트 지원 추가
- ✅ 그래프 Y축 통합 (0~200 범위) 및 Est. SpO2 그래프(점선) 추가
- ✅ 데이터 동기화 알고리즘 개선
- ✅ CSV 로깅 기능 구현
- ✅ LCD 디스플레이 가독성 개선 (QLabel 변경, 폰트 확대 32pt)
- ✅ Est. SpO2 라벨 변경 및 시각화 강화

## 📚 사용법

### 애플리케이션 실행
```bash
python spo2_graph_app.py
```

### 시리얼 포트 설정
1. 포트 선택 (드롭다운 메뉴)
2. 포트 2 설정 (O2/CO2 센서 사용 시)
3. "Start" 버튼 클릭하여 데이터 수신 시작

### 데이터 저장
1. 피검자 번호 입력
2. 코멘트 입력 (선택)
3. 데이터 로깅 시작
4. 종료 시 자동으로 CSV 파일 생성

## 👤 작성자

**Jeonghwan Lee**  
작성 일자: 2025-11-30  
최종 수정: 2026-01-24

## 📄 라이선스

프로젝트 라이선스 정보를 여기에 추가하세요.

---

**문제 해결**: 시리얼 연결 문제가 발생하는 경우 포트 번호와 보드레이트를 확인하세요.
