from pca9685 import PCA9685
from machine import I2C, Pin
import time

class PicoBotArm:
    def __init__(self, sda_pin=2, scl_pin=3, i2c_id=1, init_servos=True):
        """
        Инициализира PicoBotArm с I2C и PCA9685.
        """
        self.sda = Pin(sda_pin)
        self.scl = Pin(scl_pin)
        self.i2c_id = i2c_id
        self.i2c = I2C(id=self.i2c_id, sda=self.sda, scl=self.scl)
        self.pca = PCA9685(i2c=self.i2c)
        self.pca.freq(50)
        
        # Запазване на текущите ъгли
        self.current_angles = {0: 0, 1: 0, 2: 0}  # Начални стойности
        # Инициализация на сервомоторите
        if init_servos:
            self.init_servos()  # Автоматична инициализация при създаване на обект

    def control_servo(self, channel, angle):
        """
        Задава ъгъл на серво мотор за конкретен канал.
        :param channel: Канал на PCA9685 (0 до 15).
        :param angle: Ъгъл (0-180 градуса).
        """
        if not 0 <= angle <= 180:
            raise ValueError("Невалиден ъгъл. Задайте стойност между 0 и 180 градуса.")
        
        # Преобразуване на ъгъла в PWM duty cycle
        min_pulse = 102  # Минимална стойност на импулса (1 ms)
        max_pulse = 512  # Максимална стойност на импулса (2 ms)
        pulse = int(min_pulse + (angle / 180.0) * (max_pulse - min_pulse))
        self.pca.pwm(channel, 0, pulse)

    def smooth_move_servo(self, channel, target_angle, step=1, delay=0.02):
        """
        Плавно променя ъгъла на серво мотора.
        :param channel: Канал на PCA9685 (0 до 15).
        :param target_angle: Целеви ъгъл на сервото.
        :param step: Стъпка на промяна на ъгъла.
        :param delay: Забавяне между стъпките (в секунди).
        """
        current_angle = self.current_angles[channel]
        if current_angle < target_angle:
            for angle in range(current_angle, target_angle + 1, step):
                self.control_servo(channel, angle)
                time.sleep(delay)
        elif current_angle > target_angle:
            for angle in range(current_angle, target_angle - 1, -step):
                self.control_servo(channel, angle)
                time.sleep(delay)
        
        # Актуализира текущия ъгъл
        self.current_angles[channel] = target_angle

    def reset_servos(self):
        """
        Ресет на всички серво мотори до 90 градуса без плавно движение.
        """
        angles_to_reset = {0: 90, 1: 90, 2: 90}  # Начални стойности за всеки канал
        for channel, angle in angles_to_reset.items():
            self.smooth_move_servo(channel, angle)
            self.current_angles[channel] = angle  # Установява текущите стойности

    def init_servos(self):
        """
        Ресет на всички серво мотори до 90 градуса без плавно движение.
        """
        angles_to_reset = {0: 90, 1: 90, 2: 90}  # Начални стойности за всеки канал
        for channel, angle in angles_to_reset.items():
            self.control_servo(channel, angle)
            self.current_angles[channel] = angle  # Установява текущите стойности

