export type Disposition = "accept" | "review" | "quarantine" | "inconclusive";

export interface AssuranceReport {
  report_metadata: {
    report_id: string;
    timestamp: string;
    phase: string;
    dataset_id: string;
    model_name: string;
    model_format: string;
    preprocessing?: {
      image_size: number[];
      normalize_mean: number[];
      normalize_std: number[];
    };
  };
  disposition: {
    overall: Disposition;
    reasoning: string;
  };
  pillars: {
    F1_data_integrity: F1DataIntegrity;
    F2_model_integrity: F2ModelIntegrity;
    F3_inference_provenance: F3InferenceProvenance;
    F4_distribution_shift: F4DistributionShift;
    F5_aggregation_and_governance: F5AggregationAndGovernance;
  };
  canonical_findings: {
    total_count: number;
    by_type: Record<string, number>;
    by_severity: Record<string, number>;
    by_disposition: Record<string, number>;
  };
  coverage_statement: {
    framework: string;
    version: string;
    generated: string;
    supported_attacks: SupportedAttack[];
    unsupported_attacks: UnsupportedAttack[];
    assumptions: string[];
    known_limitations: string[];
  };
  manifest: {
    dataset_id: string;
    dataset_sample_count: number;
    dataset_hash: string;
    model_id: string;
    model_hash: string;
    model_parameter_count: number;
    config_hash: string;
    reference_clean_model_hash: string;
  };
}

// ─── F1: Data Integrity ──────────────────────────────────────────────────────

export interface SybilSyndicate {
  members: string[];
  internal_edge_density: number;
  calibrated_confidence: number;
  disposition: "QUARANTINE" | "REVIEW";
}

export interface SybilCollusion {
  finding_type: "SYBIL_COLLUSION_SYNDICATE" | "CLEAN";
  used_uniform_prior?: boolean;
  syndicates: SybilSyndicate[];
}

export interface InfluenceSuspect {
  sample_id: string;
  influence_score: number;
  source_id: string;
  class_id?: number;
}

export interface F1InfluenceFunctions {
  status: string;
  method: string;
  top_suspects: InfluenceSuspect[];
}

export interface F1DataIntegrity {
  status: string;
  total_findings: number;
  summary: {
    label_errors: { count: number; severity: string; method: string; confidence_range: number[] };
    near_duplicates: { count: number; severity: string; method: string; confidence_range: number[] };
    statistical_outliers: { count: number; severity: string; method: string; confidence_range: number[] };
  };
  sybil_collusion?: SybilCollusion;
  influence_functions?: F1InfluenceFunctions;
  contributor_risk_aggregation: Array<{
    source_id: string;
    batches: string[];
    samples_contributed: number;
    problematic_samples: number;
    risk_score: number;
    recommendation: string;
  }>;
  sample_findings: SampleFinding[];
}

export interface SampleFinding {
  finding_id: string;
  type: string;
  sample_id?: string;
  sample_ids?: string[];
  source_id?: string;
  batch_id?: string;
  batch_ids?: string[];
  severity: string;
  confidence: number;
  evidence: Record<string, any> & { method: string; description: string };
  disposition: Disposition;
  recommended_action: string;
}

// ─── F2: Model Integrity ─────────────────────────────────────────────────────

export interface ActivationClusterFinding {
  class_id: number;
  layer_name: string;
  silhouette_score: number;
  minority_fraction: number;
  suspected_sample_count: number;
  severity: string;
  confidence: number;
}

export interface ActivationClustering {
  status: string;
  layer_name: string;
  findings: ActivationClusterFinding[];
  classes_analyzed: number;
  clean_classes: number;
  suspicious_classes: number[];
}

export interface GradientClusterFinding {
  class_id: number;
  layer_name: string;
  cluster_separation_score: number;
  minority_fraction: number;
  suspected_sample_count: number;
  severity: string;
  confidence: number;
}

export interface GradientClustering {
  status: string;
  method: string;
  findings: GradientClusterFinding[];
  classes_analyzed: number;
  clean_classes: number;
  suspicious_classes: number[];
}

export interface F2InfluenceFunctions {
  status: string;
  method: string;
  top_suspects: InfluenceSuspect[];
}

export interface F2ModelIntegrity {
  status: string;
  access_level: string;
  confidence: number;
  assessment: string;
  interpretation: string;
  method: string;
  findings: any[];
  limitations: string;
  evidence: {
    architecture_match: boolean;
    architecture_name: string;
    parameter_count_clean_reference: number;
    parameter_count_submitted: number;
    per_layer_analysis: Array<{
      layer_name: string;
      spectral_signature_clean_svd_singular_values: number[];
      spectral_signature_submitted_svd_singular_values: number[];
      wasserstein_distance: number;
      threshold: number;
      status: string;
    }>;
    leave_one_out_calibration: {
      accuracy_on_clean_reference: number;
      accuracy_on_submitted_model: number;
      delta: number;
      threshold: number;
      status: string;
    };
    nextafter_max_clean_threshold: {
      computed_clean_max_spectra: number;
      submitted_max_spectra: number;
      nextafter_boundary: number;
      submitted_is_below: boolean;
      status: string;
    };
    // New: white-box behavioral detectors
    activation_clustering?: ActivationClustering;
    gradient_clustering?: GradientClustering;
    influence_functions?: F2InfluenceFunctions;
  };
}

