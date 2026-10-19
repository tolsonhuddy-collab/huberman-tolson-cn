.PHONY: test status check-sources demo private-site audit
test:
	python3 -m unittest discover -s tests -v
status:
	python3 scripts/pipeline.py status
check-sources:
	python3 scripts/pipeline.py check-sources
demo:
	python3 scripts/build_site.py --demo --out dist
private-site:
	python3 scripts/build_site.py --private --out private/site
audit:
	python3 scripts/pipeline.py audit-git
