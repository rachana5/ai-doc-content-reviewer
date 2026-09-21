.PHONY: test
test:
	@fail=0; \
	(cd plugins/doc-content-reviewer/skills/content-reviewer && PYTHONPATH=. python3 -m pytest scripts/tests/ -v) || fail=1; \
	(cd plugins/doc-content-reviewer/skills/review-doc-pr && PYTHONPATH=. python3 -m pytest scripts/tests/ -v) || fail=1; \
	exit $$fail
