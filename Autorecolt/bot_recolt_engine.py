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
        "cooldown_ms": 120,
        "clear_frames": 2,
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

    def _run_loop(self):
        scan_interval = max(
            0.015,
            float(
                self.config.get(
                    "scan_interval_ms",
                    35
                )
            ) / 1000.0
        )

        cooldown = max(
            0.05,
            float(
                self.config.get(
                    "cooldown_ms",
                    120
                )
            ) / 1000.0
        )

        clear_frames_required = max(
            1,
            int(
                self.config.get(
                    "clear_frames",
                    2
                )
            )
        )

        interaction_key = str(
            self.config.get(
                "interaction_key",
                "f"
            )
        ).strip().lower() or "f"

        last_press = 0.0
        last_signature = None
        clear_frames = 0

        try:
            with mss.mss() as sct:
                monitor_index = (
                    1 if len(sct.monitors) > 1 else 0
                )

                while self.running:
                    frame = np.array(
                        sct.grab(
                            sct.monitors[monitor_index]
                        )
                    )

                    frame = cv2.cvtColor(
                        frame,
                        cv2.COLOR_BGRA2BGR
                    )

                    roi = self._get_roi(frame)

                    detection = self._select_detection(
                        roi
                    )

                    if detection is None:
                        clear_frames += 1

                        if (
                            clear_frames
                            >= clear_frames_required
                        ):
                            last_signature = None

                        time.sleep(scan_interval)
                        continue

                    clear_frames = 0

                    signature = self._prompt_signature(
                        roi,
                        detection
                    )

                    now = time.monotonic()

                    can_press = (
                        now - last_press
                    ) >= cooldown

                    if can_press:
                        should_press = (
                            last_signature is None
                        )

                        if not should_press:
                            should_press = (
                                self._signature_changed(
                                    last_signature,
                                    signature
                                )
                            )

                        if should_press:
                            try:
                                pydirectinput.press(
                                    interaction_key
                                )

                                last_press = now
                                last_signature = signature

                            except Exception as e:
                                print(
                                    "[AutoRecolt] "
                                    f"Erreur touche : {e}"
                                )

                    time.sleep(scan_interval)

        except Exception as e:
            print(
                "[AutoRecolt] "
                f"Erreur moteur : {e}"
            )

        finally:
            self.running = False


autorecolt_engine = AutoRecoltEngine()
