# Architecture Rules

## Routes

Routes must:

- Validate request
- Call service
- Return response

Routes must not:

- Access database directly
- Execute AI logic

# Service Rules

Services must:

- Contain business logic

Services must not:

- Return HTML
- Handle UI logic

# AI Rules

Detector should be replaceable.

Recognizer should be replaceable.

Search engine should be replaceable.

Business logic must not depend on specific models.

# Documentation Rules

Every feature must update when applicable:

- `05-system-design.md`
- `backend.md`
- `08-api-design.md`