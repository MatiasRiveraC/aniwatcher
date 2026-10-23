FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*

# The user the app runs as. It must be able to write the library and download
# folders, so match it to whoever owns them on the host (e.g. --build-arg PUID=1000).
ARG PUID=568
ARG PGID=568
RUN groupadd -g ${PGID} apps && useradd -u ${PUID} -g ${PGID} -s /bin/sh -m apps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data && chown -R ${PUID}:${PGID} /app /data

USER ${PUID}

EXPOSE 5000
CMD ["python", "app.py"]