# backend/app/schemas

Pydantic models for request/response contracts.

Why these exist:
- They are the public API "source of truth" for shape and validation.
- They keep endpoint logic small (parse -> validate -> call service).

Tip: prefer updating schemas first when changing an API contract, then update handlers and tests.

