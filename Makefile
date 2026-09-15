ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON := $(ROOT)/.venv/bin/python
FROGS_ARGS ?=

.PHONY: help frogs frogs-happy frogs-sad frogs-clear frogs-bake frogs-live test

help:
	@echo "frogs         install looping frogs (auto happy/sad by weekday)"
	@echo "frogs-happy   force happy frogs"
	@echo "frogs-sad     force sad frogs"
	@echo "frogs-clear   remove frogs from the bar"
	@echo "frogs-bake    bake .anim files only, no device"
	@echo "frogs-live    old host FPS loop (needs the Mac connected)"
	@echo "test          run pytest"
	@echo ""
	@echo "Extra flags: make frogs FROGS_ARGS='--address 10.0.4.20 --token x'"

frogs:
	$(PYTHON) -m apps.wednesday_frogs.install $(FROGS_ARGS)

frogs-happy:
	$(PYTHON) -m apps.wednesday_frogs.install --mode happy $(FROGS_ARGS)

frogs-sad:
	$(PYTHON) -m apps.wednesday_frogs.install --mode sad $(FROGS_ARGS)

frogs-clear:
	$(PYTHON) -m apps.wednesday_frogs.install --clear $(FROGS_ARGS)

frogs-bake:
	$(PYTHON) -m apps.wednesday_frogs.install --bake-only $(FROGS_ARGS)

frogs-live:
	$(PYTHON) -m apps.wednesday_frogs $(FROGS_ARGS)

test:
	$(PYTHON) -m pytest tests/ -q
