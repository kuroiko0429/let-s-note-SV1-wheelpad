"""
Let's Note Wheelpad Scroll Daemon
=================================
Panasonic Let's Note のホイールパッドの縁を円形になぞることで
スクロールを実現するデーモンスクリプト。

Features:
  - スムーズスクロール (REL_WHEEL_HI_RES)
  - 水平スクロール (2本指で縁をなぞる)
  - 動的速度調整 (回転速度に応じて加速)
  - 慣性スクロール (フリック後に減速しながら継続)
  - TOML 設定ファイル対応
"""

import argparse
import math
import os
import sys
import threading
import time
import logging
import tomllib
from evdev import InputDevice, UInput, ecodes, list_devices

# ==========================================
# デフォルト設定値
# ==========================================
DEFAULTS = {
    "device": {
        "name": "Synaptics TM3562-003",
    },
    "wheelpad": {
        "center_x": 264,
        "center_y": 264,
        "deadzone": 195,
        "sensitivity": 0.3,
        "hires_step": 60,
        "natural_scroll": False,
    },
    "speed": {
        "thresholds": [
            {"velocity": 8.0, "multiplier": 4},
            {"velocity": 4.0, "multiplier": 3},
            {"velocity": 2.0, "multiplier": 2},
        ],
    },
    "inertia": {
        "enabled": True,
        "friction": 0.85,
        "min_velocity": 0.5,
        "interval": 0.016,
    },
}

# 設定ファイルの検索パス（優先順）
CONFIG_SEARCH_PATHS = [
    "/etc/wheelpad/config.toml",
]

# ==========================================
# ロギング設定
# ==========================================
logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wheelpad")


# ==========================================
# 設定管理
# ==========================================
def deep_merge(base: dict, override: dict) -> dict:
    """辞書を再帰的にマージする（override が優先）"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | None = None) -> dict:
    """設定ファイルを読み込みデフォルト値とマージする"""
    # CLI で指定された場合はそのパスのみ試す
    if config_path:
        path = os.path.expanduser(config_path)
        if os.path.isfile(path):
            log.info("設定ファイル読み込み: %s", path)
            with open(path, "rb") as f:
                return deep_merge(DEFAULTS, tomllib.load(f))
        else:
            log.warning("指定された設定ファイルが見つかりません: %s (デフォルト値を使用)", path)
            return DEFAULTS.copy()

    # 検索パスを順に探す
    for path in CONFIG_SEARCH_PATHS:
        if os.path.isfile(path):
            log.info("設定ファイル読み込み: %s", path)
            with open(path, "rb") as f:
                return deep_merge(DEFAULTS, tomllib.load(f))

    log.info("設定ファイルなし — デフォルト値を使用")
    return DEFAULTS.copy()


# ==========================================
# ユーティリティ
# ==========================================
def find_touchpad(device_name: str) -> str | None:
    """evdev デバイス一覧からタッチパッドを探す"""
    for path in list_devices():
        dev = InputDevice(path)
        if device_name in dev.name:
            log.info("タッチパッド発見: %s (%s)", dev.name, path)
            return path
    return None


def normalize_angle(diff: float) -> float:
    """角度差を -π ~ π に正規化する"""
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi
    return diff


def calc_speed_multiplier(angular_velocity: float, thresholds: list[dict]) -> int:
    """角速度 (rad/s) から速度倍率を返す"""
    for entry in thresholds:
        if angular_velocity >= entry["velocity"]:
            return entry["multiplier"]
    return 1


# ==========================================
# 慣性スクロールエンジン
# ==========================================
class InertiaEngine:
    """指を離した後に減速しながらスクロールを継続する"""

    def __init__(self, v_scroll, cfg: dict):
        self.v_scroll = v_scroll
        self.friction = cfg["friction"]
        self.min_velocity = cfg["min_velocity"]
        self.interval = cfg["interval"]
        self.enabled = cfg["enabled"]

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def trigger(self, angular_velocity: float, direction: int, horizontal: bool,
                hires_step: int):
        """慣性スクロールを開始する（前回の慣性があればキャンセル）"""
        if not self.enabled:
            return

        self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(abs(angular_velocity), direction, horizontal, hires_step),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """慣性スクロールを停止する"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.1)

    def _run(self, velocity: float, direction: int, horizontal: bool, hires_step: int):
        """減速ループ（別スレッドで実行）"""
        while velocity > self.min_velocity and not self._stop_event.is_set():
            hires_value = direction * int(hires_step * (velocity / 2.0))
            # 最低でも1ステップは出力する
            if abs(hires_value) < 1:
                hires_value = direction

            if horizontal:
                self.v_scroll.write(ecodes.EV_REL, ecodes.REL_HWHEEL, direction)
                self.v_scroll.write(ecodes.EV_REL, ecodes.REL_HWHEEL_HI_RES, hires_value)
            else:
                self.v_scroll.write(ecodes.EV_REL, ecodes.REL_WHEEL, direction)
                self.v_scroll.write(ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, hires_value)
            self.v_scroll.syn()

            velocity *= self.friction
            time.sleep(self.interval)


