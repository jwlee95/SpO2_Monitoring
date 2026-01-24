import numpy as np

class RespiratoryGasAnalyzer:
    def __init__(self, p_atm=760.0):
        """
        초기화 함수
        Args:
            p_atm (float): 대기압 (기본값 760 mmHg)
        """
        self.p_atm = p_atm
        
    def calculate_spo2(self, sensor_t_c, sensor_rh_pct, o2_pct, co2_pct, body_temp_c=37.0):
        """
        통합 알고리즘: 호흡 가스 입력 -> SpO2 출력
        
        Args:
            sensor_t_c (float): 센서가 측정한 가스 온도 (섭씨) - 수증기압 보정용
            sensor_rh_pct (float): 센서가 측정한 상대습도 (%) - 수증기압 보정용
            o2_pct (float): 센서 측정 산소 농도 (%)
            co2_pct (float): 센서 측정 이산화탄소 농도 (%)
            body_temp_c (float): 피험자의 체온 (섭씨, 기본값 37.0) - ODC Shift 계산용 
            
        Returns:
            dict: 최종 SpO2 및 중간 계산 값들
        """
        
        # --- 유효성 검사 (Input Validation) ---
        # 습도, 산소, 이산화탄소 농도는 0~100% 범위로 제한 (음수 방지)
        sensor_rh_pct = max(0.0, min(100.0, float(sensor_rh_pct)))
        o2_pct = max(0.0, min(100.0, float(o2_pct)))
        co2_pct = max(0.0, min(100.0, float(co2_pct)))
        
        # 체온이 비정상적으로 낮은 경우(음수) 방지
        body_temp_c = max(0.0, float(body_temp_c))
        
        # --- Step 1: Dalton's Law (물리적 분압 변환) ---
        # 1-1. 수증기압(P_H2O) 계산 (Magnus Formula)
        # 센서 환경(온도, 습도)에 따른 수증기압을 계산하여 유효 분압을 구함
        p_sat_hpa = 6.112 * np.exp((17.67 * sensor_t_c) / (sensor_t_c + 243.5))
        p_sat_mmhg = p_sat_hpa * 0.750062
        p_h2o = p_sat_mmhg * (sensor_rh_pct / 100.0)
        
        # 1-2. 유효 압력 (Dry Gas Pressure)
        p_effective = self.p_atm - p_h2o
        
        # 1-3. 센서 위치에서의 분압
        p_sensor_o2 = p_effective * (o2_pct / 100.0)
        p_sensor_co2 = p_effective * (co2_pct / 100.0)
        
        # --- Step 2: Physiological Estimation (생체 변환) ---
        # 2-1. 동맥혈 가스(Arterial Gas) 추정
        # 가정: 측정된 가스는 호기말 가스(End-tidal)이며, 폐포 가스와 평형임
        
        # PaCO2는 PetCO2와 거의 같음
        pa_co2 = p_sensor_co2
        
        # PaO2는 PetO2에서 A-a Gradient(약 5mmHg)만큼 감소
        a_a_gradient = 5.0
        pa_o2 = np.maximum(p_sensor_o2 - a_a_gradient, 0.1) # 음수 방지
        
        # 2-2. pH 추정 (Henderson-Hasselbalch Logic)
        # 기준: PaCO2 40mmHg일 때 pH 7.4
        # PaCO2 상승 -> pH 하강 (산증), PaCO2 하강 -> pH 상승 (알칼리증)
        estimated_ph = 7.4 - 0.008 * (pa_co2 - 40.0)
        
        # --- Step 3: Severinghaus Model (ODC 계산) ---
        # 3-1. Shift Factors 계산
        # 수정됨: 입력받은 실제 체온(body_temp_c)을 사용하여 곡선 이동 계산
        
        base_excess = 0.0 # 가정값
        
        # 온도 보정: 체온이 37도보다 높으면 곡선이 오른쪽으로 이동(산소 친화력 감소)
        factor_temp = 0.024 * (body_temp_c - 37.0) 
        factor_ph = 0.48 * (7.4 - estimated_ph)
        factor_be = 0.0013 * base_excess
        
        total_log_shift = factor_temp + factor_ph + factor_be
        
        # 3-2. Virtual PO2 (표준화)
        # 실제 조건의 PaO2를 표준 곡선(37도, pH 7.4) 상의 대응 값으로 변환
        p_virtual = pa_o2 * (10 ** -total_log_shift)
        
        # 3-3. 3차 방정식 적용 (SpO2 %)
        s_numerator = (p_virtual ** 3) + (150 * p_virtual)
        s_denominator = 23400 + s_numerator
        spo2_result = 100 * (s_numerator / s_denominator)
        
        return {
            "SpO2_Percent": round(spo2_result, 2),
            "Estimated_pH": round(estimated_ph, 3),
            "PaO2_mmHg": round(pa_o2, 2),
            "PaCO2_mmHg": round(pa_co2, 2),
            "Body_Temp_C": body_temp_c,
            "Sensor_PH2O": round(p_h2o, 2)
        }

# --- 실행 테스트 (Main Block) ---
if __name__ == "__main__":
    analyzer = RespiratoryGasAnalyzer()

    # 테스트 케이스 1: 정상 체온 (37도)
    print("\n[Case 1] 정상 체온 (37.0°C), 일반적인 날숨")
    result_normal = analyzer.calculate_spo2(
        sensor_t_c=25.0,     # 센서 온도
        sensor_rh_pct=60.0,  # 센서 습도
        o2_pct=15.0,         # 날숨 산소
        co2_pct=5.3,         # 날숨 이산화탄소
        body_temp_c=37.0     # 체온
    )
    print(f" -> PaO2: {result_normal['PaO2_mmHg']} mmHg")
    print(f" -> pH: {result_normal['Estimated_pH']}")
    print(f" -> SpO2: {result_normal['SpO2_Percent']} %")

    # 테스트 케이스 2: 고열 환자 (39도) - 같은 가스 농도라도 SpO2가 다르게 나옴
    print("\n[Case 2] 고열 환자 (39.0°C), 동일한 가스 농도")
    result_fever = analyzer.calculate_spo2(
        sensor_t_c=25.0, 
        sensor_rh_pct=60.0, 
        o2_pct=15.0, 
        co2_pct=5.3, 
        body_temp_c=39.0     # 체온 상승
    )
    print(f" -> PaO2: {result_fever['PaO2_mmHg']} mmHg (변화 없음)")
    print(f" -> pH: {result_fever['Estimated_pH']} (변화 없음)")
    print(f" -> SpO2: {result_fever['SpO2_Percent']} % (체온 영향으로 감소)")
    
    print("\n" + "="*50)
    print(f"결과 비교: 체온이 2도 오르자 SpO2가 {result_normal['SpO2_Percent']}% 에서 {result_fever['SpO2_Percent']}% 로 변함.")