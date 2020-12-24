FROM	alpine:latest
WORKDIR	/root
ENV		REPO=https://github.com/SudoNova/calishot	BRANCH=master
RUN		apk update && apk upgrade &&\
		apk add git jq py3-gevent py3-numpy py3-pip &&\
		pip install bs4 datasette datasette-json-html datasette-mask-columns datasette-pretty-json \
		fire gevent sqlite_utils &&\
		git clone --depth 1 --single-branch --branch $BRANCH --no-tags $REPO &&\
		ln -s $(which python3) /usr/bin/python
WORKDIR	/root/calishot/calishot
#ONBUILD	python calishot.py scan-shodan && python calishot.py scrape-shodan
