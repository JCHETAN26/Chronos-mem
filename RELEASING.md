# Releasing chronos-mem to PyPI

The Python package lives in `sdk/python/`. Publishing is a **manual, maintainer
step** — it needs a PyPI account and API token that CI/agents don't hold.

## Prerequisites (one time)

1. A PyPI account: https://pypi.org/account/register/
2. An API token: PyPI → Account settings → API tokens → *Add API token*
   (scope it to the `chronos-mem` project after the first upload; use an
   account-wide token for the very first one).
3. Tooling: `pip install build twine` (or use `uv` as shown below).

## Build

```bash
cd sdk/python
rm -rf dist
uv build            # or:  python -m build
```

Produces:

```
dist/chronos_mem-<version>-py3-none-any.whl
dist/chronos_mem-<version>.tar.gz
```

## Validate before uploading

```bash
twine check dist/*
```

Both artifacts must report `PASSED`.

## Publish

Authenticate with the token (username is literally `__token__`):

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX...      # your API token

# (Recommended) dry run against TestPyPI first:
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ chronos-mem   # verify

# Real release:
twine upload dist/*
```

Then `pip install chronos-mem` resolves globally.

## Cutting a new version

1. Bump `version` in `sdk/python/pyproject.toml` (PyPI rejects re-uploading an
   existing version).
2. Update `CHANGELOG` / release notes.
3. Rebuild, `twine check`, upload (above).
4. Tag the release: `git tag v<version> && git push --tags`.

## Notes

- The package metadata (Apache-2.0 license, classifiers, project URLs) is in
  `sdk/python/pyproject.toml`; the long description is `sdk/python/README.md`.
- The CI workflow (`.github/workflows/ci.yml`) gates correctness + performance
  but does **not** publish — release stays a deliberate human action.
