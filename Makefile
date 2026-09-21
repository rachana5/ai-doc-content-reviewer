SKILLS := content-reviewer review-doc-pr

.PHONY: test
test:
	@fail=0; \
	for skill in $(SKILLS); do \
		(cd plugins/doc-content-reviewer/skills/$$skill && PYTHONPATH=. python3 -m pytest scripts/tests/ -v) || fail=1; \
	done; \
	exit $$fail
