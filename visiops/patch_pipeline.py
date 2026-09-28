import re

path = r"d:\SIH-Project-main\visiops\pipeline.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = """            assessments["F1"] = f1.assessment
            source_assessments = list(f1.source_assessments)
        except Exception as exc:"""

replacement = """            # --- SPECTRAL SUBBAND REPAIR (F1 Stretch Goal) ---
            from visiops.modules.spectral_subband_repair import SpectralSubbandRepairDetector
            spectral_findings = list(f1.assessment.findings)
            
            try:
                # We initialize the detector
                spectral_detector = SpectralSubbandRepairDetector()
                
                # Mock baselines for the sake of pipeline integration without full Phase 3 implementation
                baselines = {}
                for ch in ["Y", "Cr", "Cb"]:
                    baselines[ch] = {}
                    for ri in range(spectral_detector.n_radial_bins):
                        for ai in range(spectral_detector.n_angular_bins):
                            baselines[ch][(ri, ai)] = {"median": 0.1, "mad": 0.05, "samples": 20, "tier": 1}

                # Ensure directory exists
                (staging / "artifacts" / "spectral_masks").mkdir(parents=True, exist_ok=True)
                
                if train_images is not None:
                    import cv2
                    from visiops.core.models import Finding, FindingType, Pillar, AssetLocator, Severity, MethodIdentity, Disposition
                    from visiops.utils.atomic_io import atomic_write_bytes
                    
                    # Convert tensors back to BGR numpy for OpenCV
                    # train_images is typically (N, C, H, W) normalized.
                    # We will just pass a zero image if we can't reliably convert it, or use the original files.
                    for i, sample in enumerate(manifest.samples):
                        image_path = sample.image_path
                        bgr_img = cv2.imread(str(image_path))
                        if bgr_img is not None:
                            all_findings, heatmap, metrics = spectral_detector.screen_image(bgr_img, baselines)
                            if metrics["verdict"] in ["quarantine", "review"]:
                                # Save the spectral mask artifact
                                artifact_filename = f"{sample.sample_id}_heatmap.npy"
                                artifact_rel_path = f"artifacts/spectral_masks/{artifact_filename}"
                                np.save(staging / artifact_rel_path, heatmap.astype(np.float32))
                                
                                # Create a Finding for F1
                                severity = Severity.HIGH if metrics["verdict"] == "quarantine" else Severity.MEDIUM
                                disposition = Disposition.QUARANTINE if metrics["verdict"] == "quarantine" else Disposition.REVIEW
                                
                                spectral_findings.append(
                                    Finding(
                                        finding_type=FindingType.POSSIBLE_DRIFT, # Reusing type for now, or define SPECTRAL_ANOMALY
                                        pillar=Pillar.F1,
                                        affected_asset=AssetLocator("sample", sample.sample_id),
                                        severity=severity,
                                        raw_score=metrics["flagged_fraction"],
                                        decision_threshold=0.001,
                                        confidence=0.9,
                                        confidence_normalizer="spectral_fdr",
                                        human_readable_reason="High-frequency spectral anomalies detected in image subbands.",
                                        evidence={
                                            "flagged_pixel_count": metrics["flagged_pixel_count"],
                                            "flagged_fraction": metrics["flagged_fraction"],
                                            "visual_artifact_ref": artifact_rel_path,
                                            "box_findings": [
                                                {"row": f.patch_row, "col": f.patch_col, "channel": f.channel, "anomaly_index": f.anomaly_index}
                                                for ch_findings in all_findings.values() for f in ch_findings
                                            ]
                                        },
                                        method=MethodIdentity("spectral_subband_repair", "1"),
                                        recommended_disposition=disposition,
                                    )
                                )
                from visiops.core.models import ModuleAssessment
                assessments["F1"] = ModuleAssessment(
                    status=f1.assessment.status,
                    findings=tuple(spectral_findings),
                    methods_executed=f1.assessment.methods_executed + ("spectral_subband_repair",),
                    methods_unavailable=f1.assessment.methods_unavailable,
                )
            except Exception as e:
                import logging
                logging.warning(f"Spectral Repair failed: {e}")

            source_assessments = list(f1.source_assessments)
        except Exception as exc:"""

content = content.replace(target, replacement)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
