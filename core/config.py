import os

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
SECRET_KEY = os.getenv('SECRET_KEY', 'face-attendance-secret-key')
ACCESS_TOKEN_EXPIRE_SECONDS = int(os.getenv('ACCESS_TOKEN_EXPIRE_SECONDS', '3600'))

# Liveness gate tuning:
# - HARD reject: spoof_score >= SPOOF_REJECT_THRESHOLD
# - SUSPECT reject: is_real=False AND spoof_score >= SPOOF_SUSPECT_THRESHOLD
SPOOF_REJECT_THRESHOLD = float(os.getenv('SPOOF_REJECT_THRESHOLD', '0.78'))
SPOOF_SUSPECT_THRESHOLD = float(os.getenv('SPOOF_SUSPECT_THRESHOLD', '0.62'))

# Adaptive leniency when the face occupies a large portion of frame (user stands close
# to camera). This reduces false spoof rejects caused by extreme close-up framing.
SPOOF_ADAPTIVE_AREA_START_RATIO = float(os.getenv('SPOOF_ADAPTIVE_AREA_START_RATIO', '0.18'))
SPOOF_ADAPTIVE_MAX_BONUS = float(os.getenv('SPOOF_ADAPTIVE_MAX_BONUS', '0.16'))

# Realtime WS tuning (CPU-friendly defaults)
REALTIME_WS_DETECT_INTERVAL_MS = int(os.getenv('REALTIME_WS_DETECT_INTERVAL_MS', '450'))
REALTIME_WS_TRACK_TTL_MS = int(os.getenv('REALTIME_WS_TRACK_TTL_MS', '900'))
REALTIME_WS_RECOGNIZE_COOLDOWN_MS = int(os.getenv('REALTIME_WS_RECOGNIZE_COOLDOWN_MS', '650'))
