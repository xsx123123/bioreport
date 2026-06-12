#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RNAFlow 报告生成器容器入口。

这是一个薄包装脚本，负责确保 /app 在 Python 路径中，然后调用
rnareport.cli.main() 执行完整流程。
"""

import os
import sys

# 确保容器内 /app 在 Python 路径中，使 rnareport 包可被导入
APP_ROOT = "/app"
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

# 设置 PYTHONPATH，使 Quarto 渲染时的 qmd Python 单元格也能找到 rnareport
os.environ.setdefault("PYTHONPATH", APP_ROOT)

from rnareport.cli import main

if __name__ == "__main__":
    main()
