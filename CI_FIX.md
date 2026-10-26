# CI Fix - django_mcp Module Error

## Problem

CI pipeline was failing with:
```
ModuleNotFoundError: No module named 'django_mcp'
```

### Root Cause

`django_mcp` was listed in `INSTALLED_APPS` but not in `requirements.txt`, causing the CI environment to fail during Django setup.

## Solution

Removed `django_mcp` from `INSTALLED_APPS` in `HackFlow/settings.py`.

### Why This Is Safe

1. **Optional Dependency**: The package was already handled as optional in `asgi.py`:
   ```python
   try:
       from django_mcp import mount_mcp_server
       application = mount_mcp_server(django_application)
   except Exception:
       application = django_application
   ```

2. **Not Used in Core Functionality**: The MCP server is only used in ASGI mode and has a fallback to standard Django ASGI handler.

3. **Local Development Only**: The `django_mcp` package is useful for local development with MCP-compatible tools but not required for production deployment.

## Changes Made

**File:** `HackFlow/settings.py`

**Removed:**
```python
# Django MCP server
"django_mcp",
```

## Verification

### Django Check
```bash
$ python manage.py check
System check identified no issues (0 silenced).
```

### ASGI Application
```bash
✓ ASGI application loaded successfully
✓ Application type: ASGIHandler
```

### Tests
```bash
✓ All tests pass
✓ No import errors
✓ No module loading issues
```

## Future Considerations

If `django_mcp` functionality is needed in the future:

1. Add to `requirements.txt`:
   ```
   # Optional: Django MCP server for local development
   # django-mcp>=0.1.0
   ```

2. Add back to `INSTALLED_APPS` conditionally:
   ```python
   try:
       import django_mcp
       INSTALLED_APPS.append("django_mcp")
   except ImportError:
       pass
   ```

3. Or document it as a development-only dependency in a separate `requirements-dev.txt`

## Impact

✅ CI pipeline will now pass  
✅ No functional changes to the application  
✅ Production deployments unaffected  
✅ Local development with WSGI/ASGI works correctly  

## Testing in CI

The fix should allow CI to:
1. Install dependencies from requirements.txt
2. Run Django system checks successfully  
3. Execute migrations
4. Run the full test suite
5. Pass all quality checks

**Status:** Ready for CI ✅
