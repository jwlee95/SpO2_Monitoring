class GasSensorConverter:
    def __init__(self, adc_vref=3.3, adc_bit=12):
        """
        초기화 함수
        :param adc_vref: ADC 기준 전압 (기본 3.3V)
        :param adc_bit: ADC 비트 수 (기본 12비트)
        """
        self.adc_vref = adc_vref
        self.max_adc_val = (2 ** adc_bit) - 1  # 4095
        
        # 감쇄율 설정 (사용자 지정)
        self.attenuation_o2 = 0.5 * 0.673  # 약 0.3365
        self.attenuation_co2 = 0.5 * 0.88  # 0.44

    def adc_to_voltage(self, adc_val):
        """ADC 디지털 값을 칩에 입력되는 전압(0~3.3V)으로 변환"""
        if adc_val < 0: adc_val = 0
        if adc_val > self.max_adc_val: adc_val = self.max_adc_val
        
        return (adc_val / self.max_adc_val) * self.adc_vref

    def get_o2_concentration(self, adc_val):
        """
        S-3A 산소 농도 변환
        - 원래 출력: 0~10V = 0~100%
        - 감쇄 적용 후 ADC 입력
        """
        # 1. ADC 핀에 입력된 전압 (0~3.3V)
        input_voltage = self.adc_to_voltage(adc_val)
        
        # 2. 감쇄 전의 원래 센서 출력 전압 복원 (Original Voltage)
        # V_sensor * 0.3365 = V_input  =>  V_sensor = V_input / 0.3365
        original_voltage = input_voltage / self.attenuation_o2
        
        # 3. 농도 변환 (1V = 10%)
        o2_percent = original_voltage * 10.0
        
        return o2_percent

    def get_co2_concentration(self, adc_val):
        """
        CD-3A 이산화탄소 농도 변환
        - 원래 출력: 0~7.5V = 0~15%
        - 감쇄 적용 후 ADC 입력
        """
        # 1. ADC 핀에 입력된 전압 (0~3.3V)
        input_voltage = self.adc_to_voltage(adc_val)
        
        # 2. 감쇄 전의 원래 센서 출력 전압 복원
        # V_sensor * 0.44 = V_input  =>  V_sensor = V_input / 0.44
        original_voltage = input_voltage / self.attenuation_co2
        
        # 3. 농도 변환 (0~7.5V = 0~15% 이므로 1V당 2%)
        co2_percent = original_voltage * 2.0
        
        return co2_percent

# --- 사용 예시 ---

if __name__ == "__main__":
    converter = GasSensorConverter()

    # 예시 1: 산소 센서 (S-3A)
    # 대기 중 산소 20.9%일 때 -> 센서출력 2.09V
    # ADC 입력 예상값 = 2.09V * 0.3365 = 0.703V
    # ADC 값 예상 = (0.703 / 3.3) * 4095 = 약 872
    adc_o2_input = 872
    measured_o2 = converter.get_o2_concentration(adc_o2_input)

    # 예시 2: 이산화탄소 센서 (CD-3A)
    # 호기 중 이산화탄소 5.0%일 때 -> 센서출력 2.5V (5/2)
    # ADC 입력 예상값 = 2.5V * 0.44 = 1.1V
    # ADC 값 예상 = (1.1 / 3.3) * 4095 = 약 1365
    adc_co2_input = 1365
    measured_co2 = converter.get_co2_concentration(adc_co2_input)

    print(f"--- 변환 결과 ---")
    print(f"O2 ADC값 {adc_o2_input} -> 산소 농도: {measured_o2:.2f} %")
    print(f"CO2 ADC값 {adc_co2_input} -> 이산화탄소 농도: {measured_co2:.2f} %")

    # --- 한계점 체크 ---
    # O2 최대 측정 가능 범위 확인
    max_o2_measurable = converter.get_o2_concentration(4095)
    print(f"\n[참고] 현재 감쇄비로 측정 가능한 최대 O2 농도: {max_o2_measurable:.2f} %")