"""Typed Sentinel failures."""


class SentinelError(Exception):
    """Base class for expected Sentinel failures."""


class ConfigurationError(SentinelError):
    """Configuration cannot be materialized safely."""


class ValidationError(SentinelError):
    """An input violates a declared contract."""


class CapabilityDeferredError(SentinelError):
    """A recognized capability is explicitly deferred."""

    def __init__(self, capability: str, target_phase: str = "post-phase-2") -> None:
        self.capability = capability
        self.target_phase = target_phase
        super().__init__(f"Capability {capability!r} is deferred to {target_phase}")


class ModuleUnavailableError(SentinelError):
    """A module cannot assess an asset without fabricating a clean result."""


class ProvenanceError(SentinelError):
    """Protected provenance creation or verification failed."""


class FinalizationError(SentinelError):
    """A run cannot be finalized without violating write-once semantics."""
