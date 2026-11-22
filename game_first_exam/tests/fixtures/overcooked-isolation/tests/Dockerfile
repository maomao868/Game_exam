FROM docker.io/library/python:3.10.12-slim-bookworm@sha256:4d440b214e447deddc0a94de23a3d97d28dfafdf125a8b4bb8073381510c9ee2
COPY --from=game-tests:overcooked /srv/grade.py /srv/reducers.py /srv/config_schema.py /srv/metric_rules.py /srv/instance_schema.py /srv/instance.json /tests/
COPY test.sh /tests/
RUN chmod +x /tests/test.sh
