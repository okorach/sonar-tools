#FROM alpine:latest
FROM python:3.9
LABEL maintainer="olivier.korach@gmail.com" 

ARG USERNAME=sonar
ARG USER_UID=1000
ARG USER_GID=$USER_UID



WORKDIR /opt/sonar-tools
# create a virtual environment and add it to PATH so that it is 
# applied for all future RUN and CMD calls
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv ${VIRTUAL_ENV}
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Create the user
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m ${USERNAME} 

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

USER ${USERNAME}

CMD [ "sonar-tools" ]
