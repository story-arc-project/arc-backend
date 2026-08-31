# AI Analyzer Module Specification

Implement and maintain the AI analyzer modules under `src/ai/`.

This document specifies the **module interface, response contract, environment configuration, and typing requirements**. It does not prescribe the internal AI/LLM implementation.

---

## 1. Module Location

All AI analyzer modules and their related modules must live under `src/ai/`

Do not move analyzer files outside this directory unless explicitly requested.

---

## 2. Public Entrypoint

Each analyzer module must expose a clearly defined public:

```python
main(...)
```

function.

`main(...)` is the primary public entrypoint of the analyzer.

Keep the public API minimal.

---

## 3. Importable Modules

Each analyzer must be usable as a normal Python module.

For example:

```python
from src.ai.some_analyzer import main
```

Importing the module must not require runtime secrets or credentials to be available.

Do not initialize AI/API clients or perform other runtime setup that requires credentials at module import time.

Any execution must occur only through an explicit function call such as:

```python
result = main(...)
```

If a CLI entrypoint is provided, it must be protected by:

```python
if __name__ == "__main__":
    ...
```

---

# 4. Response Models

Use the existing response models from:

```text
src/ai/models.py
```

The response models are:

* `SuccessResponse`
* `VectorSuccessResponse`
* `ErrorResponse`

Do not create duplicate response-envelope models.

The response structures are:

### `SuccessResponse`

```python
class SuccessResponse(BaseModel):
    status: Literal["success"] = "success"
    result: dict
```

`result` must always be a plain dictionary containing JSON-serializable data.

It must not be a Pydantic model.

---

### `VectorSuccessResponse`

```python
class VectorSuccessResponse(BaseModel):
    status: Literal["success"] = "success"
    result: dict
    vector: list[float]
```

`result` must always be a plain dictionary containing JSON-serializable data.

`vector` contains the embedding vector and must remain a separate top-level field.

---

### `ErrorResponse`

```python
class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    message: str
```

Use this model for analyzer failures.

Do not terminate the process for ordinary analyzer errors.

---

## 5. Response Model Usage

Analyzers that do not produce an embedding must return:

```python
SuccessResponse | ErrorResponse
```

For example:

```python
def main(...) -> SuccessResponse | ErrorResponse:
    ...
```

Analyzers that produce an embedding must return:

```python
VectorSuccessResponse | ErrorResponse
```

For example:

```python
def main(...) -> VectorSuccessResponse | ErrorResponse:
    ...
```

The return annotation must use the concrete response models rather than `dict`, `object`, or `Any`.

`result` must always be a plain `dict`, not a Pydantic model.

---

## 6. Analyzer Result Payload

The analyzer-specific result belongs in:

```python
response.result
```

`result` must always be a plain dictionary.

The dictionary must contain only JSON-serializable values.

Do not use a Pydantic `BaseModel` as `result`.

For known result structures, use precise typing such as `TypedDict` where practical.

Do not duplicate response-envelope fields inside `result`.

For example:

```python
class AnalysisResult(TypedDict):
    summary: str
    score: float
    keywords: list[str]


result: AnalysisResult = {
    "summary": "...",
    "score": 0.95,
    "keywords": ["...", "..."],
}
```

For example, avoid:

```json
{
  "status": "success",
  "result": {
    "status": "success",
    "message": "...",
    "vector": [...]
  }
}
```

The response envelope and analyzer-specific result should remain separate.

For vector-producing analyzers:

```json
{
  "status": "success",
  "result": {
    "...": "analyzer-specific data"
  },
  "vector": [0.1, 0.2, 0.3]
}
```

---

# 7. Strict Typing

Use explicit, strict type annotations throughout the public API.

The `main(...)` function must have:

* fully typed parameters
* an explicit return type
* precise parameter types
* no unnecessary `Any`
* no untyped `dict`
* no untyped `list`

For example:

```python
def main(
    source: str,
    options: AnalyzerOptions,
) -> SuccessResponse | ErrorResponse:
    ...
```

Prefer precise types such as:

```python
str
int
float
bool
str | None
list[str]
list[float]
dict[str, str]
Literal[...]
TypedDict
```

over:

```python
Any
dict
list
object
```

