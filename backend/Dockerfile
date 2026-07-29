FROM public.ecr.aws/lambda/python:3.13

COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY app/ ${LAMBDA_TASK_ROOT}/app/

RUN pip install .

CMD ["app.main.handler"]
