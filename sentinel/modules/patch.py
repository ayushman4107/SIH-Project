import re

path = r"d:\SIH-Project-main\sentinel\modules\inference_provenance\__init__.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace generate method
generate_target = """    def generate(
        self,
        *,
        input_path: Path,
        model_path: Path,
        config: dict[str, Any],
        output: Any,
        run_root: Path,
        sequence_number: int,
    ) -> ProvenanceGeneration:"""

generate_replacement = """    def execute_and_generate(
        self,
        *,
        input_path: Path,
        model: Any,
        tensor: Any,
        config: dict[str, Any],
        run_context: Any,
        run_root: Path,
        sequence_number: int,
        ledger: Any,
    ) -> ProvenanceGeneration:
        from .stages import get_deployment_identifier, stage_3a_open, stage_3b_execute, stage_3c_authenticate_and_chain
        from sentinel.utils.atomic_io import atomic_write_bytes
        from sentinel.utils.hashing import canonical_json_bytes

        deployment_id = get_deployment_identifier()
        input_bytes = input_path.read_bytes()
        
        pending_record = stage_3a_open(
            input_bytes=input_bytes,
            run_context=run_context,
            loaded_model=model,
            deployment_identifier=deployment_id,
            ledger=ledger
        )

        output_bytes, output_digest = stage_3b_execute(pending_record, tensor)
        
        record_id = pending_record.request_id
        input_ref = f"artifacts/inputs/{record_id}{input_path.suffix.lower() or '.bin'}"
        config_ref = f"artifacts/configs/{record_id}.json"
        output_ref = f"artifacts/outputs/{record_id}.npy"
        
        base = None
        try:
            atomic_write_bytes(run_root / input_ref, input_bytes)
            atomic_write_bytes(run_root / config_ref, canonical_json_bytes(config) + b"\\n")
            atomic_write_bytes(run_root / output_ref, _npy_bytes(np.frombuffer(output_bytes, dtype=np.float32)))
            
            if not self.ratchet:
                raise ValueError("Ratchet not initialized (invalid or missing secret key)")
                
            current_key = self.ratchet.get_key()
            record = stage_3c_authenticate_and_chain(
                pending=pending_record,
                output_bytes=output_bytes,
                output_digest=output_digest,
                current_key=current_key,
                ledger=ledger
            )
            base = record
            base["input_ref"] = input_ref
            base["config_ref"] = config_ref
            base["output_ref"] = output_ref
            base["status"] = ProvenanceStatus.SIGNED.value
            
            hmac_hex = record["binding_hmac"]
            self.ratchet.ratchet(hmac_hex.encode("utf-8"))
        except Exception as exc:
            base = {
                "request_id": record_id,
                "status": ProvenanceStatus.UNSIGNED.value,
                "binding_hmac": None,
                "failure_reason": f"{type(exc).__name__}: {exc}"
            }
            if getattr(self, "ratchet", None):
                self.ratchet.ratchet(b"UNSIGNED_RECORD")
                
        return ProvenanceGeneration(base, np.frombuffer(output_bytes, dtype=np.float32))"""

# Replace generate method body.
# We'll use regex to replace from def generate to def verify_chain
content = re.sub(r"    def generate\(.*?    def verify_chain\(", generate_replacement + "\n\n    def verify_chain(", content, flags=re.DOTALL)

verify_target = """                    expected_binding = binding_hmac(
                        current_key,
                        checks["input_hash"],
                        checks["model_hash"],
                        checks["config_hash"],
                        checks["output_hash"],
                    )"""

verify_replacement = """                    format_version = record.get("binding_format_version", "v1")
                    if format_version == "v1":
                        results.append(VerificationResult(VerificationVerdict.UNAVAILABLE, "UNSUPPORTED_FORMAT_VERSION", sequence))
                        record_hmac = str(record.get("binding_hmac", ""))
                        ratchet.ratchet(record_hmac.encode("utf-8") if record_hmac else b"UNSIGNED_RECORD")
                        continue
                    elif format_version == "v2":
                        deployment_json = canonical_json_bytes(record.get("deployment_identifier", {})).decode('utf-8')
                        message = "|".join([
                            "v2",
                            record.get("request_id", ""),
                            checks["input_hash"],
                            record.get("admitted_model_id", ""),
                            record.get("preprocessing_digest", ""),
                            deployment_json,
                            checks["output_hash"],
                            str(record.get("nonce", ""))
                        ]).encode('utf-8')
                        expected_binding = hmac_sha256(current_key, b"binding|", message)
                    else:
                        results.append(VerificationResult(VerificationVerdict.TAMPERED, "unknown format version", sequence))
                        ratchet.ratchet(b"UNSIGNED_RECORD")
                        continue"""

content = content.replace(verify_target, verify_replacement)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
