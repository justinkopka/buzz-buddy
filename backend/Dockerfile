FROM public.ecr.aws/lambda/python:3.13

# Match the uv version used locally, so the lock is read the same way.
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /bin/uv

# Install from uv.lock, not pyproject's loose ranges, so the image runs the
# exact versions tested locally. Dependencies come before app code so this layer
# stays cached until the lock changes. --locked fails the build if uv.lock is
# out of date with pyproject.toml, rather than building from a stale lock.
COPY pyproject.toml uv.lock ${LAMBDA_TASK_ROOT}/
RUN uv export --locked --no-dev --no-emit-project -o requirements.txt && \
    uv pip install -r requirements.txt --target ${LAMBDA_TASK_ROOT}

COPY app/ ${LAMBDA_TASK_ROOT}/app/

CMD ["app.main.handler"]