// ─── F3: Inference Provenance ────────────────────────────────────────────────

export interface RatchetScheme {
  algorithm: string;
  description: string;
  page_locked: boolean;
  secure_zeroization: boolean;
  forward_secrecy: boolean;
  ratchet_version: string;
}

export interface F3InferenceProvenance {
  status: string;
  binding_type: string;
  hmac_status: string;
  fail_open: boolean;
  ratchet_scheme?: RatchetScheme;
  inference_records: Array<{
    inference_id: string;
    sample_id: string;
    timestamp: string;
    input_sha256: string;
    model_digest: string;
    preprocessing_config_digest: string;
    predicted_label: number;
    confidence: number;
    output_sha256: string;
    binding_hmac: string;
    verified: boolean;
  }>;
  audit_ledger_entries: number;
  ledger_status: string;
  tampering_detection: {
    missing_entries: boolean;
    reordered_entries: boolean;
    modified_digests: boolean;
    altered_hmacs: boolean;
  };
  tail_truncation_check: string;
}

// ─── F4: Distribution Shift ──────────────────────────────────────────────────

export interface SyntheticProjectorResult {
  status: string;
  finding_type: "ORTHOGONAL_DRIFT_ANOMALY" | "NATURAL_COVARIATE_DRIFT";
  orthogonality_ratio: number;
  total_displacement: number;
  disposition: "QUARANTINE" | "REVIEW";
  manifold_basis_components?: number;
  variance_threshold?: number;
  ortho_threshold?: number;
  interpretation?: string;
}

export interface F4DistributionShift {
  status: string;
  ood_score: number;
  method: string;
  interpretation: string;
  threshold: number;
  explanation: string;
  evidence: {
    reference_distribution: string;
    submitted_sample_count: number;
    mahalanobis_distances: {
      mean: number;
      median: number;
      "95th_percentile": number;
      reference_mean: number;
      reference_95th_percentile: number;
    };
    predictive_entropy_ratio: {
      reference_entropy: number;
      submitted_entropy: number;
      ratio: number;
      interpretation: string;
    };
    outlier_percentage: number;
    outlier_threshold: string;
    samples_flagged: number;
    synthetic_projector?: SyntheticProjectorResult;
  };
  disposition: Disposition;
  recommendation: string;
  limitations: string | string[];
}

// ─── F5: Governance ───────────────────────────────────────────────────────────

export interface F5AggregationAndGovernance {
  aggregation_rule: string;
  pillar_dispositions: Array<{ pillar: string; severity: string; count: number; disposition: Disposition }>;
  maximum_severity: string;
  aggregated_disposition: Disposition;
  policy_exceptions: any[];
  analyst_summary: string;
}

// ─── Coverage ─────────────────────────────────────────────────────────────────

export interface SupportedAttack {
  attack_class: string;
  method: string;
  confidence_range_min: number;
  confidence_range_max: number;
  tested_on_dataset: string;
  tested_poison_ratio: number;
  validation_folds: number;
  evidence: string;
}

export interface UnsupportedAttack {
  attack_class: string;
  reason: string;
}

// ─── Audit Log ────────────────────────────────────────────────────────────────

export interface AuditLog {
  ledger_metadata: {
    report_id: string;
    ledger_id: string;
    created: string;
    entry_count: number;
    chain_status: string;
    hmac_scheme: string;
    secret_key_required: boolean;
  };
  ledger: Array<{
    sequence: number;
    timestamp: string;
    action: string;
    status: string;
    duration_seconds: number;
    samples_processed?: number;
    findings_count?: number;
    entry_payload_hash: string;
    entry_hash: string;
    previous_entry_hash: string;
    hmac_sha256: string;
  }>;
  chain_verification: {
    total_entries: number;
    links: Array<{
      from_sequence: number;
      to_sequence: number;
      stored_previous_hash: string;
      computed_entry_hash: string;
      match: boolean;
      status: string;
    }>;
    tampering_checks: {
      missing_entries: boolean;
      reordered_entries: boolean;
      modified_hashes: boolean;
      broken_chain: boolean;
      overall_status: string;
    };
  };
  hmac_verification: {
    scheme: string;
    entries_verified: number;
    entries_unsigned: number;
    verification_results: Array<{
      sequence: number;
      stored_hmac: string;
      recomputed_hmac: string;
      match: boolean;
      status: string;
    }>;
    fail_open_detected: boolean;
    unsigned_entries: boolean;
  };
  root_hash: {
    final_entry_hash: string;
    ledger_root: string;
    manifest_digest: string;
  };
  verification_summary: {
    status: string;
    message: string;
    timestamp_verified: string;
    verified_against_key: string;
    tail_truncation_check: string;
    independent_ledger_length_provided: boolean;
    tail_truncation_risk: boolean;
  };
}
