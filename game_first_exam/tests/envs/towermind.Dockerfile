FROM --platform=linux/amd64 docker.io/library/python:3.10.12-slim-bookworm@sha256:4d440b214e447deddc0a94de23a3d97d28dfafdf125a8b4bb8073381510c9ee2 AS base
ENV PYTHONUNBUFFERED=1

FROM base AS client
WORKDIR /app
COPY game_first_exam/runtime/game_client.py shared/connection/service_connection.py /app/
COPY game_first_exam/tests/towermind_probe.py /app/
USER 65534:65534
CMD ["python", "/app/towermind_probe.py"]

FROM base AS sim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libasound2 libgl1 libgl1-mesa-dri libglx-mesa0 libglib2.0-0 \
    libx11-6 libxcursor1 libxext6 libxfixes3 libxi6 libxinerama1 libxrandr2 \
    libxrender1 libvulkan1 mesa-vulkan-drivers xauth xvfb \
    && rm -rf /var/lib/apt/lists/*
ENV LIBGL_ALWAYS_SOFTWARE=1 HOME=/tmp
WORKDIR /repo
COPY game_first_exam/benchmarks/towermind/ /repo/game_first_exam/benchmarks/towermind/
RUN pip install --no-cache-dir --no-deps setuptools==84.2.1 wheel==0.45.1 \
    && pip install --no-cache-dir --no-deps --no-build-isolation -r game_first_exam/benchmarks/towermind/requirements.txt \
    && pip check \
    && python game_first_exam/benchmarks/towermind/native_assets.py /opt/towermind
COPY game_first_exam/runtime/ /repo/game_first_exam/runtime/
COPY game_first_exam/tests/towermind_fixture.py game_first_exam/tests/test_towermind_contract.py \
    game_first_exam/tests/test_towermind_native.py /repo/game_first_exam/tests/
USER 65534:65534
CMD ["xvfb-run", "-a", "-s", "-screen 0 1400x900x24", "python", "game_first_exam/tests/towermind_fixture.py"]

FROM sim AS windows-probe
USER root
RUN apt-get update && apt-get install -y --no-install-recommends wine64 \
    && rm -rf /var/lib/apt/lists/*
ADD --chmod=0444 --checksum=sha256:1828afe2608a154e1107e42aa3f49dad85dd34bf9d98e1adc0c802100c37521b \
    https://raw.githubusercontent.com/tb6147877/TowerMind/7ac5d5cb815ce022cdf6f6d40fa0a9fcc9be3e71/compressed_env/windows.zip \
    /opt/towermind/windows.zip
USER 65534:65534

FROM sim AS default
