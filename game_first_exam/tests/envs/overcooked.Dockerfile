FROM docker.io/library/python:3.10.12-slim-bookworm@sha256:4d440b214e447deddc0a94de23a3d97d28dfafdf125a8b4bb8073381510c9ee2 AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

FROM base AS client
WORKDIR /app
COPY shared/connection/service_connection.py game_first_exam/runtime/game_client.py game_first_exam/tests/overcooked_probe.py ./
USER 65534:65534
CMD ["python", "overcooked_probe.py"]

FROM base AS sim
ENV SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy PYGAME_HIDE_SUPPORT_PROMPT=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY game_first_exam/benchmarks/overcooked/requirements.txt /requirements.txt
RUN pip install --no-cache-dir setuptools==84.2.1 wheel==0.45.1 \
    && pip install --no-cache-dir --no-build-isolation -r /requirements.txt && pip check
COPY game_first_exam/runtime/ /srv/
COPY game_first_exam/benchmarks/overcooked/*.py /srv/
COPY game_first_exam/tests/fixtures/overcooked-instance.json /srv/instance.json
# The upstream planner caches layout-specific files. Only the simulator owns this cache.
RUN planner_dir="$(python -c 'from overcooked_ai_py.static import PLANNERS_DIR; print(PLANNERS_DIR)' | tail -n 1)" \
    && chown 65534:65534 "$planner_dir" && mkdir /data && chown 65534:65534 /data
WORKDIR /repo
USER 65534:65534
CMD ["python", "/srv/server.py"]
