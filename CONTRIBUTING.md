# Contributing to scip-cli

Thank you for your interest in contributing to scip-cli! This document provides guidelines and information for contributors.

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues. When creating a bug report, include:

- Clear, descriptive title
- Steps to reproduce the issue
- Expected vs actual behavior
- Environment details (OS, Python version, scip-cli version)
- Minimal reproducible example if possible

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:

- Use a clear, descriptive title
- Provide a detailed description of the proposed enhancement
- Explain why this enhancement would be useful
- Include examples of how it would be used

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests: `pytest`
5. Run linter: `ruff check .` and `ruff format .`
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/your-username/scip-cli.git
cd scip-cli

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run linter
ruff check .
ruff format .
```

## Testing

- Run full test suite: `pytest`
- Run E2E tests: `pytest tests/test_e2e.py tests/test_e2e_analyze_patterns.py`
- Integration tests require Node.js and `npx` (for `scip-typescript`)

## Code Style

- Python 3.9+
- Line length: 120 characters
- Use type hints where practical
- Follow existing code patterns
- No unnecessary comments
- Use double quotes for strings

## Commit Messages

- Use clear, descriptive commit messages
- Start with a verb in imperative mood: "Add", "Fix", "Update", "Remove"
- Keep the first line under 72 characters
- Reference issues when applicable

## Documentation

- Update README.md for user-facing changes
- Update SKILL.md if CLI flags or commands change
- Add docstrings to new functions
- Keep comments minimal but meaningful

## Questions?

Open an issue or contact the maintainer.

Thank you for contributing!
