.PHONY: build

SHELL := /bin/bash

PATH := ${GOPATH}/bin:$(PATH)
PYTHON := python3.5
ENV := env

build:
	virtualenv --quiet --python ${PYTHON} ${ENV}
	${ENV}/bin/pip install --upgrade --quiet pip wheel
	${ENV}/bin/pip install --quiet -r requirements.txt
	${ENV}/bin/python setup.py --quiet install
	pwd > ${ENV}/lib/${PYTHON}/site-packages/perfrunner.pth

clean:
	rm -fr build perfrunner.egg-info dist dcptest kvgen cbindexperf rachell *.db *.log
	find . -name '*.pyc' -o -name '*.pyo' -o -name __pycache__ | xargs rm -fr

pep8:
	${ENV}/bin/flake8 --statistics cbagent perfdaily perfrunner scripts spring
	${ENV}/bin/isort --quiet --check-only --recursive cbagent perfdaily perfrunner scripts spring

nose:
	${ENV}/bin/nosetests -v --with-coverage --cover-package=cbagent,perfrunner,spring unittests.py

misspell:
	go get -u github.com/client9/misspell/cmd/misspell
	misspell cbagent go perfdaily perfrunner scripts spring

gofmt:
	gofmt -e -d -s go && ! gofmt -l go | read

test: pep8 misspell gofmt nose

vendor-sync:
	go version
	go get -u github.com/kardianos/govendor
	govendor sync

dcptest: vendor-sync
	go build ./go/dcptest

buildquery: vendor-sync
	go get -u golang.org/x/tools/cmd/goyacc
	cd vendor/github.com/couchbase/query/parser/n1ql && sh build.sh

cbindexperf: buildquery
	go build ./go/cbindexperf

kvgen: vendor-sync
	go build ./go/kvgen

rachell:
	go build ./go/rachell

