"""
Sandbox Security and Trust Boundary Policy.
Enforces untrusted execution policies, credential sanitization, and filesystem containment.
"""

import os
import re
from typing import Dict, List, Optional, Set


class SecurityViolationError(RuntimeError):
    """Raised when an untrusted execution attempts a forbidden action or accesses disallowed paths."""
    pass


class SandboxSecurityPolicy:
    """Enforces execution boundaries for untrusted generated code."""

    # Disallowed environment variable patterns (secrets, credentials)
    SENSITIVE_ENV_PATTERNS = [
        r".*API_KEY.*",
        r".*SECRET.*",
        r".*PASSWORD.*",
        r".*TOKEN.*",
        r".*AUTH.*",
        r".*CREDENTIAL.*",
        r"AWS_.*",
        r"GITHUB_.*",
        r"GH_.*",
        r"SSH_.*",
    ]

    # Explicitly permitted safe environment variables
    ALLOWED_ENV_NAMES = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUTF8",
        "VIRTUAL_ENV",
        "LANG",
        "LC_ALL",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
    }

    # Forbidden command patterns
    FORBIDDEN_COMMAND_PATTERNS = [
        r"rm\s+-rf",
        r"format\s+[A-Z]:",
        r"curl\s+",
        r"wget\s+",
        r"nc\s+",
        r"netcat\s+",
        r"bash\s+-i",
        r"cmd\.exe\s+/c\s+del",
    ]

    @classmethod
    def sanitize_environment(cls, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Strips all sensitive credentials, tokens, and private keys from the execution environment.
        """
        source = base_env if base_env is not None else dict(os.environ)
        sanitized: Dict[str, str] = {}

        for k, v in source.items():
            k_upper = k.upper()
            # If explicitly allowed and not matching sensitive patterns
            is_sensitive = any(re.match(pat, k_upper) for pat in cls.SENSITIVE_ENV_PATTERNS)
            if not is_sensitive:
                if k_upper in cls.ALLOWED_ENV_NAMES or k.startswith("PYTEST_") or k.startswith("PYTHON"):
                    sanitized[k] = v

        # Enforce isolated python flags
        sanitized["PYTHONDONTWRITEBYTECODE"] = "1"
        return sanitized

    @classmethod
    def validate_command(cls, cmd: List[str]) -> None:
        """
        Validates command against safety policies.
        """
        if not cmd:
            raise SecurityViolationError("Empty command is not permitted.")

        cmd_str = " ".join(cmd)
        for pattern in cls.FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pattern, cmd_str, re.IGNORECASE):
                raise SecurityViolationError(f"Security policy violation: forbidden command pattern '{pattern}'.")

    @classmethod
    def validate_filesystem_boundary(cls, target_path: str, repo_root: str) -> None:
        """
        Ensures target file or working directory is strictly contained within repo_root.
        """
        norm_target = os.path.realpath(os.path.abspath(target_path))
        norm_root = os.path.realpath(os.path.abspath(repo_root))

        try:
            common = os.path.commonpath([norm_target, norm_root])
            if common != norm_root:
                raise SecurityViolationError(
                    f"Security boundary violation: target path '{norm_target}' escapes repo root '{norm_root}'."
                )
        except ValueError:
            raise SecurityViolationError(
                f"Security boundary violation: target path '{norm_target}' escapes repo root '{norm_root}'."
            )
