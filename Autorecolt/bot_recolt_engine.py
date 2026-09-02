import ctypes
from ctypes import wintypes
import json
import threading
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import pydirectinput


pydirectinput.PAUSE = 0.0


class AutoRecoltEngine:
    """
    Moteur d'auto-collecte.

    Modes :
      - examiner : uniquement "Examiner"
      - objects   : objets/ressources
      - both      : les deux

    Le moteur détecte une interaction, appuie une fois, puis attend que
    le prompt disparaisse ou change avant d'autoriser un nouvel appui.
    """

    DEFAULT_CONFIG = {
        "enabled": False,
        "interaction_key": "f",
        "mode": "both",
        "scan_interval_ms": 35,
        "cooldown_ms": 250,
        "stable_frames": 2,
        "clear_frames": 3,
        "change_frames": 4,
        "change_threshold": 0.22,
        "require_genshin_foreground": True,
        "genshin_window_keywords": ["genshin impact", "原神"],
        "roi": {
            "x": 0.50,
            "y": 0.36,
            "width": 0.49,
            "height": 0.30
        },
        "f_badge": {
            "min_area": 120,
            "max_area": 6000,
            "min_width": 12,
            "max_width": 110,
            "min_height": 12,
            "max_height": 110
        },
        "examiner_template": {
            "enabled": True,
            "threshold": 0.52,
            "scales": [0.75, 0.90, 1.05, 1.20, 1.40, 1.60, 1.80, 2.00]
        }
    }

    def __init__(self):
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        self.config_path = Path(__file__).resolve().parent / "config.json"
        self.template_path = (
            Path(__file__).resolve().parent / "templates" / "examiner.png"
        )

        self.config = self.load_config()

        self._template_edges = None
        self._load_examiner_template()

    def _merge_config(self, base, override):
        if not isinstance(base, dict) or not isinstance(override, dict):
            return override

        result = dict(base)

        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value

        return result

    def load_config(self):
        config = dict(self.DEFAULT_CONFIG)

        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)

                config = self._merge_config(self.DEFAULT_CONFIG, saved)

            except Exception as e:
                print(f"[AutoRecolt] Erreur config : {e}")

        return config

    def save_config(self, new_config):
        if not isinstance(new_config, dict):
            return False

        self.config = self._merge_config(self.config, new_config)

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(
                    self.config,
                    f,
                    indent=4,
                    ensure_ascii=False
                )

            return True

        except Exception as e:
            print(f"[AutoRecolt] Impossible de sauvegarder la config : {e}")
            return False

    def get_config(self):
        return self.config

    def _load_examiner_template(self):
        if not self.template_path.exists():
            print("[AutoRecolt] Template Examiner absent.")
            return

        try:
            template = cv2.imread(
                str(self.template_path),
                cv2.IMREAD_GRAYSCALE
            )

            if template is None:
                raise ValueError("template illisible")

            self._template_edges = cv2.Canny(
                template,
                60,
                160
            )

        except Exception as e:
            print(f"[AutoRecolt] Erreur template Examiner : {e}")
            self._template_edges = None

    def start(self):
        with self.lock:
            if self.running:
                return False

            self.config = self.load_config()
            self.running = True

            self.thread = threading.Thread(
                target=self._run_loop,
                name="AutoRecolt",
                daemon=True
            )

            self.thread.start()

        print("[AutoRecolt] Démarré")
        return True

    def stop(self):
        with self.lock:
            if not self.running:
                return False

            self.running = False
            thread = self.thread

        if thread and thread.is_alive():
            thread.join(timeout=1.5)

        print("[AutoRecolt] Arrêté")
        return True

    def _get_roi(self, frame):
        height, width = frame.shape[:2]
        roi_cfg = self.config.get("roi", {})

        x = int(width * float(roi_cfg.get("x", 0.50)))
        y = int(height * float(roi_cfg.get("y", 0.36)))
        w = int(width * float(roi_cfg.get("width", 0.49)))
        h = int(height * float(roi_cfg.get("height", 0.30)))

        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        return frame[y:y + h, x:x + w]

    def _find_f_badge(self, roi):
        if roi is None or roi.size == 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Le badge de la touche est clair/blanc.
        lower = np.array([0, 0, 180], dtype=np.uint8)
        upper = np.array([180, 95, 255], dtype=np.uint8)

        mask = cv2.inRange(hsv, lower, upper)

        kernel = np.ones((3, 3), np.uint8)

        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=1
        )

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        cfg = self.config.get("f_badge", {})

        min_area = float(cfg.get("min_area", 120))
        max_area = float(cfg.get("max_area", 6000))
        min_w = int(cfg.get("min_width", 12))
        max_w = int(cfg.get("max_width", 110))
        min_h = int(cfg.get("min_height", 12))
        max_h = int(cfg.get("max_height", 110))

        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)

            if area < min_area or area > max_area:
                continue

            x, y, w, h = cv2.boundingRect(contour)

            if not (min_w <= w <= max_w):
                continue

            if not (min_h <= h <= max_h):
                continue

            ratio = w / max(h, 1)

            if ratio < 0.45 or ratio > 2.2:
                continue

            candidates.append((x, y, w, h, area))

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[4],
            reverse=True
        )

        x, y, w, h, area = candidates[0]

        return {
            "bbox": (x, y, w, h),
            "area": area
        }

    def _detect_generic_prompt(self, roi):
        badge = self._find_f_badge(roi)

        if badge is None:
            return None

        x, y, w, h = badge["bbox"]

        right_x1 = min(
            roi.shape[1],
            x + w + 4
        )

        right_x2 = min(
            roi.shape[1],
            x + w + max(100, int(w * 9))
        )

        right_y1 = max(
            0,
            y - int(h * 0.25)
        )

        right_y2 = min(
            roi.shape[0],
            y + int(h * 1.45)
        )

        if right_x2 <= right_x1 or right_y2 <= right_y1:
            return None

        area = roi[
            right_y1:right_y2,
            right_x1:right_x2
        ]

        if area.size == 0:
            return None

        gray = cv2.cvtColor(
            area,
            cv2.COLOR_BGR2GRAY
        )

        mean_value = float(np.mean(gray))
        bright_pixels = float(np.mean(gray > 170))

        confidence = 0.65

        if mean_value < 145:
            confidence += 0.12

        if bright_pixels > 0.01:
            confidence += 0.08

        return {
            "type": "object",
            "bbox": badge["bbox"],
            "confidence": min(confidence, 0.99)
        }

    def _detect_examiner(self, roi):
        if self._template_edges is None:
            return None

        if not self.config.get(
            "examiner_template",
            {}
        ).get("enabled", True):
            return None

        gray = cv2.cvtColor(
            roi,
            cv2.COLOR_BGR2GRAY
        )

        edges = cv2.Canny(
            gray,
            60,
            160
        )

        template = self._template_edges

        if template is None or template.size == 0:
            return None

        cfg = self.config.get(
            "examiner_template",
            {}
        )

        threshold = float(
            cfg.get("threshold", 0.52)
        )

        scales = cfg.get(
            "scales",
            [0.75, 0.90, 1.05, 1.20, 1.40, 1.60, 1.80, 2.00]
        )

        best_score = 0.0
        best_bbox = None

        for scale in scales:
            scaled_w = max(
                20,
                int(template.shape[1] * float(scale))
            )

            scaled_h = max(
                12,
                int(template.shape[0] * float(scale))
            )

            if (
                scaled_w >= edges.shape[1]
                or scaled_h >= edges.shape[0]
            ):
                continue

            scaled = cv2.resize(
                template,
                (scaled_w, scaled_h),
                interpolation=cv2.INTER_AREA
            )

            result = cv2.matchTemplate(
                edges,
                scaled,
                cv2.TM_CCOEFF_NORMED
            )

            _, max_val, _, max_loc = cv2.minMaxLoc(
                result
            )

            if max_val > best_score:
                best_score = float(max_val)

                best_bbox = (
                    max_loc[0],
                    max_loc[1],
                    scaled_w,
                    scaled_h
                )

        if (
            best_bbox is not None
            and best_score >= threshold
        ):
            return {
                "type": "examiner",
                "bbox": best_bbox,
                "confidence": best_score
            }

        return None

    def _prompt_signature(self, roi, detection):
        if detection is None:
            return None

        x, y, w, h = detection["bbox"]

        x1 = max(
            0,
            x - int(w * 0.2)
        )

        y1 = max(
            0,
            y - int(h * 0.5)
        )

        x2 = min(
            roi.shape[1],
            x + max(w * 8, 80)
        )

        y2 = min(
            roi.shape[0],
            y + int(h * 1.8)
        )

        crop = roi[
            y1:y2,
            x1:x2
        ]

        if crop.size == 0:
            return None

        small = cv2.resize(
            crop,
            (32, 16),
            interpolation=cv2.INTER_AREA
        )

        gray = cv2.cvtColor(
            small,
            cv2.COLOR_BGR2GRAY
        )

        return gray.astype(np.float32)

    def _signature_changed(self, previous, current):
        if previous is None or current is None:
            return True

        if previous.shape != current.shape:
            return True

        diff = np.mean(
            np.abs(previous - current)
        ) / 255.0

        return diff >= 0.10

    def _select_detection(self, roi):
        mode = str(
            self.config.get("mode", "both")
        ).lower()

        if mode not in (
            "examiner",
            "objects",
            "both"
        ):
            mode = "both"

        generic = None
        examiner = None

        if mode in ("objects", "both"):
            generic = self._detect_generic_prompt(roi)

        if mode in ("examiner", "both"):
            examiner = self._detect_examiner(roi)

        if mode == "objects":
            return generic

        if mode == "examiner":
            return examiner

        if examiner is not None and generic is not None:
            if examiner["confidence"] >= generic["confidence"]:
                return examiner
            return generic

        return examiner or generic

    def _get_window_text(self, hwnd):
        try:
            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value or ""
        except Exception:
            return ""

    def _find_genshin_window(self):
        """Trouve la fenêtre visible de Genshin sans dépendance externe."""
        keywords = [
            str(k).lower()
            for k in self.config.get("genshin_window_keywords", ["genshin impact", "原神"])
            if k
        ]
        user32 = ctypes.windll.user32
        found = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = self._get_window_text(hwnd).strip()
            if not title:
                return True
            low = title.lower()
            if any(k in low for k in keywords):
                rect = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    if rect.right > rect.left and rect.bottom > rect.top:
                        found.append((hwnd, title, (rect.left, rect.top, rect.right, rect.bottom)))
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
        if not found:
            return None

        foreground = user32.GetForegroundWindow()
        for item in found:
            if item[0] == foreground:
                return item
        return found[0]

    def _is_genshin_foreground(self):
        target = self._find_genshin_window()
        return bool(target and target[0] == ctypes.windll.user32.GetForegroundWindow())

    def _focus_genshin(self, hwnd):
        """Rend Genshin actif juste avant l'envoi de la touche."""
        user32 = ctypes.windll.user32
        try:
            if user32.GetForegroundWindow() == hwnd:
                return True

            SW_RESTORE = 9
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)

            # GetCurrentThreadId appartient à kernel32, pas user32.
            # On n'a de toute façon pas besoin d'AttachThreadInput ici :
            # SetForegroundWindow/BringWindowToTop suffisent pour notre cas.
            foreground = user32.GetForegroundWindow()

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.08)
            return user32.GetForegroundWindow() == hwnd
        except Exception as e:
            print(f"[AutoRecolt] Impossible de reprendre le focus Genshin : {e}")
            return False

    def _send_interaction(self, key):
        """Envoie une touche avec Win32 SendInput (compatible x86/x64)."""
        user32 = ctypes.windll.user32

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_SCANCODE = 0x0008

        special = {
            "space": 0x20,
            "enter": 0x0D,
            "escape": 0x1B,
            "esc": 0x1B,
            "tab": 0x09,
            "shift": 0x10,
            "ctrl": 0x11,
            "control": 0x11,
            "alt": 0x12,
            "backspace": 0x08,
            "delete": 0x2E,
            "up": 0x26,
            "down": 0x28,
            "left": 0x25,
            "right": 0x27,
        }

        function_keys = {f"f{i}": 0x6F + i for i in range(1, 13)}

        key = str(key).strip().lower()
        if len(key) == 1:
            vk = ord(key.upper())
        else:
            vk = special.get(key, function_keys.get(key))

        if vk is None:
            raise ValueError(f"Touche non supportée : {key}")

        # Win32 SendInput attend exactement :
        # INPUT = DWORD type + union { MOUSEINPUT | KEYBDINPUT | HARDWAREINPUT }.
        # L'union garantit l'alignement correct sur x86 et x64.
        # En ctypes, l'union garantit l'alignement correct.
        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [
                ("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [
                ("type", ctypes.c_ulong),
                ("u", INPUT_UNION),
            ]

        # Utilise le scan code physique plutôt que wVk seul.
        # C'est généralement plus fiable pour un jeu DirectX.
        MAPVK_VK_TO_VSC = 0
        user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        user32.MapVirtualKeyW.restype = wintypes.UINT
        scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)

        if not scan:
            # Fallback : SendInput en VK si Windows ne donne pas de scan code.
            down_ki = KEYBDINPUT(vk, 0, 0, 0, 0)
            up_ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
        else:
            down_ki = KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, 0)
            up_ki = KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)

        inputs = (INPUT * 2)(
            INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=down_ki)),
            INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=up_ki)),
        )

        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT

        sent = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        if sent != 2:
            raise ctypes.WinError()

    def _run_loop(self):
        scan_interval = max(
            0.015,
            float(self.config.get("scan_interval_ms", 35)) / 1000.0
        )
        cooldown = max(
            0.05,
            float(self.config.get("cooldown_ms", 120)) / 1000.0
        )
        clear_frames_required = max(
            1,
            int(self.config.get("clear_frames", 2))
        )
        change_frames_required = max(
            1,
            int(self.config.get("change_frames", 3))
        )
        change_threshold = float(
            self.config.get("change_threshold", 0.22)
        )
        interaction_key = str(
            self.config.get("interaction_key", "f")
        ).strip().lower() or "f"

        armed = True
        clear_frames = 0
        change_frames = 0
        last_signature = None
        candidate_signature = None
        last_press = 0.0
        last_focus = None
        last_window_handle = None

        try:
            with mss.mss() as sct:
                monitor_index = 1 if len(sct.monitors) > 1 else 0

                while self.running:
                    target_window = self._find_genshin_window()
                    if target_window:
                        last_window_handle = target_window[0]

                        # Choisit le moniteur qui contient le centre de la fenêtre Genshin.
                        left, top, right, bottom = target_window[2]
                        cx = (left + right) / 2
                        cy = (top + bottom) / 2
                        for idx, mon in enumerate(sct.monitors):
                            if (mon["left"] <= cx < mon["left"] + mon["width"] and
                                    mon["top"] <= cy < mon["top"] + mon["height"]):
                                monitor_index = idx
                                break

                    focused = bool(
                        target_window and
                        target_window[0] == ctypes.windll.user32.GetForegroundWindow()
                    )

                    if focused != last_focus:
                        if focused:
                            print("[AutoRecolt] Genshin au premier plan -> surveillance active")
                        elif target_window:
                            print("[AutoRecolt] Genshin en arrière-plan -> détection maintenue")
                        else:
                            print("[AutoRecolt] Fenêtre Genshin introuvable")
                        last_focus = focused

                    if not target_window:
                        time.sleep(scan_interval)
                        continue

                    # IMPORTANT : on continue à analyser l'écran même si Genshin
                    # n'est pas la fenêtre active. Sinon, après une perte de focus,
                    # le moteur ne pourrait jamais atteindre la logique qui reprend
                    # le focus pour envoyer l'interaction suivante.
                    frame = np.array(sct.grab(sct.monitors[monitor_index]))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    roi = self._get_roi(frame)
                    detection = self._select_detection(roi)

                    if detection is None:
                        clear_frames += 1
                        change_frames = 0
                        candidate_signature = None
                        if clear_frames >= clear_frames_required:
                            armed = True
                            last_signature = None
                        time.sleep(scan_interval)
                        continue

                    clear_frames = 0
                    signature = self._prompt_signature(roi, detection)
                    if signature is None:
                        time.sleep(scan_interval)
                        continue

                    now = time.monotonic()

                    if armed and (now - last_press) >= cooldown:
                        try:
                            # Rechercher la fenêtre juste avant l'envoi : elle peut
                            # avoir changé entre la capture et cette ligne.
                            target = self._find_genshin_window()
                            if not target:
                                time.sleep(scan_interval)
                                continue

                            if not self._focus_genshin(target[0]):
                                print("[AutoRecolt] Impossible d'activer Genshin -> appui annulé")
                                time.sleep(scan_interval)
                                continue

                            # Double vérification du focus après SetForegroundWindow.
                            if ctypes.windll.user32.GetForegroundWindow() != target[0]:
                                print("[AutoRecolt] Genshin non actif après focus -> appui annulé")
                                time.sleep(scan_interval)
                                continue

                            self._send_interaction(interaction_key)
                            last_press = time.monotonic()
                            last_signature = signature.copy()
                            candidate_signature = None
                            change_frames = 0
                            armed = False
                            print(
                                f"[AutoRecolt] Interaction détectée "
                                f"({detection['type']}, {detection['confidence']:.2f}) -> "
                                f"{interaction_key.upper()}"
                            )
                        except Exception as e:
                            print(f"[AutoRecolt] Erreur touche : {e}")

                        time.sleep(scan_interval)
                        continue

                    # Même si le prompt reste affiché quelques frames, aucun spam.
                    # Un nouvel appui n'est permis qu'après disparition du prompt ou
                    # un changement réel et stable de celui-ci.
                    if not armed and last_signature is not None:
                        diff = np.mean(np.abs(last_signature - signature)) / 255.0

                        if diff >= change_threshold:
                            if candidate_signature is None:
                                change_frames = 1
                                candidate_signature = signature.copy()
                            else:
                                candidate_diff = np.mean(
                                    np.abs(candidate_signature - signature)
                                ) / 255.0
                                if candidate_diff < 0.08:
                                    change_frames += 1
                                else:
                                    change_frames = 1
                                candidate_signature = signature.copy()

                            if change_frames >= change_frames_required:
                                armed = True
                                candidate_signature = None
                                change_frames = 0
                        else:
                            change_frames = 0
                            candidate_signature = None

                    time.sleep(scan_interval)

        except Exception as e:
            print(f"[AutoRecolt] Erreur moteur : {e}")
        finally:
            self.running = False


autorecolt_engine = AutoRecoltEngine()
