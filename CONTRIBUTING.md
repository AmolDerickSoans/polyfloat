# Contributing to PolyCLI

We welcome contributions! Please follow these guidelines to ensure a smooth process.

## Development Setup

1.  **Fork** the repository.
2.  **Clone** your fork:
    ```bash
    git clone https://github.com/YOUR_USERNAME/polyfloat.git
    cd polyfloat
    ```
3.  **Install dependencies** (we support pip/poetry):
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .[dev]
    ```

## Code Standards

-   **Linting**: We use `ruff` and `black`. Run `ruff check .` and `black .` before committing.
-   **Testing**: Run `pytest` to ensure all tests pass.
-   **Type Hinting**: All new code must be type-hinted.

## Pull Request Process

1.  Create a branch for your feature: `git checkout -b feature/amazing-feature`
2.  Commit your changes.
3.  Push to your fork and submit a Pull Request.
