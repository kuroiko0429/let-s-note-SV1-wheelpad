import math
import time
import sys
from evdev import InputDevice, UInput, ecodes, list_devices

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
CENTER_X = 264  
CENTER_Y = 264  
SENSITIVITY = 0.3
DEADZONE = 195

DEBUG_MODE = False # 常駐させる時はFalseにしてログを止める

# ==========================================
# 🔍 タッチパッドを自動で探し出す関数
# ==========================================
def find_touchpad():
    for path in list_devices():
        device = InputDevice(path)
        # evtestで確認したデバイス名の一部を指定
        if "Synaptics TM3562-003" in device.name:
            return path
    return None

DEVICE_PATH = find_touchpad()
if DEVICE_PATH is None:
    print("[ERROR] タッチパッドが見つかりません！")
    sys.exit(1)

# ==========================================
# 🚀 INITIALIZATION
# ==========================================
pad = InputDevice(DEVICE_PATH)
pad.grab()

v_pad = UInput.from_device(pad, name="LetsNote-Virtual-Pad")
v_mouse = UInput({ecodes.EV_REL: [ecodes.REL_WHEEL]}, name="LetsNote-Virtual-Wheel")

if DEBUG_MODE:
    print(f"[{time.time():.4f}] [INFO] Daemon started on {pad.name} ({DEVICE_PATH})")

buffer = []
is_touching = False
scroll_mode = False
last_angle = None
current_x = CENTER_X
current_y = CENTER_Y

try:
    for event in pad.read_loop():
        buffer.append(event)

        if event.type == ecodes.EV_ABS:
            if event.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                current_x = event.value
            elif event.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                current_y = event.value

        if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
            touch_changed = False
            
            for e in buffer:
                if e.type == ecodes.EV_KEY and e.code == ecodes.BTN_TOUCH:
                    is_touching = (e.value == 1)
                    touch_changed = True

            if touch_changed:
                if is_touching:
                    dist = math.sqrt((current_x - CENTER_X)**2 + (current_y - CENTER_Y)**2)
                    if dist > DEADZONE:
                        scroll_mode = True
                        last_angle = math.atan2(current_y - CENTER_Y, current_x - CENTER_X)
                    else:
                        scroll_mode = False
                else:
                    if scroll_mode:
                        scroll_mode = False
                        buffer = []
                        continue
                    else:
                        scroll_mode = False

            if scroll_mode:
                if is_touching:
                    current_angle = math.atan2(current_y - CENTER_Y, current_x - CENTER_X)
                    
                    if last_angle is not None:
                        angle_diff = current_angle - last_angle
                        
                        if angle_diff > math.pi: angle_diff -= 2 * math.pi
                        elif angle_diff < -math.pi: angle_diff += 2 * math.pi
                        
                        if abs(angle_diff) > SENSITIVITY:
                            direction = -1 if angle_diff > 0 else 1
                            v_mouse.write(ecodes.EV_REL, ecodes.REL_WHEEL, direction)
                            v_mouse.syn()
                            last_angle = current_angle
            else:
                for e in buffer:
                    v_pad.write(e.type, e.code, e.value)

            buffer = []

except KeyboardInterrupt:
    pad.ungrab()
    v_pad.close()
    v_mouse.close()