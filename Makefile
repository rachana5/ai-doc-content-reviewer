.PHONY: test
test:
	cd plugins/doc-content-reviewer/skills/content-reviewer && \
	PYTHONPATH=. python3 -m pytest scripts/tests/ -v
	cd plugins/doc-content-reviewer/skills/review-doc-pr && \
	PYTHONPATH=. python3 -m pytest scripts/tests/ -v
