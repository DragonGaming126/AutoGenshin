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

import eel
from MusicAutoPlay.bot_engine import bot_engine
from MusicAutoPlay.input_manager import input_manager
from Autoskip.bot_engine import autoskip_engine

# Configuration Eel
# L'application Eel sera servie à partir du dossier 'src'
eel.init('src')

@eel.expose
def start_bot():
    """Démarre le bot d'autoplay"""
    if autoskip_engine.running:
        autoskip_engine.stop()
    success = bot_engine.start()
    return {"success": success, "message": "Bot démarré" if success else "Le bot est déjà en cours d'exécution"}

@eel.expose
def stop_bot():
    """Arrête le bot d'autoplay"""
    success = bot_engine.stop()
    return {"success": success, "message": "Bot arrêté" if success else "Le bot n'est pas en cours d'exécution"}

@eel.expose
def get_bot_status():
    """Vérifie si le bot tourne"""
    return bot_engine.running

# --- AUTOSKIP ENDPOINTS ---

@eel.expose
def start_autoskip():
    """Démarre le bot autoskip"""
    if bot_engine.running:
        bot_engine.stop()
    success = autoskip_engine.start()
    return {"success": success, "message": "Autoskip démarré" if success else "Autoskip est déjà en cours d'exécution"}

@eel.expose
def stop_autoskip():
    """Arrête le bot autoskip"""
    success = autoskip_engine.stop()
    return {"success": success, "message": "Autoskip arrêté" if success else "Autoskip n'est pas en cours d'exécution"}

@eel.expose
def get_autoskip_status():
    """Vérifie si autoskip tourne"""
    return autoskip_engine.running

@eel.expose
def get_autoskip_config():
    """Récupère la configuration autoskip"""
    return autoskip_engine.get_config()

@eel.expose
def save_autoskip_config(new_config):
    """Sauvegarde une nouvelle configuration autoskip"""
    autoskip_engine.save_config(new_config)
    return True

@eel.expose
def get_config():
    """Récupère la configuration actuelle"""
    return bot_engine.get_config()

@eel.expose
def save_config(new_config):
    """Sauvegarde une nouvelle configuration"""
    bot_engine.save_config(new_config)
    return True

@eel.expose
def capture_key():
    """Met le thread en pause et attend une touche clavier"""
    key = input_manager.get_next_keypress()
    return key

@eel.expose
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
    return {"hotkey_music": "<f6>", "hotkey_skip": "<f7>"}

def save_app_config(new_config):
    with open(APP_CONFIG_PATH, 'w') as f:
        json.dump(new_config, f, indent=4)

@eel.expose
def get_app_config():
    return load_app_config()

@eel.expose
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
    try:
        eel.updateBotUIStatus(bot_engine.running)()
        eel.updateAutoskipUIStatus(autoskip_engine.running)()
    except Exception:
        pass

def toggle_autoskip_hotkey():
    if autoskip_engine.running:
        autoskip_engine.stop()
    else:
        if bot_engine.running:
            bot_engine.stop()
        autoskip_engine.start()
    try:
        eel.updateBotUIStatus(bot_engine.running)()
        eel.updateAutoskipUIStatus(autoskip_engine.running)()
    except Exception:
        pass

def reload_hotkeys():
    global hotkey_listener
    if hotkey_listener is not None:
        hotkey_listener.stop()
    
    app_config = load_app_config()
    hk_music = app_config.get("hotkey_music", "<f6>")
    hk_skip = app_config.get("hotkey_skip", "<f7>")
    
    hotkey_dict = {}
    if hk_music:
        hotkey_dict[hk_music] = toggle_autoplay_hotkey
    if hk_skip:
        hotkey_dict[hk_skip] = toggle_autoskip_hotkey
        
    hotkey_listener = keyboard.GlobalHotKeys(hotkey_dict)
    hotkey_listener.start()

# Démarrage initial des raccourcis
reload_hotkeys()

if __name__ == '__main__':
    # Options pour une application standalone plus clean
    eel_kwargs = {
        'size': (1000, 750),
        'position': (300, 200),
    }
    
    try:
        # Essaye de démarrer avec Edge (très courant sur Windows) ou Chrome
        eel.start('main_gui.html', mode='edge', **eel_kwargs)
    except Exception as e:
        # Fallback sur le navigateur par défaut
        print(f"Erreur avec Edge/Chrome: {e}. Lancement avec le navigateur par défaut.")
        eel.start('main_gui.html', mode='default', **eel_kwargs)
