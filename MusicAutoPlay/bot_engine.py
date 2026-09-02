import time
import cv2
import numpy as np
import mss
import pydirectinput
import threading
import json
import os

pydirectinput.PAUSE = 0.0

LOWER_YELLOW = np.array([20, 100, 150])
UPPER_YELLOW = np.array([40, 255, 255])
LOWER_PURPLE = np.array([110, 30, 80])
UPPER_PURPLE = np.array([160, 255, 255])

class BotEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {}

    def save_config(self, new_config):
        self.config.update(new_config)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_config(self):
        return self.config

    def start(self):
        if not self.running:
            self.running = True
            # Reload config just before starting to ensure latest keys
            self.config = self.load_config()
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            return True
        return False

    def stop(self):
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=1.0)
            # Relâche toutes les touches par sécurité
            keys = self.config.get('keys', [])
            for key in keys:
                pydirectinput.keyUp(key)
            return True
        return False

    def _run_loop(self):
        sct = mss.mss()
        
        c = self.config
        keys = c.get('keys', ['a', 's', 'd', 'j', 'k', 'l'])
        initial_y = c.get('initial_y', 867)
        x_start = c.get('x_start', 350)
        x_end = c.get('x_end', 1550)
        width = x_end - x_start
        height = c.get('height', 20)
        columns_x = c.get('columns_x', [10, 235, 451, 671, 884, 1099])
        column_width = c.get('column_width', 25)
        
        tap_duration = c.get('tap_duration', 0.02)
        tap_cooldown = c.get('tap_cooldown', 0.05)
        hold_debounce = c.get('hold_debounce', 0.15)
        pixel_threshold = c.get('pixel_threshold', 15)

        key_states = {key: False for key in keys}
        action_type = {key: None for key in keys}
        action_start = {key: 0.0 for key in keys}
        last_purple = {key: 0.0 for key in keys}

        zone = {'top': initial_y, 'left': x_start, 'width': width, 'height': height}

        while self.running:
            current_time = time.perf_counter()
            
            img_bgra = np.array(sct.grab(zone))
            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
            
            mask_yellow = cv2.inRange(img_hsv, LOWER_YELLOW, UPPER_YELLOW)
            mask_purple = cv2.inRange(img_hsv, LOWER_PURPLE, UPPER_PURPLE)

            for i, key in enumerate(keys):
                if i >= len(columns_x):
                    break
                    
                col_x = columns_x[i]
                roi_yellow = mask_yellow[:, col_x:col_x+column_width]
                roi_purple = mask_purple[:, col_x:col_x+column_width]
                
                y_px = cv2.countNonZero(roi_yellow)
                p_px = cv2.countNonZero(roi_purple)
                
                if y_px > pixel_threshold:
                    if action_type[key] != 'HOLD': 
                        if action_type[key] != 'TAP' or (current_time - action_start[key] > tap_cooldown):
                            if not key_states[key]:
                                pydirectinput.keyDown(key)
                                key_states[key] = True
                            action_type[key] = 'TAP'
                            action_start[key] = current_time

                if p_px > pixel_threshold:
                    if not key_states[key]:
                        pydirectinput.keyDown(key)
                        key_states[key] = True
                    action_type[key] = 'HOLD' 
                    last_purple[key] = current_time
                    
                if key_states[key]:
                    if action_type[key] == 'TAP':
                        if current_time - action_start[key] > tap_duration:
                            pydirectinput.keyUp(key)
                            key_states[key] = False
                    
                    elif action_type[key] == 'HOLD':
                        if p_px <= pixel_threshold and (current_time - last_purple[key] > hold_debounce):
                            pydirectinput.keyUp(key)
                            key_states[key] = False
                            action_type[key] = None
                            
                if not key_states[key] and action_type[key] == 'TAP':
                    if y_px <= pixel_threshold:
                        action_type[key] = None
            
            # Un micro sleep pour éviter de manger 100% du CPU
            time.sleep(0.001)

# Instance globale
bot_engine = BotEngine()
