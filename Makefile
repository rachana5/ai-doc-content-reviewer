SKILLS := content-reviewer review-doc-pr review-doc-pr-proxy

.PHONY: test help

help:
	@echo "make test - run unit tests for every skill"

test:
	@fail=0; \
	for skill in $(SKILLS); do \
		(cd plugins/doc-content-reviewer/skills/$$skill && PYTHONPATH=. python3 -m pytest scripts/tests/ -v) || fail=1; \
	done; \
	exit $$fail
