# Contributing

Open an issue describing the observed behavior, platform, Python and `hcloud`
versions, and sanitized reproduction. Keep feature proposals tied to a
repeatable Hetzner Cloud workflow.

Use Python 3.10 or later. Runtime dependencies should remain standard-library
only. Run:

```console
python -m unittest discover -s tests -v
python scripts/check_release.py
python -m build
```

Tests must not create paid resources or depend on credentials. Keep live
acceptance evidence distinct from mocked provider tests. Changes to packaged
knowledge must update the file hashes and release version as appropriate.

Follow the current CLI contract and retain explicit, reviewable mutation
boundaries. Do not add automatic write retries.
