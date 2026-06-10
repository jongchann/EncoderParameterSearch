# Encoder Parameter Search

## Python environment

Use the project virtual environment only. Do not install or run backend dependencies with the system Python.

Set up the environment:

```sh
./scripts/bootstrap_venv.sh
```

Run tests:

```sh
./scripts/test.sh
```

Start the backend server:

```sh
./scripts/run_server.sh
```

The server exposes:

```text
GET /health
```

The current Step 1 server uses only the Python standard library so it can start
inside `.venv` before third-party dependencies are installed. FastAPI remains
declared in `pyproject.toml` for the API implementation steps that follow.
