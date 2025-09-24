# https://developers.home-assistant.io/docs/add-ons/configuration#add-on-dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

# Execute during the build of the image
ARG TEMPIO_VERSION BUILD_ARCH
RUN \
    curl -sSLf -o /usr/bin/tempio \
    "https://github.com/home-assistant/tempio/releases/download/${TEMPIO_VERSION}/tempio_${BUILD_ARCH}"

# Copy root filesystem
COPY rootfs /
RUN apk add --no-cache ca-certificates && \
    update-ca-certificates

RUN apk update && \
    apk add --no-cache nginx python3 py3-pip
    
RUN apk add py3-requests py3-flask

# Install Python packages 
RUN apk add --no-cache \
    py3-setuptools \
    py3-wheel \
    py3-websocket-client

# Install Flask-Sock for WebSocket support
# °²×° Flask£¨ºó¶Ë£©
RUN pip3 install --no-cache-dir flask-sock
