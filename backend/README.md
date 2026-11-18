# Backend

FastAPI on Python 3.12, async SQLAlchemy 2.0, Pydantic v2 and Alembic. Tooling: uv, Ruff,
mypy (strict) and pytest. How to run it and the API it serves are in the top-level
[`README.md`](../README.md); the design choices are in
[`ARCHITECTURE.md`](../ARCHITECTURE.md).

## Layout

```
backend/
├── app/
│   ├── main.py            # application factory and middleware order
│   ├── api/v1/routers/    # auth, content (with images and export), improve, brand_voices, health, meta
│   ├── core/              # settings, security, logging, exceptions, the dated model catalog
│   ├── db/                # engine and session, models, enums
│   ├── repositories/      # queries, one module per table
│   ├── services/          # business logic, renderers, image storage
│   ├── providers/         # ILLMProvider and IImageProvider: OpenAI and mock implementations, and Bedrock stubs that raise
│   ├── prompts/           # one module per content type, plus the improver and the image prompt
│   ├── schemas/           # request and response models
│   ├── middleware/        # request id, CSRF origin check, rate limit, security headers, access log, 500s
│   └── scripts/           # seed data, and the weekly model-lifecycle check
├── alembic/               # migrations
├── tests/                 # unit tests, integration tests against Postgres, golden prompts
├── Dockerfile
└── pyproject.toml
```

## Tests

```bash
uv sync --frozen
uv run alembic upgrade head
REQUIRE_DB=1 uv run pytest --cov=app --cov-fail-under=80
```

The integration tests need Postgres at `DATABASE_URL`. Without it they are skipped, unless
`REQUIRE_DB=1` is set, as it is in CI, in which case they fail.
