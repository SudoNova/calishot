FROM		alpine:latest
ARG			REPO=https://github.com/SudoNova/calishot
ARG			BRANCH=dev
RUN			cd /tmp && mkdir /data &&\
			apk update && apk upgrade &&\
			apk add git jq py3-gevent py3-numpy py3-pip &&\
			pip install bs4 datasette datasette-json-html datasette-mask-columns datasette-pretty-json \
			fire gevent sqlite_utils &&\
			git clone --depth 1 --single-branch --branch $BRANCH --no-tags $REPO &&\
			ln -s $(which python3) /usr/bin/python &&\
			mv calishot/*.db /data; mv calishot/*.json /data; mv calishot/calishot / &&\
			apk cache clean; pip cache purge; \
			rm -rf /root/.cache && rm -rf /var/cache/* &&  rm -rf /tmp/* && mkdir /var/cache/apk
WORKDIR		/calishot
#ONBUILD	python calishot.py scan-shodan && python calishot.py scrape-shodan
CMD			datasette serve --host 0.0.0.0 --port 80 /data/
EXPOSE		80
