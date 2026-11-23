# syntax=docker/dockerfile:1.7
FROM python:3.10-slim-bookworm AS base
WORKDIR /bench/src
ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/bench/src:/bench/lib:/integration
COPY --from=upstream /LICENSE /licenses/Collab-Overcooked
COPY --from=upstream /lib/overcooked_ai/LICENSE /licenses/Overcooked-AI

FROM base AS dependencies
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

FROM dependencies AS role
COPY --from=upstream /src/collab/modules.py /src/collab/utils.py /src/collab/web_util.py ./collab/
COPY --from=upstream /lib/overcooked_ai/overcooked_ai_py/mdp/actions.py /bench/lib/overcooked_ai_py/mdp/actions.py
COPY --from=upstream /lib/llama_tokenizer /bench/lib/llama_tokenizer
ENV TIKTOKEN_CACHE_DIR=/opt/tokens
RUN python -c "import tiktoken; tiktoken.encoding_for_model('gpt-4')"
COPY role.py wire.py /integration/
RUN touch openai_key.txt
USER 65534:65534
CMD ["python","/integration/role.py"]

FROM role AS probe
COPY fixture_policy.py /integration/

FROM dependencies AS engine
COPY --from=upstream /lib/overcooked_ai/overcooked_ai_py /bench/lib/overcooked_ai_py
COPY --from=upstream /lib/overcooked_ai/setup.py /bench/lib/setup.py
RUN pip install --no-deps -e ../lib

FROM engine AS sim
COPY --from=upstream /src/collab ./collab
COPY --from=upstream /src/main.py /src/utils.py ./
COPY --from=upstream /src/prompts/gpt ./prompts/gpt
COPY --from=upstream /src/prompts/recipe ./prompts/recipe
COPY adapter.py wire.py /integration/
RUN touch openai_key.txt && mkdir -p /channels/Chef /channels/Assistant /status /evidence && chown -R 65534:65534 /channels /status /evidence /bench/lib/overcooked_ai_py/data/planners && chmod 777 /channels/* /status
USER 65534:65534
CMD ["python","/integration/adapter.py"]

FROM engine AS grader
COPY --from=upstream /src/eval_utils.py /src/time_step.py ./
COPY --from=upstream /src/prompts/reference ./prompts/reference
COPY grade.py /integration/
