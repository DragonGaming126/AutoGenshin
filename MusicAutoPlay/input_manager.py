import pynput
import time

class InputManager:
    def __init__(self):
        self.keyboard_listener = None
        self.mouse_listener = None
        self.last_key = None
        self.last_pos = None

    def _on_press(self, key):
        try:
            self.last_key = key.char
        except AttributeError:
            self.last_key = key.name
        return False  # Stop listener

    def get_next_keypress(self):
        self.last_key = None
        with pynput.keyboard.Listener(on_press=self._on_press) as listener:
            listener.join()
        return self.last_key

    def _on_click(self, x, y, button, pressed):
        if pressed and button == pynput.mouse.Button.left:
            self.last_pos = (int(x), int(y))
            return False # Stop listener

    def get_next_click_position(self):
        self.last_pos = None
        with pynput.mouse.Listener(on_click=self._on_click) as listener:
            listener.join()
        return self.last_pos

# Instance globale
input_manager = InputManager()
