FROM		alpine:latest
ARG			REPO=https://github.com/SudoNova/calishot
ARG			BRANCH=dev
RUN			cd /root &&\
			apk update && apk upgrade &&\
			apk add git jq py3-gevent py3-numpy py3-pip &&\
			pip install bs4 datasette datasette-json-html datasette-mask-columns datasette-pretty-json \
			fire gevent sqlite_utils &&\
			git clone --depth 1 --single-branch --branch $BRANCH --no-tags $REPO &&\
			ln -s $(which python3) /usr/bin/python &&\
			apk cache clean; pip cache purge; rm -rf /root/.cache; rm -rf /var/cache/*
WORKDIR		/root/calishot/calishot
#ONBUILD	python calishot.py scan-shodan && python calishot.py scrape-shodan
ENTRYPOINT	datasette
CMD			serve index.db --config sql_time_limit_ms:10000 --config allow_download:off \
			--config max_returned_rows:2000  --config num_sql_threads:10 --metadata metadata.json
EXPOSE		8001
