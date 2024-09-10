#FROM alpine:latest
FROM python:3.9
LABEL maintainer="olivier.korach@gmail.com" 
WORKDIR /opt/sonar-tools
# create a virtual environment and add it to PATH so that it is 
# applied for all future RUN and CMD calls
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv ${VIRTUAL_ENV}
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install python/pip
ENV PYTHONUNBUFFERED=1
COPY ./sonar sonar
COPY ./requirements.txt .
COPY ./cli cli
COPY ./setup.py .
COPY ./sonar-tools .
COPY ./README.md .
COPY ./LICENSE .
COPY ./sonar/audit sonar/audit

RUN pip install --upgrade pip \
&& pip install --no-cache-dir -r requirements.txt \
&& pip install --no-cache-dir --upgrade pip setuptools wheel \
&& python setup.py bdist_wheel \
&& pip install dist/*-py3-*.whl --force-reinstall

CMD [ "sonar-tools" ]
