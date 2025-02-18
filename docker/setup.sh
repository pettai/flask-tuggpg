#!/bin/bash

set -e
set -x

export DEBIAN_FRONTEND noninteractive

apt-get update && \
    apt-get -y dist-upgrade && \
    apt-get install -y \
      libpython3-dev \
      python3-venv \
      iputils-ping \
      procps \
      bind9-host \
      netcat-openbsd \
      net-tools \
      curl \
      gnupg2 \
      git \
    && apt-get clean

rm -rf /var/lib/apt/lists/*

python3 -m venv /opt/flask-tuggpg/env
/opt/flask-tuggpg/env/bin/pip install -U pip
/opt/flask-tuggpg/env/bin/pip install --no-cache-dir -r /opt/flask-tuggpg/requirements.txt
/opt/flask-tuggpg/env/bin/pip freeze

addgroup --system tuggpg

adduser --system --shell /bin/false tuggpg