When a result payload has a known structure, prefer `TypedDict` or another precise dictionary type.

Do not create a Pydantic `BaseModel` solely to represent the `result` payload.

The outer response is a Pydantic model, but `result` itself must always be a dictionary.

Use existing project types whenever possible rather than creating duplicate types.

The goal is strong IDE/IntelliSense support and minimal type-checking errors.

---

# 8. Environment Configuration

Environment-dependent configuration must use environment variables.

Required secrets/configuration must not be hardcoded in source code.

Gemini authentication must use `GEMINI_API_KEY`

Never hardcode:

* API keys
* tokens
* passwords
* credentials
* other secrets

Environment configuration must not prevent the module from being imported when runtime credentials are unavailable.

---

# 9. Preserve Existing Interface

When modifying an existing analyzer:

* preserve existing `main(...)` parameters unless an interface change is explicitly requested
* preserve existing response/result schemas unless an interface change is explicitly requested
* preserve existing externally observable behavior unless it conflicts with this specification
* avoid modifying unrelated files

Do not change the public interface merely for stylistic reasons.

---

# 10. Refactoring

Refactoring is allowed when it meaningfully improves:

* readability
* maintainability
* performance
* type safety
* code duplication
* error-proneness
* overall code quality

Performance and readability improvements are explicitly allowed.

However, refactoring must not unnecessarily change:

* the public `main(...)` interface
* response model types
* response structure
* existing output semantics

Prefer focused improvements over unrelated rewrites.

---

# 11. Avoid Unnecessary Code

Do not add code for hypothetical use cases.

Avoid unnecessary:

* abstraction layers
* wrapper functions
* duplicate models
* duplicate utilities
* compatibility layers
* configuration systems
* dependencies
* public functions

Keep the analyzer implementation as simple as reasonably possible while maintaining good:

* readability
* performance
* maintainability
* type safety

---

# 12. Existing Models and Types

Prefer reusing existing project types.

In particular, use:

```text
src/ai/models.py
```

for the common response models.

Do not redefine:

```python
SuccessResponse
VectorSuccessResponse
ErrorResponse
```

inside individual analyzer modules.

If an analyzer-specific result has a structured schema, use a precise dictionary type such as `TypedDict` when practical. Do not use a Pydantic `BaseModel` as the type of `result`.

---

# 13. Output Contract

Every analyzer must have a predictable output contract.

### Normal analyzer

```text
main(...)
    ↓
SuccessResponse | ErrorResponse
```

### Vector analyzer

```text
main(...)
    ↓
VectorSuccessResponse | ErrorResponse
```

Successful responses must contain:

```text
status = "success"
result = analyzer-specific result
```

Vector responses additionally contain:

```text
vector = list[float]
```

Error responses contain:

```text
status = "error"
message = str
```

---

# Core Requirements

1. **All analyzer files live under `src/ai/`.**
2. **Every analyzer exposes `main(...)` as its primary public entrypoint.**
3. **Analyzers are importable Python modules.**
4. **Importing a module must not execute analysis.**
5. **Use the existing `SuccessResponse`, `VectorSuccessResponse`, and `ErrorResponse` models.**
6. **`SuccessResponse.result` is always a plain `dict` containing JSON-serializable data.**
7. **`VectorSuccessResponse.result` is always a plain `dict`, with `vector: list[float]` as a separate top-level field.**
8. **`ErrorResponse` represents failures with a string `message`.**
9. **`result` must not be a Pydantic model.**
10. **Use `TypedDict` or other precise dictionary types for known result structures where practical.**
11. **Use explicit and precise return types for `main(...)`.**
12. **Use strict parameter and helper-function typing to minimize IntelliSense/type-checking errors.**
13. **Never hardcode secrets.**
14. **Environment configuration must not prevent module import.**
15. **Preserve existing public interfaces and output contracts unless explicitly asked to change them.**
16. **Performance, readability, maintainability, and type-safety refactoring is allowed.**
17. **Avoid unrelated or unnecessary refactoring.**
18. **Reuse existing project types and models instead of creating duplicates.**
19. **Keep the public API minimal.**
20. **Do not prescribe or unnecessarily alter the internal AI/LLM implementation as long as the interface and output contract are satisfied.**
