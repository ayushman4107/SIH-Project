import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getLedger, getReport } from '../api/client';
import type { AuditLog, AssuranceReport } from '../api/types';
import VerificationStatus from '../components/VerificationStatus';
import { Clock, Key, ShieldAlert, Lock, Shield, Zap } from 'lucide-react';

export default function Ledger() {
  const { reportId } = useParams();
  const [ledger, setLedger] = useState<AuditLog | null>(null);
  const [report, setReport] = useState<AssuranceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!reportId) return;
    setLoading(true);
    Promise.all([getLedger(reportId), getReport(reportId)])
      .then(([ledgerData, reportData]) => {
        setLedger(ledgerData);
        setReport(reportData);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [reportId]);

  if (loading) return <div className="text-muted text-center py-12">Loading ledger...</div>;
  if (error) return <div className="text-red-500 text-center py-12">Error: {error}</div>;
  if (!ledger) return <div className="text-muted text-center py-12">Ledger not found</div>;

  const { ledger_metadata, verification_summary, chain_verification, hmac_verification } = ledger;
  const ratchetScheme = report?.pillars.F3_inference_provenance?.ratchet_scheme;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">F3: Inference Provenance</h1>
          <p className="text-sm text-muted flex items-center gap-2">
            <Key className="w-4 h-4" /> Scheme: {ledger_metadata.hmac_scheme}
            <span className="text-gray-300">|</span>
            <Clock className="w-4 h-4" /> Created: {new Date(ledger_metadata.created).toLocaleString()}
          </p>
        </div>
        <div className="flex flex-col items-end">
          <VerificationStatus
            status={verification_summary.status}
            hasRisk={verification_summary.tail_truncation_risk}
            riskMessage="The ledger was not verified against an independent length. Tail truncation (missing final entries) cannot be ruled out."
            className="items-end"
          />
        </div>
      </div>

      {/* HKDF Ratchet Security Panel */}
      {ratchetScheme && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Lock className="w-5 h-5 text-purple-600" />
            HKDF Ratchet Key Security
          </h2>
          <div className="bg-white border border-border rounded-lg p-5 shadow-sm border-l-4 border-l-purple-500">
            <div className="flex flex-col sm:flex-row gap-6">
              {/* Algorithm badge */}
              <div className="flex flex-col items-center justify-center bg-purple-50 rounded-lg p-4 min-w-[140px] border border-purple-100">
                <Zap className="w-8 h-8 text-purple-600 mb-2" />
                <span className="text-xs font-bold text-purple-900 text-center">{ratchetScheme.algorithm}</span>
                <span className="text-[10px] text-purple-600 mt-1">{ratchetScheme.ratchet_version}</span>
              </div>

              {/* Security properties */}
              <div className="flex-1">
                <p className="text-sm text-gray-700 mb-4">{ratchetScheme.description}</p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${
                    ratchetScheme.page_locked
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-gray-50 border-gray-200 text-gray-500'
                  }`}>
                    <Lock className="w-4 h-4 flex-shrink-0" />
                    <div>
                      <div className="text-xs font-bold">Page-Locked Memory</div>
                      <div className="text-[10px] opacity-70">VirtualLock (Windows)</div>
                    </div>
                    <span className="ml-auto">{ratchetScheme.page_locked ? '✓' : '✗'}</span>
                  </div>

                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${
                    ratchetScheme.secure_zeroization
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-gray-50 border-gray-200 text-gray-500'
                  }`}>
                    <Shield className="w-4 h-4 flex-shrink-0" />
                    <div>
                      <div className="text-xs font-bold">Secure Zeroization</div>
                      <div className="text-[10px] opacity-70">RtlSecureZeroMemory</div>
                    </div>
                    <span className="ml-auto">{ratchetScheme.secure_zeroization ? '✓' : '✗'}</span>
                  </div>

                  <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${
                    ratchetScheme.forward_secrecy
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-gray-50 border-gray-200 text-gray-500'
                  }`}>
                    <Zap className="w-4 h-4 flex-shrink-0" />
                    <div>
                      <div className="text-xs font-bold">Forward Secrecy</div>
                      <div className="text-[10px] opacity-70">Per-entry key ratchet</div>
                    </div>
                    <span className="ml-auto">{ratchetScheme.forward_secrecy ? '✓' : '✗'}</span>
                  </div>
                </div>

                <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-100 text-xs text-gray-600">
                  <p>
                    <span className="font-semibold">How it works:</span> After each HMAC-SHA256 signature, the key is
                    ratcheted via HKDF: <code className="font-mono bg-gray-100 px-1 rounded">K<sub>n+1</sub> = HMAC-SHA256(K<sub>n</sub>, "sentinel-ratchet-v1" ∥ σ<sub>n</sub>)</code>.
                    This ensures compromise of a derived key does not expose prior or future session keys.
                    The key buffer is page-locked to prevent swap-file leakage and securely zeroed after use.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white p-5 rounded-lg border border-border shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">Chain Verification</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Total Entries</span>
              <span className="text-sm font-medium">{chain_verification.total_entries}</span>
            </div>
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Broken Chain</span>
              <span className="text-sm font-medium">{chain_verification.tampering_checks.broken_chain ? 'Yes' : 'No'}</span>
            </div>
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Missing Entries</span>
              <span className="text-sm font-medium">{chain_verification.tampering_checks.missing_entries ? 'Yes' : 'No'}</span>
            </div>
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Modified Hashes</span>
              <span className="text-sm font-medium">{chain_verification.tampering_checks.modified_hashes ? 'Yes' : 'No'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Overall Status</span>
              <VerificationStatus status={chain_verification.tampering_checks.overall_status} />
            </div>
          </div>
        </div>

        <div className="bg-white p-5 rounded-lg border border-border shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">HMAC Verification</h3>
          <div className="space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Entries Verified</span>
              <span className="text-sm font-medium">{hmac_verification.entries_verified}</span>
            </div>
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Unsigned Entries</span>
              <span className="text-sm font-medium">{hmac_verification.entries_unsigned}</span>
            </div>
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <span className="text-sm text-gray-600">Fail Open Detected</span>
              <span className="text-sm font-medium">{hmac_verification.fail_open_detected ? 'Yes' : 'No'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Status</span>
              <VerificationStatus status={hmac_verification.fail_open_detected ? 'fail_open' : 'verified'} />
            </div>
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          Audit Timeline
          {verification_summary.tail_truncation_risk && (
            <ShieldAlert className="w-4 h-4 text-amber-500" aria-label="Tail truncation risk" />
          )}
        </h2>

        <div className="relative border-l border-gray-200 ml-3 space-y-8 pb-4">
          {ledger.ledger.map((entry) => {
            const hmacResult = hmac_verification.verification_results.find(r => r.sequence === entry.sequence);
            const chainResult = chain_verification.links.find(r => r.to_sequence === entry.sequence);

            const isUnsigned = entry.status === 'UNSIGNED';
            const hmacMatch = hmacResult?.match ?? false;

            return (
              <div key={entry.sequence} className="relative pl-6">
                {/* Timeline dot */}
                <span className={`absolute -left-[5px] top-1.5 w-[10px] h-[10px] rounded-full ring-4 ring-white ${
                  isUnsigned ? 'bg-gray-300' : hmacMatch ? 'bg-green-500' : 'bg-red-500'
                }`} />

                <div className="bg-white border border-border rounded-lg p-4 shadow-sm">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2 mb-3">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="bg-gray-100 text-gray-600 text-xs font-mono px-2 py-0.5 rounded">Seq {entry.sequence}</span>
                        <h4 className="text-sm font-bold text-gray-900">{entry.action}</h4>
                      </div>
                      <p className="text-xs text-gray-500">{new Date(entry.timestamp).toLocaleString()} ({entry.duration_seconds.toFixed(2)}s)</p>
                    </div>
                    <div>
                      <VerificationStatus status={entry.status} className="!flex-row" />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-2 text-xs font-mono mt-4 pt-3 border-t border-gray-100">
                    <div className="flex flex-col">
                      <span className="text-gray-400">Entry Hash</span>
                      <span className="text-gray-700 truncate" title={entry.entry_hash}>{entry.entry_hash}</span>
                    </div>
                    {entry.sequence > 0 && (
                      <div className="flex flex-col mt-1">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">Previous Hash</span>
                          {chainResult && !chainResult.match && (
                            <span className="text-red-500 font-bold">CHAIN BROKEN</span>
                          )}
                        </div>
                        <span className="text-gray-700 truncate" title={entry.previous_entry_hash}>{entry.previous_entry_hash}</span>
                      </div>
                    )}
                    <div className="flex flex-col mt-1">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-400">HMAC Signature</span>
                        {hmacResult && !hmacResult.match && !isUnsigned && (
                          <span className="text-red-500 font-bold">INVALID SIGNATURE</span>
                        )}
                      </div>
                      <span className="text-gray-700 truncate" title={entry.hmac_sha256}>{entry.hmac_sha256 || 'N/A'}</span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
