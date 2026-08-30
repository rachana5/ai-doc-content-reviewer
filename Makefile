.PHONY: test
test:
	cd plugins/doc-content-reviewer/skills/content-reviewer && \
	PYTHONPATH=. python3 -m pytest scripts/tests/ -v
