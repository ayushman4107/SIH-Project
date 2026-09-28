from __future__ import annotations
import cv2
import numpy as np
import scipy.stats as stats
from dataclasses import dataclass
import scipy.signal.windows as windows
from numpy.lib.stride_tricks import sliding_window_view

@dataclass
class SpectralPatchFinding:
    patch_row: int
    patch_col: int
    channel: str
    sector_radius_idx: int
    sector_angle_idx: int
    energy_fraction: float
    baseline_median: float
    baseline_mad: float
    anomaly_index: float

class SpectralSubbandRepairDetector:
    def __init__(
        self,
        patch_size: int = 16,
        stride: int = 8,
        n_radial_bins: int = 3,
        n_angular_bins: int = 8,
        anomaly_index_threshold: float = 6.0,
    ):
        self.patch_size = patch_size
        self.stride = stride
        self.n_radial_bins = n_radial_bins
        self.n_angular_bins = n_angular_bins
        self.anomaly_index_threshold = anomaly_index_threshold

        # V9 Sine-Window WOLA Geometry
        sine_1d = windows.hann(patch_size, sym=False) ** 0.5
        self._window = np.outer(sine_1d, sine_1d).astype(np.float32)
        self._polar_masks = self._build_polar_bin_masks(patch_size)

    def _build_polar_bin_masks(self, size: int) -> dict[tuple[int, int], np.ndarray]:
        freqs_y = np.fft.fftfreq(size)[:, None]
        freqs_x = np.fft.rfftfreq(size)[None, :]
        radius = np.sqrt(freqs_y ** 2 + freqs_x ** 2)
        angle = np.arctan2(freqs_y, freqs_x)

        r_edges = np.linspace(0, radius.max(), self.n_radial_bins + 1)
        a_edges = np.linspace(-np.pi, np.pi, self.n_angular_bins + 1)

        masks = {}
        for ri in range(self.n_radial_bins):
            for ai in range(self.n_angular_bins):
                mask = (
                    (radius >= r_edges[ri]) & (radius <= r_edges[ri + 1]) &
                    (angle >= a_edges[ai]) & (angle <= a_edges[ai + 1])
                )
                # DC Hard-Exclusion
                mask[0, 0] = False
                if mask.any():
                    masks[(ri, ai)] = mask
        return masks

    def _get_hermitian_weights(self, mask: np.ndarray, size: int) -> np.ndarray:
        weights = np.ones_like(mask, dtype=np.float32) * 2.0
        weights[:, -1] = 1.0 
        weights[size//2, :] = 1.0
        weights[0, 0] = 1.0
        weights[0, -1] = 1.0
        weights[size//2, 0] = 1.0
        weights[size//2, -1] = 1.0
        return weights[mask]

    def _process_patch(self, patch: np.ndarray, baselines: dict) -> tuple[np.ndarray, list[SpectralPatchFinding]]:
        windowed = patch * self._window
        F = np.fft.rfft2(windowed)
        magnitudes = np.abs(F)
        phases = np.angle(F)
        
        sector_energies = {}
        for (ri, ai), mask in self._polar_masks.items():
            W = self._get_hermitian_weights(mask, self.patch_size)
            sector_energies[(ri, ai)] = np.sum(W * (magnitudes[mask] ** 2))
            
        active_sectors = set(sector_energies.keys())
        flagged_sectors = set()
        findings = []
        
        # V9 Global Recursive Triage
        while True:
            total_energy = sum(sector_energies[k] for k in active_sectors) + 1e-12
            new_flag_found = False
            
            for k in active_sectors:
                if k in flagged_sectors:
                    continue
                fraction = sector_energies[k] / total_energy
                baseline = baselines.get(k)
                if not baseline:
                    continue
                    
                anomaly_idx = (fraction - baseline["median"]) / (baseline["mad"] + 1e-8)
                if anomaly_idx > self.anomaly_index_threshold:
                    flagged_sectors.add(k)
                    new_flag_found = True
            
            if not new_flag_found:
                break
                
            current_t = 0.0
            for k in flagged_sectors:
                baseline = baselines.get(k)
                target_fraction = baseline["median"] + self.anomaly_index_threshold * baseline["mad"]
                current_t += target_fraction
                
            if current_t >= 1.0:
                flagged_sectors.clear()
                break
                
            benign_energy = sum(sector_energies[k] for k in active_sectors if k not in flagged_sectors)
            target_total = benign_energy / (1.0 - current_t)
            
            for k in flagged_sectors:
                baseline = baselines.get(k)
                target_fraction = baseline["median"] + self.anomaly_index_threshold * baseline["mad"]
                sector_energies[k] = target_fraction * target_total
        
        # V9 Dual-Mode Annihilation & Phase Preservation
        for k in flagged_sectors:
            mask = self._polar_masks[k]
            mags = magnitudes[mask]
            
            internal_median = np.median(mags)
            internal_mad = np.median(np.abs(mags - internal_median))
            
            outliers = (mags - internal_median) > 3.0 * (internal_mad + 1e-8)
            
            if np.any(outliers):
                # Mode 1: Sparse Magnitude Annihilation
                mags[outliers] = internal_median
            else:
                # Mode 2: Dense Magnitude Annihilation
                target_E = sector_energies[k]
                W = self._get_hermitian_weights(mask, self.patch_size)
                current_E = np.sum(W * (mags ** 2))
                if current_E > target_E:
                    attenuation = np.sqrt(target_E / current_E)
                    mags *= attenuation
            
            F[mask] = mags * np.exp(1j * phases[mask])
            
            baseline = baselines.get(k)
            fraction = sector_energies[k] / total_energy
            anomaly_idx = (fraction - baseline["median"]) / (baseline["mad"] + 1e-8)
            findings.append(SpectralPatchFinding(
                patch_row=0, patch_col=0, channel="", 
                sector_radius_idx=k[0], sector_angle_idx=k[1],
                energy_fraction=fraction, baseline_median=baseline["median"],
                baseline_mad=baseline["mad"], anomaly_index=anomaly_idx
            ))
            
        repaired_patch = np.fft.irfft2(F)
        repaired_patch *= self._window
        return repaired_patch, findings

    def screen_image(self, bgr_image: np.ndarray, baselines: dict) -> tuple[dict, np.ndarray, dict]:
        original_h, original_w = bgr_image.shape[:2]
        
        # V9 Padded Geometry
        pad_size = self.patch_size // 2
        padded_bgr = np.pad(bgr_image, ((pad_size, pad_size), (pad_size, pad_size), (0, 0)), mode='reflect')
        ph, pw = padded_bgr.shape[:2]
        
        is_grayscale = False
        if len(bgr_image.shape) == 2 or (np.all(bgr_image[:,:,0] == bgr_image[:,:,1])):
            is_grayscale = True
            channels = {"Y": padded_bgr[:,:,0] if len(bgr_image.shape)==3 else padded_bgr}
        else:
            ycrcb = cv2.cvtColor(padded_bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
            channels = {"Y": ycrcb[..., 0], "Cr": ycrcb[..., 1], "Cb": ycrcb[..., 2]}

        all_findings = {}
        repaired_channels = {}
        
        for ch_name, ch_img in channels.items():
            if ch_name not in baselines:
                repaired_channels[ch_name] = ch_img.copy()
                continue
                
            ch_findings = []
            repaired_ch = np.zeros_like(ch_img, dtype=np.float32)
            weight_ch = np.zeros_like(ch_img, dtype=np.float32)
            
            ny = (ph - self.patch_size) // self.stride + 1
            nx = (pw - self.patch_size) // self.stride + 1
            
            for y_idx in range(ny):
                for x_idx in range(nx):
                    y = y_idx * self.stride
                    x = x_idx * self.stride
                    
                    patch = ch_img[y:y+self.patch_size, x:x+self.patch_size]
                    repaired_patch, findings = self._process_patch(patch, baselines[ch_name])
                    
                    for f in findings:
                        f.patch_row = y - pad_size
                        f.patch_col = x - pad_size
                        f.channel = ch_name
                        if f.patch_row >= 0 and f.patch_col >= 0 and f.patch_row < original_h and f.patch_col < original_w:
                            ch_findings.append(f)
                            
                    repaired_ch[y:y+self.patch_size, x:x+self.patch_size] += repaired_patch
                    weight_ch[y:y+self.patch_size, x:x+self.patch_size] += self._window ** 2
                    
            safe_weights = np.where(weight_ch > 0, weight_ch, 1.0)
            repaired_channels[ch_name] = repaired_ch / safe_weights
            all_findings[ch_name] = ch_findings
            
        if is_grayscale:
            sanitized_padded = repaired_channels["Y"]
            sanitized_padded = np.stack([sanitized_padded]*3, axis=-1)
        else:
            sanitized_ycrcb = np.stack([repaired_channels["Y"], repaired_channels["Cr"], repaired_channels["Cb"]], axis=-1)
            sanitized_padded = cv2.cvtColor(sanitized_ycrcb.astype(np.float32), cv2.COLOR_YCrCb2BGR)
            
        sanitized = sanitized_padded[pad_size:pad_size+original_h, pad_size:pad_size+original_w]
        
        # V9 Post-Clamp Heatmapping
        sanitized_uint8 = np.clip(sanitized, 0, 255).astype(np.uint8)
        heatmap_bgr = np.abs(bgr_image.astype(np.int32) - sanitized_uint8.astype(np.int32)).astype(np.uint8)
        heatmap = np.max(heatmap_bgr, axis=2)
        
        flagged_pixels = np.count_nonzero(heatmap > 0)
        total_area = original_h * original_w
        flagged_fraction = flagged_pixels / total_area
        
        verdict = "accept"
        if flagged_fraction >= 0.005:
            verdict = "quarantine"
        elif flagged_fraction >= 0.001:
            verdict = "review"
            
        metrics = {
            "flagged_fraction": float(flagged_fraction),
            "flagged_pixel_count": int(flagged_pixels),
            "verdict": verdict,
            "is_grayscale_fallback": is_grayscale
        }
        
        return all_findings, heatmap, metrics
