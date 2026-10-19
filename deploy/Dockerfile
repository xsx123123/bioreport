FROM python:3.12.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    HOME=/tmp/bioreport-home \
    QUARTO_PYTHON=/usr/local/bin/python \
    BROWSER_PATH=/usr/bin/chromium

# Chromium supports Kaleido static export; Noto supplies consistent CJK fonts.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates chromium curl fonts-noto-cjk fontconfig tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp/bioreport-home /workspace \
    && chmod 1777 /tmp/bioreport-home /workspace

# Pin the Quarto release and verify the downloaded package before installation.
RUN curl -fsSL -o /tmp/quarto.deb \
      https://github.com/quarto-dev/quarto-cli/releases/download/v1.8.26/quarto-1.8.26-linux-amd64.deb \
    && echo '60451a42095dd60bc23ad529b39ca81017da688aab029bec9b5565818fc55cf8  /tmp/quarto.deb' | sha256sum -c - \
    && apt-get install -y --no-install-recommends /tmp/quarto.deb \
    && rm -f /tmp/quarto.deb \
    && quarto --version

WORKDIR /app
COPY pyproject.toml README.md ./
COPY bioreport ./bioreport
COPY omics ./omics
COPY templates ./templates
COPY configs ./configs
COPY examples ./examples

# Install a distribution rather than relying on an editable source checkout.
RUN python -m pip install --no-cache-dir '.[security,validation]' \
    && python -m pip check \
    && python -m pip freeze > /opt/bioreport-python-packages.txt

COPY deploy/smoke_test.py /opt/bioreport-smoke-test.py
# Validate the installed package from outside the source checkout.
WORKDIR /tmp
RUN quarto check jupyter \
    && python /opt/bioreport-smoke-test.py --examples /app/examples

WORKDIR /workspace
ENTRYPOINT ["bioreport"]
CMD ["--help"]
