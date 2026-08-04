"""pytest 用のパス設定 — backend/ を import ルートにする。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
