SKILLS := content-reviewer review-doc-pr
HUB_DOC_ROOT ?=

.PHONY: test sync-check help

help:
	@echo "make test                          - run unit tests for every skill and tools/"
	@echo "make sync-check HUB_DOC_ROOT=<path> - check hub-doc's copy of review-doc-pr matches this repo"

test:
	@fail=0; \
	for skill in $(SKILLS); do \
		(cd plugins/doc-content-reviewer/skills/$$skill && PYTHONPATH=. python3 -m pytest scripts/tests/ -v) || fail=1; \
	done; \
	python3 -m pytest tools/tests/ -v || fail=1; \
	exit $$fail

sync-check:
	@if [ -z "$(HUB_DOC_ROOT)" ]; then \
		echo "usage: make sync-check HUB_DOC_ROOT=<path to local traefik/hub-doc clone>"; \
		exit 2; \
	fi
	@python3 tools/check_review_doc_pr_sync.py --hub-doc-root $(HUB_DOC_ROOT)
