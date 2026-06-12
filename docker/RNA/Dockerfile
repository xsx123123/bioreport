# 1. 使用稳定版基础镜像 (Bookworm)
FROM python:3.12.12-slim-bookworm

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    PYTHONPATH=/app

# --- 关键修复：解决非 Root 用户运行时的权限问题 ---
# 创建一个所有用户可写的目录作为 HOME
RUN mkdir -p /tmp_home && chmod 777 /tmp_home
ENV HOME=/tmp_home

# 2. 安装系统依赖
# fonts-noto-cjk: 解决绘图和报告中的中文乱码
# gdebi-core: 用于安装 Quarto deb 包
# procps: 某些监控工具可能需要 ps 命令
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    gdebi-core \
    fonts-noto-cjk \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 3. 安装 Quarto
RUN wget https://github.com/quarto-dev/quarto-cli/releases/download/v1.8.26/quarto-1.8.26-linux-amd64.deb \
    && dpkg -i quarto-1.8.26-linux-amd64.deb \
    && rm quarto-1.8.26-linux-amd64.deb

# 验证安装
RUN quarto check install

# 4. 部署应用代码
# 建议保持在 /app 目录下，结构清晰
WORKDIR /app

# 先复制依赖与包配置，利用 Docker 缓存层
COPY requirements.txt pyproject.toml ./

# 使用清华源加速安装依赖
RUN pip install --no-cache-dir -i https://mirrors.ustc.edu.cn/pypi/simple \
    -r requirements.txt

# 安装 rnareport 包（editable 模式，方便调试）
COPY rnareport ./rnareport
RUN pip install --no-cache-dir -e .

# 复制 Quarto 模板、配置与入口脚本
COPY templates ./templates
COPY configs ./configs
COPY requirements.yaml ./requirements.yaml
COPY project_summary.json ./project_summary.json
COPY entrypoint.py ./entrypoint.py

RUN chmod -R 777 /app/templates /app/configs /tmp_home/

# 5. 启动命令
# 确保使用 list 格式 ["executable", "param"]
ENTRYPOINT ["python", "entrypoint.py"]
