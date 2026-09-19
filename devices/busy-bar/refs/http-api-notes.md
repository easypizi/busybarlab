# BUSY Bar HTTP API notes

Source: https://docs.busy.app/bar/dev/http-api (fetched 2026-09-19)

## Draw and upload

- `POST /api/assets/upload?application_name=&file=` with `Content-Type: application/octet-stream`. Image <= 255 KB. `busylib.assets_upload` sends bytes as-is. Resize first.
- `POST /api/display/draw` JSON: `application_name` + `elements[]` with `id`, `type` (`text`|`image`), `display` (`front`|`back`), `x`, `y`, plus text/font/color/width/align/scroll_* or image `path`.
- Fonts in official examples: `small` (5), `medium` (7), `big` / `extra_large`.
- Color is 8-digit hex including alpha, e.g. `#00FF00FF`.

## Auth examples

USB: no header.

Wi-Fi:

```
X-API-Token: <password>
```

Cloud:

```
Authorization: Bearer <token>
```

## Libraries

- Python: https://pypi.org/project/busylib/
- TypeScript: https://go.busy.app/typescript-library
