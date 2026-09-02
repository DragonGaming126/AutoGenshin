import time
import pydirectinput
import threading
import json
import os

pydirectinput.PAUSE = 0.0

class AutoskipEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {"skip_key": "f", "interval_ms": 20}

    def save_config(self, new_config):
        self.config.update(new_config)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_config(self):
        return self.config

    def start(self):
        if not self.running:
            self.running = True
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
            return True
        return False

    def _run_loop(self):
        key = self.config.get("skip_key", "f")
        # Conversion ms to seconds
        interval = self.config.get("interval_ms", 20) / 1000.0
        
        while self.running:
            pydirectinput.press(key)
            time.sleep(interval)

# Instance globale
autoskip_engine = AutoskipEngine()