# ==========================================
# メインデーモン
# ==========================================
class WheelpadDaemon:
    """ホイールパッドのスクロール処理を管理するデーモン"""

    def __init__(self, device_path: str, cfg: dict):
        self.cfg_wp = cfg["wheelpad"]
        self.cfg_speed = cfg["speed"]

        self.pad = InputDevice(device_path)
        self.pad.grab()

        # 仮想デバイス: 通常のタッチパッドイベント転送用
        self.v_pad = UInput.from_device(self.pad, name="LetsNote-Virtual-Pad")

        # 仮想デバイス: スクロールイベント出力用 (HI_RES 対応)
        self.v_scroll = UInput(
            {
                ecodes.EV_REL: [
                    ecodes.REL_WHEEL,
                    ecodes.REL_WHEEL_HI_RES,
                    ecodes.REL_HWHEEL,
                    ecodes.REL_HWHEEL_HI_RES,
                ],
            },
            name="LetsNote-Virtual-Wheel",
        )

        # 慣性スクロールエンジン
        self.inertia = InertiaEngine(self.v_scroll, cfg["inertia"])

        # 状態管理
        self.buffer: list = []
        self.is_touching = False
        self.scroll_mode = False
        self.finger_count = 0
        self.last_angle: float | None = None
        self.last_time: float | None = None
        self.last_direction = 1
        self.last_horizontal = False
        self.last_angular_velocity = 0.0
        self.current_x = self.cfg_wp["center_x"]
        self.current_y = self.cfg_wp["center_y"]

        # ナチュラルスクロール用の符号
        self._scroll_sign = -1 if self.cfg_wp["natural_scroll"] else 1

        log.info("デーモン起動: %s (%s)", self.pad.name, device_path)

    def run(self):
        """メインイベントループ"""
        try:
            for event in self.pad.read_loop():
                self.buffer.append(event)
                self._update_position(event)

                if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                    self._process_frame()
                    self.buffer.clear()
        except KeyboardInterrupt:
            log.info("シャットダウン...")
        finally:
            self.cleanup()

    def cleanup(self):
        """リソース解放"""
        self.inertia.stop()
        self.pad.ungrab()
        self.v_pad.close()
        self.v_scroll.close()

    # ------------------------------------------
    # 内部メソッド
    # ------------------------------------------
    def _update_position(self, event):
        """タッチ座標を更新する"""
        if event.type != ecodes.EV_ABS:
            return
        if event.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
            self.current_x = event.value
        elif event.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
            self.current_y = event.value

    def _process_frame(self):
        """SYN_REPORT ごとに1フレーム分の処理を行う"""
        self._detect_touch_change()
        self._detect_finger_count()

        if self.scroll_mode and self.is_touching:
            self._handle_scroll()
        elif not self.scroll_mode:
            self._forward_events()

    def _detect_touch_change(self):
        """タッチの開始/終了を検出し、スクロールモードを決定する"""
        cx = self.cfg_wp["center_x"]
        cy = self.cfg_wp["center_y"]

        for e in self.buffer:
            if e.type == ecodes.EV_KEY and e.code == ecodes.BTN_TOUCH:
                self.is_touching = (e.value == 1)

                if self.is_touching:
                    # 新しいタッチが始まったら慣性をキャンセル
                    self.inertia.stop()

                    dist = math.hypot(self.current_x - cx, self.current_y - cy)
                    if dist > self.cfg_wp["deadzone"]:
                        self.scroll_mode = True
                        self.last_angle = math.atan2(
                            self.current_y - cy, self.current_x - cx
                        )
                        self.last_time = time.monotonic()
                        self.last_angular_velocity = 0.0
                        log.debug("スクロールモード開始")
                    else:
                        self.scroll_mode = False
                else:
                    # タッチ終了
                    if self.scroll_mode:
                        # 慣性スクロールを発動
                        self.inertia.trigger(
                            angular_velocity=self.last_angular_velocity,
                            direction=self.last_direction,
                            horizontal=self.last_horizontal,
                            hires_step=self.cfg_wp["hires_step"],
                        )
                        self.scroll_mode = False
                        self.last_angle = None
                        self.last_time = None
                        self.buffer.clear()
                        return
                    self.scroll_mode = False

    def _detect_finger_count(self):
        """同時タッチ数を検出する (水平スクロール判定用)"""
        for e in self.buffer:
            if e.type == ecodes.EV_KEY:
                if e.code == ecodes.BTN_TOOL_FINGER:
                    self.finger_count = 1 if e.value else 0
                elif e.code == ecodes.BTN_TOOL_DOUBLETAP:
                    self.finger_count = 2 if e.value else self.finger_count

    def _handle_scroll(self):
        """回転角度からスクロールイベントを生成する"""
        cx = self.cfg_wp["center_x"]
        cy = self.cfg_wp["center_y"]
        current_angle = math.atan2(self.current_y - cy, self.current_x - cx)
        now = time.monotonic()

        if self.last_angle is None:
            self.last_angle = current_angle
            self.last_time = now
            return

        angle_diff = normalize_angle(current_angle - self.last_angle)

        if abs(angle_diff) < self.cfg_wp["sensitivity"]:
            return

        # 角速度 (rad/s) を計算
        dt = now - self.last_time
        angular_velocity = abs(angle_diff) / dt if dt > 0 else 0
        multiplier = calc_speed_multiplier(angular_velocity, self.cfg_speed["thresholds"])

        # スクロール方向
        raw_direction = -1 if angle_diff > 0 else 1
        direction = raw_direction * self._scroll_sign
        hires_value = direction * self.cfg_wp["hires_step"] * multiplier
        horizontal = self.finger_count >= 2

        # 慣性用に最後の状態を記憶
        self.last_direction = direction
        self.last_horizontal = horizontal
        self.last_angular_velocity = angular_velocity

        if horizontal:
            self.v_scroll.write(ecodes.EV_REL, ecodes.REL_HWHEEL, direction * multiplier)
            self.v_scroll.write(ecodes.EV_REL, ecodes.REL_HWHEEL_HI_RES, hires_value)
            log.debug("水平: dir=%d mult=%d vel=%.2f", direction, multiplier, angular_velocity)
        else:
            self.v_scroll.write(ecodes.EV_REL, ecodes.REL_WHEEL, direction * multiplier)
            self.v_scroll.write(ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, hires_value)
            log.debug("垂直: dir=%d mult=%d vel=%.2f", direction, multiplier, angular_velocity)

        self.v_scroll.syn()
        self.last_angle = current_angle
        self.last_time = now

    def _forward_events(self):
        """スクロールモードでない場合は通常のタッチパッドイベントを転送する"""
        for e in self.buffer:
            self.v_pad.write(e.type, e.code, e.value)


# ==========================================
# エントリーポイント
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Let's Note Wheelpad Scroll Daemon")
    parser.add_argument(
        "--config", "-c",
        metavar="PATH",
        help="設定ファイルのパス (デフォルト: /etc/wheelpad/config.toml)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグログを有効にする",
    )
    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    cfg = load_config(args.config)

    device_path = find_touchpad(cfg["device"]["name"])
    if device_path is None:
        log.error("タッチパッドが見つかりません: %s", cfg["device"]["name"])
        sys.exit(1)

    daemon = WheelpadDaemon(device_path, cfg)
    daemon.run()


if __name__ == "__main__":
    main()