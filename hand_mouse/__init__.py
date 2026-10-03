import os

# mediapipe(glog/TFLite) 경고 로그 억제 — mediapipe import 전에 설정돼야 함
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
