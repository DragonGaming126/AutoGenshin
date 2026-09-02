import ctypes
import sys
import os
import json

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    # Relance le script avec les droits d'administrateur
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()

from MusicAutoPlay.bot_engine import bot_engine
from MusicAutoPlay.input_manager import input_manager
from Autoskip.bot_engine import autoskip_engine
from Autorecolt.bot_recolt_engine import autorecolt_engine


def start_bot():
    """Démarre le bot d'autoplay"""
    if autoskip_engine.running:
        autoskip_engine.stop()
    success = bot_engine.start()
    return {"success": success, "message": "Bot démarré" if success else "Le bot est déjà en cours d'exécution"}


def stop_bot():
    """Arrête le bot d'autoplay"""
    success = bot_engine.stop()
    return {"success": success, "message": "Bot arrêté" if success else "Le bot n'est pas en cours d'exécution"}


def get_bot_status():
    """Vérifie si le bot tourne"""
    return bot_engine.running


# --- AUTOSKIP ENDPOINTS ---

def start_autoskip():
    """Démarre le bot autoskip"""
    if bot_engine.running:
        bot_engine.stop()
    success = autoskip_engine.start()
    return {"success": success, "message": "Autoskip démarré" if success else "Autoskip est déjà en cours d'exécution"}


def stop_autoskip():
    """Arrête le bot autoskip"""
    success = autoskip_engine.stop()
    return {"success": success, "message": "Autoskip arrêté" if success else "Autoskip n'est pas en cours d'exécution"}


def get_autoskip_status():
    """Vérifie si autoskip tourne"""
    return autoskip_engine.running


def get_autoskip_config():
    """Récupère la configuration autoskip"""
    return autoskip_engine.get_config()


def save_autoskip_config(new_config):
    """Sauvegarde une nouvelle configuration autoskip"""
    autoskip_engine.save_config(new_config)
    return True


# --- AUTORECOLT ENDPOINTS ---

def start_autorecolt():
    """Démarre l'auto-collecte."""
    success = autorecolt_engine.start()
    return {
        "success": success,
        "message": (
            "Auto-collecte démarrée"
            if success else
            "Auto-collecte est déjà en cours d'exécution"
        )
    }


def stop_autorecolt():
    """Arrête l'auto-collecte."""
    success = autorecolt_engine.stop()
    return {
        "success": success,
        "message": (
            "Auto-collecte arrêtée"
            if success else
            "Auto-collecte n'est pas en cours d'exécution"
        )
    }


def get_autorecolt_status():
    """Vérifie si l'auto-collecte tourne."""
    return autorecolt_engine.running


def get_autorecolt_config():
    """Récupère la configuration auto-collecte."""
    return autorecolt_engine.get_config()


def save_autorecolt_config(new_config):
    """Sauvegarde la configuration auto-collecte."""
    return autorecolt_engine.save_config(new_config)


# --- CONFIGURATION MUSIQUE ---

def get_config():
    """Récupère la configuration actuelle"""
    return bot_engine.get_config()


def save_config(new_config):
    """Sauvegarde une nouvelle configuration"""
    bot_engine.save_config(new_config)
    return True


def capture_key():
    """Met le thread en pause et attend une touche clavier"""
    key = input_manager.get_next_keypress()
    return key


def capture_click():
    """Met le thread en pause et attend un clic souris pour récupérer X/Y"""
    pos = input_manager.get_next_click_position()
    return pos


# --- APP CONFIG ENDPOINTS ---

APP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'app_config.json')


def load_app_config():
    if os.path.exists(APP_CONFIG_PATH):
        with open(APP_CONFIG_PATH, 'r') as f:
            return json.load(f)

    return {
        "hotkey_music": "<f6>",
        "hotkey_skip": "<f7>",
        "hotkey_recolt": "<f8>"
    }


def save_app_config(new_config):
    with open(APP_CONFIG_PATH, 'w') as f:
        json.dump(new_config, f, indent=4)


def get_app_config():
    return load_app_config()


def save_and_reload_app_config(new_config):
    save_app_config(new_config)
    reload_hotkeys()
    return True


from pynput import keyboard

hotkey_listener = None


def toggle_autoplay_hotkey():
    if bot_engine.running:
        bot_engine.stop()
    else:
        if autoskip_engine.running:
            autoskip_engine.stop()
        bot_engine.start()



def toggle_autoskip_hotkey():
    if autoskip_engine.running:
        autoskip_engine.stop()
    else:
        if bot_engine.running:
            bot_engine.stop()
        autoskip_engine.start()



def toggle_autorecolt_hotkey():
    """Raccourci global indépendant des modes Musique et Autoskip."""
    if autorecolt_engine.running:
        autorecolt_engine.stop()
    else:
        autorecolt_engine.start()



def reload_hotkeys():
    global hotkey_listener

    if hotkey_listener is not None:
        hotkey_listener.stop()

    app_config = load_app_config()

    hk_music = app_config.get("hotkey_music", "<f6>")
    hk_skip = app_config.get("hotkey_skip", "<f7>")
    hk_recolt = app_config.get("hotkey_recolt", "<f8>")

    hotkey_dict = {}

    if hk_music:
        hotkey_dict[hk_music] = toggle_autoplay_hotkey

    if hk_skip:
        hotkey_dict[hk_skip] = toggle_autoskip_hotkey

    if hk_recolt:
        hotkey_dict[hk_recolt] = toggle_autorecolt_hotkey

    hotkey_listener = keyboard.GlobalHotKeys(hotkey_dict)
    hotkey_listener.start()


# Démarrage initial des raccourcis
reload_hotkeys()


class AppAPI:
    """Pont Python <-> JavaScript utilisé par pywebview.

    Contrairement à Eel, pywebview n'ouvre aucun serveur HTTP localhost :
    l'interface HTML est chargée directement dans une fenêtre native.
    """

    def start_bot(self):
        return start_bot()

    def stop_bot(self):
        return stop_bot()

    def get_bot_status(self):
        return get_bot_status()

    def start_autoskip(self):
        return start_autoskip()

    def stop_autoskip(self):
        return stop_autoskip()

    def get_autoskip_status(self):
        return get_autoskip_status()

    def get_autoskip_config(self):
        return get_autoskip_config()

    def save_autoskip_config(self, new_config):
        return save_autoskip_config(new_config)

    def start_autorecolt(self):
        return start_autorecolt()

    def stop_autorecolt(self):
        return stop_autorecolt()

    def get_autorecolt_status(self):
        return get_autorecolt_status()

    def get_autorecolt_config(self):
        return get_autorecolt_config()

    def save_autorecolt_config(self, new_config):
        return save_autorecolt_config(new_config)

    def get_config(self):
        return get_config()

    def save_config(self, new_config):
        return save_config(new_config)

    def capture_key(self):
        return capture_key()

    def capture_click(self):
        return capture_click()

    def get_app_config(self):
        return get_app_config()

    def save_and_reload_app_config(self, new_config):
        return save_and_reload_app_config(new_config)


if __name__ == '__main__':
    import webview

    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, 'src', 'main_gui.html')

    # Fenêtre native indépendante : aucun navigateur externe et aucun port
    # localhost (donc plus de WinError 10048 sur le port 8000).
    window = webview.create_window(
        'AutoGenshin',
        url=html_path,
        js_api=AppAPI(),
        width=1000,
        height=750,
        min_size=(900, 650),
        resizable=True,
        text_select=False,
    )

    webview.start(debug=False)
