#library needed: pyserial

import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox
import time
import re

class JDY41Configurator:
    # БИНАРНЫЕ КОМАНДЫ для JDY-41 
    CMD_RESET = bytes.fromhex("AB E3 0D 0A")
    CMD_READ_PARAMS = bytes.fromhex("AA E2 0D 0A")
    CMD_READ_VERSION = bytes.fromhex("AA E4 0D 0A")
    CMD_READ_DEVICE_ID = bytes.fromhex("F2 AD 0D 0A")
    
    # Префикс для команды записи параметров
    CMD_SET_PARAMS_PREFIX = bytes.fromhex("A9 E1")

    def __init__(self, root):
        self.root = root
        self.root.title("Настройка JDY-41")
        self.root.resizable(True, True)

        self.serial_port = None
        self.is_connected = False

        # Сопоставление значений
        self.baud_rates = {
            "1200": "01", "2400": "02", "4800": "03", "9600": "04",
            "19200": "05", "38400": "06", "57600": "07", "115200": "08"
        }
        self.baud_rates_reverse = {v: k for k, v in self.baud_rates.items()}
        
        self.power_levels = {
            "-25dB": "01", "-15dB": "02", "-5dB": "03", "0dB": "04",
            "+3dB": "05", "+6dB": "06", "+9dB": "07", "+10dB": "08", "+12dB": "09"
        }
        self.power_levels_reverse = {v: k for k, v in self.power_levels.items()}
        
        self.modes = {
            "Прозрачная передача (A0)": "A0",
            "Передатчик пульта с LED (C0)": "C0",
            "Передатчик пульта (C1)": "C1",
            "Приёмник, синхронизация уровня (C2)": "C2",
            "Приёмник, инверсия уровня (C3)": "C3",
            "Приёмник, импульсный уровень (C4)": "C4",
            "Обучаемый приёмник, синхронизация (C5)": "C5",
            "Обучаемый приёмник, инверсия/импульс (C6)": "C6",
            "Обучаемый приёмник, импульсный (C7)": "C7"
        }
        self.modes_reverse = {v: k for k, v in self.modes.items()}

        self.create_widgets()
        self.refresh_ports()

    def validate_hex_input(self, text):
        """Проверка ввода: только HEX символы и не более 8 символов"""
        if text == "":
            return True
        
        # Проверяем, что строка содержит только HEX символы
        if not all(c in "0123456789ABCDEFabcdef" for c in text):
            return False
        
        # Проверяем длину (не более 8 символов)
        if len(text) > 8:
            return False
        
        return True

    def on_id_entry_changed(self, *args):
        """Обработчик изменения текста в поле Wireless ID"""
        text = self.id_var.get()
        
        # Удаляем все не-HEX символы
        cleaned_text = ''.join(c for c in text if c in "0123456789ABCDEFabcdef")
        
        # Ограничиваем длину 8 символами
        if len(cleaned_text) > 8:
            cleaned_text = cleaned_text[:8]
        
        # Преобразуем в верхний регистр
        cleaned_text = cleaned_text.upper()
        
        # Если текст изменился после очистки, обновляем поле
        if cleaned_text != text:
            self.id_var.set(cleaned_text)

    def create_widgets(self):
        # Основной контейнер
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Фрейм подключения
        frame_connection = ttk.LabelFrame(main_frame, text="Подключение", padding=10)
        frame_connection.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        ttk.Label(frame_connection, text="COM-порт:").grid(row=0, column=0, sticky="w")
        self.port_combobox = ttk.Combobox(frame_connection, width=15, state="readonly")
        self.port_combobox.grid(row=0, column=1, padx=5)

        self.refresh_button = ttk.Button(frame_connection, text="Обновить", width=10, command=self.refresh_ports)
        self.refresh_button.grid(row=0, column=2, padx=5)

        self.connect_button = ttk.Button(frame_connection, text="Подключиться", command=self.toggle_connection)
        self.connect_button.grid(row=0, column=3, padx=5)

        # Кнопка сброса модуля
        self.reset_button = ttk.Button(frame_connection, text="Сброс модуля", command=self.reset_module, state=tk.DISABLED)
        self.reset_button.grid(row=0, column=4, padx=5)

        # Фрейм параметров
        frame_params = ttk.LabelFrame(main_frame, text="Параметры модуля", padding=10)
        frame_params.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Скорость
        ttk.Label(frame_params, text="Скорость UART:").grid(row=0, column=0, sticky="w", pady=5)
        self.baud_combobox = ttk.Combobox(frame_params, values=list(self.baud_rates.keys()), width=15, state="readonly")
        self.baud_combobox.set("9600")
        self.baud_combobox.grid(row=0, column=1, sticky="w", pady=5)

        # Канал
        ttk.Label(frame_params, text="Радиоканал (0-127):").grid(row=1, column=0, sticky="w", pady=5)
        self.channel_spinbox = ttk.Spinbox(frame_params, from_=0, to=127, width=5)
        self.channel_spinbox.set(0)
        self.channel_spinbox.grid(row=1, column=1, sticky="w", pady=5)

        # Мощность
        ttk.Label(frame_params, text="Мощность TX:").grid(row=2, column=0, sticky="w", pady=5)
        self.power_combobox = ttk.Combobox(frame_params, values=list(self.power_levels.keys()), width=15, state="readonly")
        self.power_combobox.set("+12dB")
        self.power_combobox.grid(row=2, column=1, sticky="w", pady=5)

        # Режим
        ttk.Label(frame_params, text="Режим работы:").grid(row=3, column=0, sticky="w", pady=5)
        self.mode_combobox = ttk.Combobox(frame_params, values=list(self.modes.keys()), width=50, state="readonly")
        self.mode_combobox.set("Прозрачная передача (A0)")
        self.mode_combobox.grid(row=3, column=1, columnspan=2, sticky="w", pady=5)

        # Wireless ID с валидацией
        ttk.Label(frame_params, text="Wireless ID (HEX):").grid(row=4, column=0, sticky="w", pady=5)
        
        # Создаем строковую переменную для отслеживания изменений
        self.id_var = tk.StringVar()
        self.id_var.set("00000000")
        self.id_var.trace_add('write', self.on_id_entry_changed)
        
        # Создаем поле ввода с привязкой к переменной
        self.id_entry = ttk.Entry(frame_params, width=10, textvariable=self.id_var)
        self.id_entry.grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(frame_params, text="(8 HEX символов, напр. AABBCCDD)").grid(row=4, column=2, sticky="w", padx=5)

        # Ответ на передачу данных
        self.response_var = tk.BooleanVar(value=True)
        self.response_checkbutton = ttk.Checkbutton(frame_params, text="Отвечать на приём данных", variable=self.response_var)
        self.response_checkbutton.grid(row=5, column=0, columnspan=3, sticky="w", pady=5)

        # Кнопки действий
        frame_actions = ttk.Frame(main_frame, padding=10)
        frame_actions.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.read_button = ttk.Button(frame_actions, text="Прочитать параметры", command=self.read_params, state=tk.DISABLED)
        self.read_button.pack(side=tk.LEFT, padx=5)

        self.write_button = ttk.Button(frame_actions, text="Записать параметры", command=self.write_params, state=tk.DISABLED)
        self.write_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = ttk.Button(frame_actions, text="Очистить лог", command=self.clear_log)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # Лог
        frame_log = ttk.LabelFrame(main_frame, text="Лог", padding=10)
        frame_log.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        main_frame.grid_rowconfigure(3, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(frame_log, height=16, width=70, bg="#f0f0f0")
        scrollbar = ttk.Scrollbar(frame_log, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame_log.grid_rowconfigure(0, weight=1)
        frame_log.grid_columnconfigure(0, weight=1)

        self.create_context_menu()

    def create_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Копировать", command=self.copy_selected)
        self.context_menu.add_command(label="Выделить всё", command=self.select_all)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Очистить лог", command=self.clear_log)

        self.log_text.bind("<Button-3>", self.show_context_menu)
        self.log_text.bind("<Control-c>", lambda e: self.copy_selected())
        self.log_text.bind("<Control-a>", lambda e: self.select_all())

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_selected(self):
        try:
            selected_text = self.log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
        except tk.TclError:
            pass

    def select_all(self):
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)
        self.log_text.mark_set(tk.INSERT, "1.0")
        self.log_text.see(tk.INSERT)
        return 'break'

    def clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def log(self, message):
        self.root.after(0, self._log_to_widget, message)

    def _log_to_widget(self, message):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combobox['values'] = ports
        if ports:
            self.port_combobox.set(ports[0])

    def toggle_connection(self):
        if not self.is_connected:
            port = self.port_combobox.get()
            if not port:
                messagebox.showerror("Ошибка", "Выберите COM-порт.")
                return
            try:
                self.serial_port = serial.Serial(port, baudrate=9600, timeout=2)
                self.is_connected = True
                self.connect_button.config(text="Отключиться")
                self.read_button.config(state=tk.NORMAL)
                self.write_button.config(state=tk.NORMAL)
                self.reset_button.config(state=tk.NORMAL)
                self.log(f"Подключено к {port}")
                self.send_command(self.CMD_RESET, "Сброс модуля")
            except serial.SerialException as e:
                messagebox.showerror("Ошибка подключения", f"Не удалось открыть порт {port}.\n{e}")
        else:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.is_connected = False
            self.connect_button.config(text="Подключиться")
            self.read_button.config(state=tk.DISABLED)
            self.write_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
            self.log("Отключено")

    def reset_module(self):
        """Сброс модуля по нажатию кнопки."""
        self.log("=" * 50)
        self.log("🔄 Сброс модуля...")
        self.send_command(self.CMD_RESET, "Сброс модуля")
        self.log("=" * 50)

    def send_command(self, data, description):
        if not self.serial_port or not self.serial_port.is_open:
            self.log("Ошибка: нет соединения.")
            return None
        try:
            self.log(f">> Отправка ({description}): {data.hex().upper()}")
            self.serial_port.reset_input_buffer()
            self.serial_port.write(data)
            time.sleep(0.3)
            
            response = b''
            while self.serial_port.in_waiting:
                response += self.serial_port.read(self.serial_port.in_waiting)
                time.sleep(0.05)
            
            if response:
                ascii_response = response.decode('ascii', errors='ignore')
                self.log(f"<< Ответ (HEX): {response.hex().upper()} | ASCII: {ascii_response}")
                return response
            else:
                self.log("<< Нет ответа")
                return None
        except serial.SerialException as e:
            self.log(f"Ошибка отправки: {e}")
            return None

    def parse_read_response(self, response):
        """Разбор ответа от команды чтения параметров"""
        try:
            self.log(f"🔍 Начинаю разбор ответа длиной {len(response)} байт")
            
            hex_str = response.hex().upper()
            self.log(f"🔍 HEX строка: {hex_str}")
            
            while hex_str.startswith("AAE2AAE2"):
                hex_str = hex_str[4:]
                self.log(f"🔍 Убран дублирующийся заголовок, осталось: {hex_str}")
            
            if not hex_str.startswith("AAE2"):
                self.log(f"❌ Ответ не начинается с AAE2: {hex_str[:4]}")
                return False
            
            data_hex = hex_str[4:]
            self.log(f"🔍 Данные после заголовка: {data_hex}")
            
            if data_hex.endswith("0D0A"):
                data_hex = data_hex[:-4]
                self.log(f"🔍 Данные без окончания 0D0A: {data_hex}")
            
            if len(data_hex) < 10:
                self.log(f"❌ Слишком короткие данные: {len(data_hex)} символов")
                return False
            
            baud_hex = data_hex[0:2]
            channel = int(data_hex[2:4], 16)
            power_hex = data_hex[4:6]
            mode_hex = data_hex[6:8]
            wireless_id = data_hex[8:16]
            response_byte = int(data_hex[16:18], 16) if len(data_hex) >= 18 else 0
            backup_byte = int(data_hex[18:20], 16) if len(data_hex) >= 20 else 0
            
            self.log(f"✅ Параметры успешно разобраны:")
            self.log(f"   Скорость: {self.baud_rates_reverse.get(baud_hex, 'Неизвестно')} (0x{baud_hex})")
            self.log(f"   Канал: {channel} (0x{channel:02X})")
            self.log(f"   Мощность: {self.power_levels_reverse.get(power_hex, 'Неизвестно')} (0x{power_hex})")
            self.log(f"   Режим: {self.modes_reverse.get(mode_hex, 'Неизвестно')} (0x{mode_hex})")
            self.log(f"   Wireless ID: {wireless_id}")
            self.log(f"   Ответ на приём: {'Да' if response_byte == 1 else 'Нет'} (0x{response_byte:02X})")
            self.log(f"   Резерв: 0x{backup_byte:02X}")
            
            self.root.after(0, self.update_gui_fields, baud_hex, channel, power_hex, mode_hex, wireless_id, response_byte)
            
            return True
            
        except Exception as e:
            self.log(f"❌ Ошибка разбора ответа: {e}")
            import traceback
            self.log(traceback.format_exc())
            return False

    def update_gui_fields(self, baud_hex, channel, power_hex, mode_hex, wireless_id, response_byte):
        """Обновление полей GUI на основе разобранных параметров."""
        self.log("📝 Обновляю поля интерфейса...")
        
        baud_text = self.baud_rates_reverse.get(baud_hex)
        if baud_text:
            self.baud_combobox.set(baud_text)
            self.log(f"   Установлена скорость: {baud_text}")
        
        self.channel_spinbox.delete(0, tk.END)
        self.channel_spinbox.insert(0, str(channel))
        self.log(f"   Установлен канал: {channel}")
        
        power_text = self.power_levels_reverse.get(power_hex)
        if power_text:
            self.power_combobox.set(power_text)
            self.log(f"   Установлена мощность: {power_text}")
        
        mode_text = self.modes_reverse.get(mode_hex)
        if mode_text:
            self.mode_combobox.set(mode_text)
            self.log(f"   Установлен режим: {mode_text}")
        
        self.id_var.set(wireless_id)
        self.log(f"   Установлен ID: {wireless_id}")
        
        self.response_var.set(response_byte == 0x01)
        self.log(f"   Ответ на приём: {'включен' if response_byte == 0x01 else 'выключен'}")

    def build_params_command(self):
        try:
            baud_hex = self.baud_rates[self.baud_combobox.get()]
            channel = int(self.channel_spinbox.get())
            channel_hex = f"{channel:02X}"
            power_hex = self.power_levels[self.power_combobox.get()]
            mode_hex = self.modes[self.mode_combobox.get()]
            
            id_str = self.id_var.get().strip().upper()
            if len(id_str) != 8 or not all(c in "0123456789ABCDEF" for c in id_str):
                raise ValueError("Wireless ID должен состоять ровно из 8 HEX символов (0-9, A-F).")
            
            response_hex = "01" if self.response_var.get() else "00"
            backup = "00"

            params_hex = f"{baud_hex} {channel_hex} {power_hex} {mode_hex} {id_str} {response_hex} {backup} 0D 0A"
            command = self.CMD_SET_PARAMS_PREFIX + bytes.fromhex(params_hex)
            return command
            
        except Exception as e:
            messagebox.showerror("Ошибка параметров", str(e))
            return None

    def write_params(self):
        """Запись параметров с автоматическим сбросом модуля."""
        self.log("=" * 50)
        self.log("📝 Запись параметров в модуль...")
        cmd = self.build_params_command()
        if cmd:
            response = self.send_command(cmd, "Запись параметров")
            if response:
                self.log("✅ Параметры записаны, выполняю сброс модуля...")
                time.sleep(0.3)
                self.send_command(self.CMD_RESET, "Сброс модуля после записи")
                self.log("✅ Модуль перезагружен с новыми параметрами")
            else:
                self.log("❌ Не получен ответ при записи параметров")
        self.log("=" * 50)

    def read_params(self):
        """Чтение текущих параметров модуля с автоматическим разбором."""
        self.log("=" * 50)
        self.log("📡 Запрос параметров модуля...")
        response = self.send_command(self.CMD_READ_PARAMS, "Чтение параметров")
        if response:
            self.log("📥 Получен ответ, начинаю разбор...")
            success = self.parse_read_response(response)
            if success:
                self.log("✅ Параметры успешно загружены в интерфейс")
            else:
                self.log("❌ Не удалось разобрать ответ модуля")
                self.log("💡 Попробуйте нажать кнопку еще раз")
        else:
            self.log("❌ Модуль не ответил на запрос")
        self.log("=" * 50)

if __name__ == "__main__":
    root = tk.Tk()
    root.minsize(650, 500)
    app = JDY41Configurator(root)
    root.mainloop()