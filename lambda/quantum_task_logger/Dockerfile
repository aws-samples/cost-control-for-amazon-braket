# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

FROM public.ecr.aws/lambda/python:3.12-arm64

COPY requirements.txt  .
RUN  pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY index.py ${LAMBDA_TASK_ROOT}
COPY models.py ${LAMBDA_TASK_ROOT}

CMD [ "index.handler" ]