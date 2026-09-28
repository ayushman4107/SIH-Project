export interface AssuranceReport {
  schema_version: string;
  case_id: string;
  subject_type: 'TRAINING_SAMPLE' | 'CANDIDATE_MODEL' | 'INFERENCE';
  sample_id: string | null;
  request_id: string | null;
  dataset_version: string | null;
  model_id: string | null;
  raw_input_digest: string | null;
  preprocessed_input_digest: string | null;
  preprocessing_hash: string | null;
  F1_data_integrity: {
    box_status: string;
    activation_edge_centroid_finding_ids: string[];
    spectral_status: string;
    spectral_screen_id: string | null;
    mask_id: string | null;
    mask_source_image_digest: string | null;
  };
  F2_model_integrity: {
    probe_set_id: string | null;
    fingerprint_component_scores: Record<string, number>;
    behavioral_status: string;
    quant_baseline_id: string | null;
    quantization_status: string;
    admission: string;
  };
  F3_inference_provenance: {
    audit_seq: number | null;
    raw_output_digest: string | null;
    raw_record_hash: string | null;
    assessment_record_hash: string | null;
    chain_status: string;
    vdf_status: string;
    checkpoint_id: string | null;
    telemetry_status: string;
  };
  F4_shift_assessment: {
    energy: number | null;
    entropy: number | null;
    mahalanobis_distance: number | null;
    grad_h_norm: number | null;
    missing_signals: string[];
    risk_score: number | null;
    disposition: string;
  };
  F5_governance: {
    action: string;
    analyst_decision: string | null;
    limitation_notes: string[];
  };
}
export type Disposition = 'ACCEPT' | 'REVIEW' | 'QUARANTINE' | 'PENDING';
