FROM python:3.9.1

ENV prometheus_multiproc_dir /var/tmp/prometheus_multiproc_dir
RUN mkdir $prometheus_multiproc_dir \
    && chown www-data $prometheus_multiproc_dir \
    && chmod g+w $prometheus_multiproc_dir

WORKDIR /srv/service
ADD requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt install wget && \
    wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.16.0/kubeseal-linux-amd64 -O kubeseal && \
    install -m 755 kubeseal /usr/local/bin/kubeseal

ADD . .

USER www-data

CMD ["gunicorn", "--bind=0.0.0.0:8080", "--config", "gunicorn.conf.py", "--workers=3", "-k", "uvicorn.workers.UvicornWorker", "--log-level=INFO", "workspace_api:app"]
