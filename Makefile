ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON := $(ROOT)/.venv/bin/python
FROGS_ARGS ?=
BAR_IP ?=
BAR_TOKEN ?=

.PHONY: help frogs frogs-happy frogs-sad frogs-clear frogs-bake frogs-live flipper-export test test-assistant

help:
	@echo "frogs           install looping frogs (auto happy/sad by weekday)"
	@echo "frogs-happy     force happy frogs"
	@echo "frogs-sad       force sad frogs"
	@echo "frogs-clear     remove frogs from the bar"
	@echo "frogs-bake      bake .anim files only, no device"
	@echo "frogs-live      old host FPS loop (needs the Mac connected)"
	@echo "flipper-export  write Flipper SD files (needs BAR_IP and BAR_TOKEN)"
	@echo "test            run busybar pytest"
	@echo "test-assistant  run assistant pytest"
	@echo ""
	@echo "Extra flags: make frogs FROGS_ARGS='--address 10.0.4.20 --token x'"
	@echo "             make flipper-export BAR_IP=192.168.1.50 BAR_TOKEN=xxx"

frogs:
	$(PYTHON) -m busybar.wednesday_frogs.install $(FROGS_ARGS)

frogs-happy:
	$(PYTHON) -m busybar.wednesday_frogs.install --mode happy $(FROGS_ARGS)

frogs-sad:
	$(PYTHON) -m busybar.wednesday_frogs.install --mode sad $(FROGS_ARGS)

frogs-clear:
	$(PYTHON) -m busybar.wednesday_frogs.install --clear $(FROGS_ARGS)

frogs-bake:
	$(PYTHON) -m busybar.wednesday_frogs.install --bake-only $(FROGS_ARGS)

frogs-live:
	$(PYTHON) -m busybar.wednesday_frogs $(FROGS_ARGS)

flipper-export:
	@test -n "$(BAR_IP)" || (echo "BAR_IP is required, e.g. make flipper-export BAR_IP=192.168.1.50 BAR_TOKEN=xxx"; exit 1)
	@test -n "$(BAR_TOKEN)" || (echo "BAR_TOKEN is required, e.g. make flipper-export BAR_IP=192.168.1.50 BAR_TOKEN=xxx"; exit 1)
	$(PYTHON) -m busybar.wednesday_frogs.flipper_export --bar-ip "$(BAR_IP)" --token "$(BAR_TOKEN)"
	cp "$(ROOT)/flipper/busybar_remote/busybar_frogs.js" "$(ROOT)/flipper/busybar_remote/flipper_http.js" "$(ROOT)/flipper/out/"
	@echo "Copy flipper/out/* to SD:/apps/Scripts/"

test:
	$(PYTHON) -m pytest tests/ -q

test-assistant:
	cd $(ROOT)/services/assistant && $(PYTHON) -m pytest tests -q
