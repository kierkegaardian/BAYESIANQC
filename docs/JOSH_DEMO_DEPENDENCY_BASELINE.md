# Josh demo dependency security baseline

Recorded on 2026-07-09 for the disposable stakeholder demo release.

The versions named in the original implementation plan were re-evaluated at
release time because that same plan prohibits deployment with a known high or
critical advisory. The requested `starlette==0.49.3` now has six known
vulnerability records in the Python Packaging Advisory Database:

- `PYSEC-2026-161` (reported twice by the current audit data);
- `PYSEC-2026-249`;
- `PYSEC-2026-248`;
- `CVE-2026-48818`;
- `CVE-2026-48817`.

The first Starlette release clearing every reported issue is `1.3.1`.
`fastapi==0.120.4` requires Starlette `<0.50.0`, so it cannot be combined with
that safe release. `fastapi==0.139.0` supports Starlette `1.3.1` but requires
Pydantic `>=2.9.0`, so preserving `pydantic==2.8.2` is also impossible after
the security upgrade. The release therefore pins:

- `fastapi==0.139.0`;
- `starlette==1.3.1`;
- `pydantic==2.13.4`;
- `python-multipart==0.0.32`.

The requested `pytest==8.2.2` also now reports `PYSEC-2026-1845`; the test
toolchain uses `pytest==9.0.3`, its published fix version.

Evidence commands:

```bash
python -m pip_audit -r requirements.txt
python -m pip_audit -r <requested-pin-requirements-file>
python -m pip install --dry-run --ignore-installed \
  fastapi==0.120.4 starlette==1.3.1 pydantic==2.8.2
```

The release requirements audit must finish with `No known vulnerabilities
found`. This note documents a security-gate override of the superseded pins;
it is not permission to float dependency versions in later releases.

## Frontend build-tool baseline

The originally requested `vitest==2.1.9` and its Vite 5 dependency now fall in
critical/high advisory ranges. The release therefore uses `vitest==4.1.10`,
`vite==8.1.4`, and `@vitejs/plugin-vue==6.0.7`. Patched compatible transitive
versions are locked with npm overrides for `fast-uri`, `minimatch`, and
`brace-expansion`. CI and the web-image builder audit the complete dependency
tree at high severity in addition to auditing the runtime tree.

The current registry also reports `js-yaml==4.1.1` for
`GHSA-h67p-54hq-rp68`; the lockfile overrides that schema-generation
dependency to the published patched `4.3.0` release. The complete npm audit is
therefore clean and no advisory waiver is required. Any future high or
critical advisory remains a release blocker; a future moderate requires a
written reachability analysis and explicit waiver.

Frontend evidence commands use the same Node 22 image as the web build:

```bash
npm ci --include=dev
npm audit --omit=dev --audit-level=high
npm audit --audit-level=high
npm test
npm run typecheck
npm run build
```
