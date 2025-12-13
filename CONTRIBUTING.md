# Contributing to Sensei API

Thank you for your interest in contributing to the Sensei League of Legends Coach project! We welcome contributions from the community.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a new branch for your work
5. Make your changes
6. Test your changes
7. Submit a pull request

## How to Contribute

### Types of Contributions

We welcome many types of contributions:

- Bug fixes
- New features
- Documentation improvements
- Code refactoring
- Performance improvements
- Test coverage improvements
- Champion data updates
- Translation improvements

### Good First Issues

Look for issues tagged with `good first issue` or `help wanted` if you're new to the project.

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (optional, recommended)
- Git

### Local Setup

1. Clone your fork:
```bash
git clone https://github.com/YOUR_USERNAME/LeagueAiCoach.git
cd LeagueAiCoach
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements-dev.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

5. Run tests to verify setup:
```bash
pytest
```

6. Start the development server:
```bash
uvicorn app.main:app --reload
```

### Docker Setup (Recommended)

```bash
docker-compose up -d --build
```

## Pull Request Process

1. **Create a branch**: Use a descriptive name
   ```bash
   git checkout -b feature/add-new-champion-data
   git checkout -b fix/audio-processing-bug
   ```

2. **Make your changes**: Follow our coding standards

3. **Write/update tests**: Ensure your changes are tested

4. **Run the test suite**:
   ```bash
   pytest
   ```

5. **Run code quality checks**:
   ```bash
   black app/ tests/
   flake8 app/ tests/
   mypy app/
   ```

6. **Commit your changes**: Use clear, descriptive commit messages
   ```bash
   git commit -m "Add support for new champion X"
   ```

7. **Push to your fork**:
   ```bash
   git push origin feature/add-new-champion-data
   ```

8. **Open a Pull Request**:
   - Provide a clear description of the changes
   - Reference any related issues
   - Ensure CI checks pass

### Pull Request Guidelines

- Keep PRs focused on a single concern
- Include tests for new functionality
- Update documentation as needed
- Follow the existing code style
- Ensure all tests pass
- Add a clear description of what and why

## Coding Standards

### Python Style

- Follow PEP 8 style guide
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use `black` for code formatting
- Use `flake8` for linting
- Use `mypy` for type checking

### Code Formatting

Before submitting, run:

```bash
# Format code
black app/ tests/

# Check linting
flake8 app/ tests/

# Type checking
mypy app/
```

### Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Keep comments clear and concise
- Update README.md if adding new features

### Commit Messages

- Use the imperative mood ("Add feature" not "Added feature")
- First line should be 50 characters or less
- Reference issues and pull requests when relevant
- Examples:
  ```
  Add support for Korean language in TTS
  Fix audio transcription timeout issue #123
  Update champion data for patch 14.1
  ```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_live_coach.py

# Run with coverage
pytest --cov=app tests/

# Run in Docker
docker-compose run --rm --build sensei-api test
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files with `test_` prefix
- Use descriptive test function names
- Include both positive and negative test cases
- Mock external API calls

## Reporting Bugs

### Before Submitting a Bug Report

- Check the issue tracker for existing reports
- Verify the bug exists in the latest version
- Collect relevant information (logs, error messages, steps to reproduce)

### How to Submit a Bug Report

Create an issue on GitHub with:

- **Clear title**: Brief description of the issue
- **Description**: Detailed explanation of the problem
- **Steps to reproduce**: Numbered list of steps
- **Expected behavior**: What should happen
- **Actual behavior**: What actually happens
- **Environment**: OS, Python version, dependency versions
- **Logs/Screenshots**: Any relevant error messages or screenshots

## Feature Requests

We welcome feature requests! To submit a feature request:

1. Check existing issues to avoid duplicates
2. Create a new issue with the `enhancement` label
3. Describe the feature and its use case
4. Explain why this feature would be useful
5. Be open to discussion and feedback

## Questions?

If you have questions about contributing:

- Open a GitHub Discussion
- Check existing documentation
- Review closed issues and PRs

## License

By contributing to this project, you agree that your contributions will be licensed under the Apache License 2.0.

---

Thank you for contributing to Sensei API!
