FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 568 apps && useradd -u 568 -g 568 -s /bin/sh -m apps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data && chown -R 568:568 /app /data

USER 568

EXPOSE 5000
CMD ["python", "app.py"]