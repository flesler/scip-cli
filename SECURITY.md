# Security Policy

## Supported Versions

|Version|Supported|
|---|---|
|latest|:white_check_mark:|
|< latest|:x:|

## Reporting a Vulnerability

**Do not open public issues for security vulnerabilities.**

If you discover a security vulnerability, please email **aflesler@gmail.com** with:

- Description of the vulnerability
- Steps to reproduce or proof of concept
- Potential impact
- Suggested fix (if any)

## What to Expect

- Acknowledgment within 48 hours
- Assessment of the vulnerability's severity and impact
- Timeline for a fix and release
- Credit in the release notes (unless you prefer to remain anonymous)

## Scope

Security considerations for scip-cli include:

- **Index integrity**: SCIP indexes are read from local filesystem and trusted
- **SQL injection**: All queries use parameterized statements
- **Path traversal**: File operations are scoped to the indexed project
- **Dependency security**: Minimal dependencies; pinned versions in `pyproject.toml`

## Security Best Practices for Users

- Install from PyPI: `pip install scip-cli` (verified releases)
- Keep scip-cli updated to the latest version
- Review `.scip-cli.json` configuration before use in untrusted projects
- The `scip` binary is downloaded from [official releases](https://github.com/scip-code/scip/releases)

## Responsible Disclosure

We appreciate responsible disclosure and will work with you to understand and address the issue promptly.
