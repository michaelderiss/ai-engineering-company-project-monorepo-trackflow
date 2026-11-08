# TrackFlow API serialization audit

## Scope and conventions

This audit covers all 37 application business routes declared in `services/api/main.py` and `services/api/routes/`. FastAPI-generated `/openapi.json`, `/docs`, and `/redoc` are framework metadata endpoints, not business response contracts; they are intentionally not assigned application serializers. Error responses are produced by the global handlers and are not route success payloads.

Success responses now have an explicit Pydantic response model except the CSV download, whose response is deliberately declared in OpenAPI as `text/csv` with a string body because it is a streamed file, not JSON. Request models remain distinct from response projections. Internal `User` and ORM/storage models are not used as public response contracts. In particular, `hashed_password` is never serialized; public signup does not return email and cannot assign a role or active status; user-directory endpoints omit email; and only authenticated `GET /auth/me` returns the caller's own email. Inventory movement outputs omit the internal `user_uuid` actor identifier.

The target fields listed below are exact success-body projections. Nullable fields may be present as `null` where the schema defines them. All routes require authentication unless noted.

## Endpoint-by-endpoint matrix

| Method and path | Original response contract | Target response fields / media | Change |
|---|---|---|---|
| `POST /auth/login` | `Token` response model | `access_token`, `token_type` | Existing explicit token model retained. |
| `GET /auth/me` | Internal `User`, including `hashed_password` | `id`, caller `email`, `is_active`, `role`, `created_at`, `updated_at`, optional profile (`id`, `user_id`, `display_name`, `phone`, `address`) | Replaced internal schema with a safe caller projection. |
| `POST /auth/forgot-password` | Untyped message dictionary | `message` | Added explicit generic response; no email is returned. |
| `POST /auth/reset-password` | Untyped message dictionary | `message` | Added explicit response; no email/password is returned. |
| `POST /auth/change-password` | Untyped message dictionary | `message` | Added explicit response; no credentials are returned. |
| `POST /users` | Internal `User`, including email, `hashed_password`, and profile | `id`, `is_active`, `role`, `created_at`, `updated_at` | Added signup-only output; request rejects caller-supplied role/status. |
| `GET /users` | `list[User]`, exposing hashes, email, and nested profile | List of `id`, `is_active`, `role`, `created_at`, `updated_at` | Replaced with slim directory projection. |
| `GET /users/{user_id}` | `User`, exposing hash and email | `id`, `is_active`, `role`, `created_at`, `updated_at` | Replaced with slim per-user projection. |
| `PATCH /users/{user_id}` | `User`, exposing hash and email | `id`, `is_active`, `role`, `created_at`, `updated_at` | Replaced output; role/status changes require admin. |
| `DELETE /users/{user_id}` | Untyped `{deleted, id}` | `deleted`, `id` | Added explicit delete response. |
| `POST /profiles` | `Profile` model | `id`, `user_id`, `display_name`, `phone`, `address` | Replaced with response-only profile projection. |
| `GET /profiles` | `list[Profile]` | List of `id`, `user_id`, `display_name`, `phone`, `address` | Replaced with response-only projection. |
| `GET /profiles/me` | `Profile` | `id`, `user_id`, `display_name`, `phone`, `address` | Replaced with response-only projection. |
| `PATCH /profiles/me` | `Profile` | `id`, `user_id`, `display_name`, `phone`, `address` | Replaced with response-only projection. |
| `GET /profiles/{profile_id}` | `Profile` | `id`, `user_id`, `display_name`, `phone`, `address` | Replaced with response-only projection. |
| `PATCH /profiles/{profile_id}` | `Profile` | `id`, `user_id`, `display_name`, `phone`, `address` | Replaced with response-only projection. |
| `POST /suppliers` | `Supplier` inheriting the write model | `id`, `name`, `country`, `categories`, `rate_per_shipment`, `currency`, `status`, `service_zone`, `contact_email`, `notes`, `updated_at` | Added dedicated output projection. Supplier contact email is business data, not a user credential. |
| `GET /suppliers` | `list[Supplier]` inheriting write model | Same supplier projection | Added dedicated output projection. |
| `GET /suppliers/{supplier_id}` | `Supplier` inheriting write model | Same supplier projection | Added dedicated output projection. |
| `PATCH /suppliers/{supplier_id}/rate` | `Supplier` inheriting write model | Same supplier projection | Added dedicated output projection. |
| `PATCH /suppliers/{supplier_id}/status` | `Supplier` inheriting write model | Same supplier projection | Added dedicated output projection. |
| `DELETE /suppliers/{supplier_id}` | Untyped `{deleted, id}` | `deleted`, `id` | Added explicit delete response. |
| `GET /inventory/products` | `list[SKURead]` inheriting create shape | `id`, `name`, `sku`, `client_name`, `category`, `warehouse`, `current_stock` | Replaced with dedicated output projection; cached catalog semantics unchanged. |
| `POST /inventory/products` | `SKURead` inheriting create shape | Same SKU projection | Replaced with dedicated output projection. |
| `GET /inventory/products/{sku_id}` | `SKURead` inheriting create shape | Same SKU projection | Replaced with dedicated output projection. |
| `POST /inventory/orders/inbound` | `StockEntryRead`, including `user_uuid` | `id`, `sku_id`, `quantity`, `reference`, `warehouse`, `created_at` | Removed internal actor ID from response. |
| `POST /inventory/orders/outbound` | `StockExitRead`, including `user_uuid` | `id`, `sku_id`, `quantity`, `exit_type`, `tracking_number`, `warehouse`, `created_at` | Removed internal actor ID from response. |
| `GET /inventory/orders` | `list[StockOrderRead]`, including actor ID and broad nested SKU reference | `id`, `order_type`, `sku_id`, `quantity`, nullable `reference`, nullable `exit_type`, nullable `tracking_number`, `warehouse`, `created_at`, and SKU (`id`, `name`, `sku`, `client_name`, `category`, `warehouse`) | Dedicated projection omits actor ID; history UI no longer renders internal creator IDs. |
| `GET /api/incidents/options` | Untyped dictionary | `branches`, `categories`, `statuses`, `origins`, `transitions` | Added explicit lookup response. |
| `GET /api/incidents/summary` | Untyped cached dictionary | `total`, `by_status`, `by_category`, `by_origin`, `by_branch` | Added explicit summary response; user-scoped cache behavior unchanged. |
| `POST /api/incidents` | Shared incident model inheriting request shape | `id`, `title`, `description`, `category`, `status`, `origin`, `branch`, `created_at`, `updated_at` | API-owned output projection avoids coupling output filtering to shared request model. |
| `GET /api/incidents` | `list[Incident]` | List of the incident projection above | Replaced with API-owned output projection. |
| `GET /api/incidents/{incident_id}` | `Incident` | Incident projection above | Replaced with API-owned output projection. |
| `PATCH /api/incidents/{incident_id}/status` | `Incident` | Incident projection above | Replaced with API-owned output projection. |
| `GET /health` | Untyped status dictionary | `status` (`"ok"`) | Added explicit health response. |
| `POST /api/incidents/analyze` | Untyped analysis dictionary | `total_records`, `valid_records`, `invalid_records`, `invalid_breakdown`, `category_breakdown`, `status_breakdown`, `country_breakdown`, `satisfaction_breakdown`, `satisfaction_average`, `scored_closed_incidents`, `closed_incidents`, `source_file` | Added explicit analysis response; response values and existing analyzer behavior retained. |
| `GET /api/incidents/results/export` | Streaming response without explicit OpenAPI content schema | `text/csv` string body; attachment filename `results.csv` | Explicitly documented streamed media type; no misleading JSON response model. |

## Security and compatibility notes

- The internal `User` model still carries `hashed_password` for authentication/storage. It is not a response model.
- Signup accepts only email, password, and optional profile input. Role and active status are server defaults (`user`, active). A self-service PATCH cannot assign a role or alter active status; administrators can manage these fields.
- `GET /auth/me` is the only user endpoint exposing email, and only for the authenticated account, matching the profile page's own-account requirement. Signup, login, forgot-password, and reset-password responses do not echo email or password values.
- Inventory persistence continues recording the actor identifier internally for audit purposes; response projections and the UI omit it because the public API has no user-display-name relationship and the raw numeric ID is not meaningful as a creator label.
- The catalog cache and user-scoped incident-summary cache, their TTLs, invalidation, authentication, and no-store behavior are unchanged.
- Error response payloads remain governed by the application-wide exception handlers; these are not successful route serializers.

## Verification

The route tests assert omitted sensitive fields and the retained functional fields. OpenAPI schema checks and the backend/frontend validation results are recorded with the milestone changes after execution. Interactive `/docs` checks should verify at least `GET /auth/me`, `GET /inventory/products`, and `GET /api/incidents/summary` against a running API with a valid bearer token where required.
