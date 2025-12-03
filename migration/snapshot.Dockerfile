FROM alpine:3.22.2
LABEL maintainer="olivier.korach@gmail.com" 
ENV IN_DOCKER="Yes"

ARG USERNAME=sonar
ARG USER_UID=1000
ARG GROUPNAME=sonar

# Create the user
RUN addgroup -S ${GROUPNAME} && adduser -u ${USER_UID} -S ${USERNAME} -G ${GROUPNAME}

# Install python/pip
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python

# create a virtual environment and add it to PATH so that it is 
# applied for all future RUN and CMD calls
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /opt/sonar-migration

COPY ./sonar sonar
COPY ./migration/pyproject.toml .
COPY ./migration migration
COPY ./migration/README.md .
COPY ./LICENSE .
COPY ./cli cli

RUN pip install --upgrade pip \
&& pip install --no-cache-dir poetry \
&& poetry build \
&& pip install dist/sonar_migration-*-py3-*.whl --force-reinstall

USER ${USERNAME}
WORKDIR /home/${USERNAME}

HEALTHCHECK --interval=180s --timeout=5s CMD [ "sonar-migration", "-h" ]

ENTRYPOINT ["sonar-migration"]
