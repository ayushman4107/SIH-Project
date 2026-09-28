"""Typed Visiops failures."""


class VisiopsError(Exception):
    """Base class for expected Visiops failures."""


class ConfigurationError(VisiopsError):
    """Configuration cannot be materialized safely."""


class ValidationError(VisiopsError):
    """An input violates a declared contract."""


class CapabilityDeferredError(VisiopsError):
    """A recognized capability is explicitly deferred."""

    def __init__(self, capability: str, target_phase: str = "post-phase-2") -> None:
        self.capability = capability
        self.target_phase = target_phase
        super().__init__(f"Capability {capability!r} is deferred to {target_phase}")


class ModuleUnavailableError(VisiopsError):
    """A module cannot assess an asset without fabricating a clean result."""


class ProvenanceError(VisiopsError):
    """Protected provenance creation or verification failed."""


class FinalizationError(VisiopsError):
    """A run cannot be finalized without violating write-once semantics."""
