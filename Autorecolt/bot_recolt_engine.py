import ctypes
import json
import threading
import time
from pathlib import Path

import cv2
import mss
import numpy as np
import pydirectinput

pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = False


class AutoRecoltEngine:
    """
    Auto-collecte Genshin.

    Détection:
      - recherche du badge de touche (F/E/autre touche) dans la zone
        d'interaction située à droite de l'écran;
      - recherche multi-échelle de l'ancien template "Examiner" si activé;
      - sélection du moniteur qui contient la fenêtre Genshin au premier plan.

    Sécurité:
      - n'envoie une touche que lorsque Genshin est au premier plan;
      - un prompt détecté ne provoque qu'un appui;
      - le prompt doit disparaître avant un nouvel appui.
    """

    DEFAULT_CONFIG = {
        "enabled": False,
        "interaction_key": "f",
        "mode": "both",
        "scan_interval_ms": 25,
        "cooldown_ms": 100,
        "clear_frames": 2,
        "foreground_only": True,
        "window_title_contains": ["Genshin Impact"],
        "roi": {
            "x": 0.45,
            "y": 0.30,
            "width": 0.55,
            "height": 0.42
        },
        "f_badge": {
            "min_area": 80,
            "max_area": 8000,
            "min_width": 10,
            "max_width": 140,
            "min_height": 10,
            "max_height": 120
        },
        "examiner_template": {
            "enabled": True,
            "threshold": 0.55,
            "scales": [0.60, 0.75, 0.90, 1.05, 1.20, 1.40, 1.60, 1.80, 2.00]
        }
    }

    def __init__(self):
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        base = Path(__file__).resolve().parent
        self.config_path = base / "config.json"
        self.template_path = base / "templates" / "examiner.png"

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
        config = self._merge_config({}, self.DEFAULT_CONFIG)

        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                config = self._merge_config(config, saved)
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
                json.dump(self.config, f, indent=4, ensure_ascii=False)
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
            template = cv2.imread(str(self.template_path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                raise ValueError("template illisible")

            self._template_edges = cv2.Canny(template, 60, 160)
            print(
                f"[AutoRecolt] Template chargé: "
                f"{template.shape[1]}x{template.shape[0]}"
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

    # ---------- Windows ----------

    @staticmethod
    def _foreground_window_title():
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return ""

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""

            buffer = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
        except Exception:
            return ""

    def _game_is_foreground(self):
        if not self.config.get("foreground_only", True):
            return True

        title = self._foreground_window_title().strip().lower()
        if not title:
            return False

        allowed = self.config.get(
            "window_title_contains",
            ["Genshin Impact"]
        )

        return any(
            str(part).strip().lower() in title
            for part in allowed
            if str(part).strip()
        )

    @staticmethod
    def _foreground_window_rect():
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            rect = ctypes.wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None

            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            return None

    @staticmethod
    def _monitor_for_point(sct, px, py):
        for index, monitor in enumerate(sct.monitors[1:], start=1):
            left = monitor["left"]
            top = monitor["top"]
            right = left + monitor["width"]
            bottom = top + monitor["height"]

            if left <= px < right and top <= py < bottom:
                return index

        return 1 if len(sct.monitors) > 1 else 0

    def _get_game_monitor_index(self, sct):
        rect = self._foreground_window_rect()
        if not rect:
            return 1 if len(sct.monitors) > 1 else 0

        left, top, right, bottom = rect
        return self._monitor_for_point(
            sct,
            (left + right) // 2,
            (top + bottom) // 2
        )

    # ---------- Detection ----------

    def _get_roi(self, frame):
        height, width = frame.shape[:2]
        cfg = self.config.get("roi", {})

        x = int(width * float(cfg.get("x", 0.45)))
        y = int(height * float(cfg.get("y", 0.30)))
        w = int(width * float(cfg.get("width", 0.55)))
        h = int(height * float(cfg.get("height", 0.42)))

        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        return frame[y:y + h, x:x + w]

    def _find_key_badges(self, roi):
        if roi is None or roi.size == 0:
            return []

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Les badges de touches de Genshin sont très lumineux,
        # avec une saturation faible à modérée.
        lower = np.array([0, 0, 175], dtype=np.uint8)
        upper = np.array([180, 115, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        cfg = self.config.get("f_badge", {})
        min_area = float(cfg.get("min_area", 80))
        max_area = float(cfg.get("max_area", 8000))
        min_w = int(cfg.get("min_width", 10))
        max_w = int(cfg.get("max_width", 140))
        min_h = int(cfg.get("min_height", 10))
        max_h = int(cfg.get("max_height", 120))

        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if not (min_area <= area <= max_area):
                continue

            x, y, w, h = cv2.boundingRect(contour)

            if not (min_w <= w <= max_w and min_h <= h <= max_h):
                continue

            ratio = w / max(h, 1)
            if not (0.45 <= ratio <= 2.6):
                continue

            # Score: privilégie les rectangles assez compacts.
            rectangularity = area / max(w * h, 1)
            score = (
                min(area / 1200.0, 1.0) * 0.55
                + min(rectangularity / 0.75, 1.0) * 0.45
            )

            candidates.append(
                {
                    "bbox": (x, y, w, h),
                    "area": area,
                    "score": score
                }
            )

        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates

    def _detect_generic_prompt(self, roi):
        candidates = self._find_key_badges(roi)
        if not candidates:
            return None

        # Le prompt d'interaction se trouve généralement dans la partie
        # droite du ROI. On préfère donc les candidats les plus à droite.
        roi_width = roi.shape[1]
        right_candidates = [
            c for c in candidates
            if c["bbox"][0] > roi_width * 0.15
        ]

        pool = right_candidates or candidates
        best = max(
            pool,
            key=lambda c: (
                c["bbox"][0] / max(roi_width, 1) * 0.45
                + c["score"] * 0.55
            )
        )

        return {
            "type": "object",
            "bbox": best["bbox"],
            "confidence": min(0.99, 0.55 + best["score"] * 0.40)
        }

    def _detect_examiner(self, roi):
        if self._template_edges is None:
            return None

        cfg = self.config.get("examiner_template", {})
        if not cfg.get("enabled", True):
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 160)
        template = self._template_edges

        threshold = float(cfg.get("threshold", 0.55))
        scales = cfg.get(
            "scales",
            [0.60, 0.75, 0.90, 1.05, 1.20, 1.40, 1.60, 1.80, 2.00]
        )

        best_score = 0.0
        best_bbox = None

        for scale in scales:
            scaled_w = max(20, int(template.shape[1] * float(scale)))
            scaled_h = max(12, int(template.shape[0] * float(scale)))

            if scaled_w >= edges.shape[1] or scaled_h >= edges.shape[0]:
                continue

            scaled = cv2.resize(
                template,
                (scaled_w, scaled_h),
                interpolation=cv2.INTER_AREA
            )

            result = cv2.matchTemplate(
                edges, scaled, cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_score:
                best_score = float(max_val)
                best_bbox = (
                    max_loc[0],
                    max_loc[1],
                    scaled_w,
                    scaled_h
                )

        if best_bbox is not None and best_score >= threshold:
            return {
                "type": "examiner",
                "bbox": best_bbox,
                "confidence": best_score
            }

        return None

    def _select_detection(self, roi):
        mode = str(self.config.get("mode", "both")).lower()
        if mode not in ("examiner", "objects", "both"):
            mode = "both"

        generic = (
            self._detect_generic_prompt(roi)
            if mode in ("objects", "both")
            else None
        )

        examiner = (
            self._detect_examiner(roi)
            if mode in ("examiner", "both")
            else None
        )

        if mode == "objects":
            return generic
        if mode == "examiner":
            return examiner

        # Pour "both", le badge de touche est une preuve plus directe
        # de la présence d'une interaction exploitable.
        if generic is not None:
            return generic

        return examiner

    @staticmethod
    def _prompt_signature(roi, detection):
        if detection is None:
            return None

        x, y, w, h = detection["bbox"]

        x1 = max(0, x - int(w * 0.5))
        y1 = max(0, y - int(h * 0.8))
        x2 = min(roi.shape[1], x + max(int(w * 12), 100))
        y2 = min(roi.shape[0], y + int(h * 2.5))

        crop = roi[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        small = cv2.resize(crop, (48, 24), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return gray.astype(np.float32)

    @staticmethod
    def _signature_changed(previous, current):
        if previous is None or current is None:
            return True

        diff = np.mean(np.abs(previous - current)) / 255.0
        return diff >= 0.08

    def _press_interaction(self, key):
        try:
            # keyDown/keyUp séparés sont plus fiables que press() avec
            # certaines applications qui filtrent les événements rapides.
            pydirectinput.keyDown(key)
            time.sleep(0.015)
            pydirectinput.keyUp(key)
            return True
        except Exception as e:
            print(f"[AutoRecolt] Erreur touche '{key}' : {e}")
            return False

    def _run_loop(self):
        scan_interval = max(
            0.015,
            float(self.config.get("scan_interval_ms", 25)) / 1000.0
        )
        cooldown = max(
            0.05,
            float(self.config.get("cooldown_ms", 100)) / 1000.0
        )
        clear_required = max(
            1,
            int(self.config.get("clear_frames", 2))
        )

        interaction_key = (
            str(self.config.get("interaction_key", "f"))
            .strip()
            .lower()
            or "f"
        )

        last_press = 0.0
        last_signature = None
        clear_frames = 0
        last_monitor = None

        try:
            with mss.mss() as sct:
                while self.running:
                    # Ne pas tenter d'interagir avec l'interface AutoGenshin
                    # ou une autre fenêtre.
                    if not self._game_is_foreground():
                        clear_frames = clear_required
                        last_signature = None
                        time.sleep(0.05)
                        continue

                    monitor_index = self._get_game_monitor_index(sct)

                    if monitor_index != last_monitor:
                        print(
                            f"[AutoRecolt] Moniteur actif: {monitor_index}"
                        )
                        last_monitor = monitor_index

                    frame = np.array(sct.grab(sct.monitors[monitor_index]))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    roi = self._get_roi(frame)

                    detection = self._select_detection(roi)

                    if detection is None:
                        clear_frames += 1
                        if clear_frames >= clear_required:
                            last_signature = None
                        time.sleep(scan_interval)
                        continue

                    clear_frames = 0
                    signature = self._prompt_signature(roi, detection)
                    now = time.monotonic()

                    if now - last_press < cooldown:
                        time.sleep(scan_interval)
                        continue

                    # Un prompt identique ne doit pas être re-déclenché.
                    if (
                        last_signature is not None
                        and not self._signature_changed(
                            last_signature, signature
                        )
                    ):
                        time.sleep(scan_interval)
                        continue

                    # Revalide le focus juste avant l'envoi.
                    if not self._game_is_foreground():
                        last_signature = None
                        time.sleep(scan_interval)
                        continue

                    if self._press_interaction(interaction_key):
                        last_press = time.monotonic()
                        last_signature = signature
                        print(
                            f"[AutoRecolt] Interaction détectée "
                            f"({detection['type']}, "
                            f"{detection['confidence']:.2f}) -> "
                            f"{interaction_key.upper()}"
                        )

                    time.sleep(scan_interval)

        except Exception as e:
            print(f"[AutoRecolt] Erreur moteur : {e}")

        finally:
            self.running = False


autorecolt_engine = AutoRecoltEngine()
