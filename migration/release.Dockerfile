FROM alpine:3.21.2
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
COPY ./requirements.txt .
COPY ./cli cli
COPY ./setup_migration.py .
COPY ./migration migration
COPY ./migration/README.md .
COPY ./LICENSE .
COPY ./sonar/audit sonar/audit

RUN pip install --upgrade pip \
&& pip install sonar-migration==0.4 --force-reinstall

USER ${USERNAME}
WORKDIR /home/${USERNAME}

HEALTHCHECK --interval=180s --timeout=5s CMD [ "sonar-migration", "-h" ]

ENTRYPOINT ["sonar-migration"]
