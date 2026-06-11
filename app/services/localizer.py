import os
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib")

import numpy as np
import SimpleITK as sitk
import torch
import torch.nn as nn
from monai.networks.nets import BasicUNet
from scipy import ndimage as ndi


DEFAULT_MODEL_PATH = Path("/Users/fellwakh/Downloads/production_localizer.pt")
DEFAULT_MICRO_CT_SPACING_MM = float(os.getenv("LOCALIZER_DEFAULT_SPACING_MM", "0.01002"))
MAX_TRUSTED_SPACING_MM = float(os.getenv("LOCALIZER_MAX_TRUSTED_SPACING_MM", "0.1"))
DEFAULT_CROP_EDGE_MM = float(os.getenv("LOCALIZER_DEFAULT_CROP_EDGE_MM", "4.5"))


def _strip_nii_suffix(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".nii.gz"):
        return filename[:-7]
    if lower.endswith(".nii"):
        return filename[:-4]
    return Path(filename).stem


def automated_crop_name(filename: str) -> str:
    return f"{_strip_nii_suffix(Path(filename).name)}_Automated_Crop.nii.gz"


def _read_image(path: str | Path) -> sitk.Image:
    img = sitk.ReadImage(str(path))
    if img.GetNumberOfComponentsPerPixel() > 1:
        img = sitk.VectorIndexSelectionCast(img, 0)
    return img


def _sitk_to_np(img: sitk.Image) -> np.ndarray:
    return sitk.GetArrayFromImage(img)


def _resample_to_target_size(
    img: sitk.Image,
    target_size_zyx: tuple[int, int, int],
    is_label: bool = False,
) -> sitk.Image:
    target_size_xyz = (target_size_zyx[2], target_size_zyx[1], target_size_zyx[0])
    orig_size = img.GetSize()
    orig_spacing = img.GetSpacing()
    new_spacing = [
        orig_size[i] * orig_spacing[i] / target_size_xyz[i] for i in range(3)
    ]
    interp = sitk.sitkNearestNeighbor if is_label else sitk.sitkBSpline

    rs = sitk.ResampleImageFilter()
    rs.SetSize(list(target_size_xyz))
    rs.SetOutputSpacing(new_spacing)
    rs.SetOutputOrigin(img.GetOrigin())
    rs.SetOutputDirection(img.GetDirection())
    rs.SetInterpolator(interp)
    rs.SetDefaultPixelValue(0)
    return rs.Execute(img)


def _normalize_intensity(arr: np.ndarray, p_lo: float = 0.5, p_hi: float = 99.5) -> np.ndarray:
    lo, hi = np.percentile(arr, [p_lo, p_hi])
    arr = np.clip(arr, lo, hi)
    mu = arr.mean()
    sd = arr.std() + 1e-6
    return ((arr - mu) / sd).astype(np.float32)


def _largest_cc_centroid(mask: np.ndarray):
    if mask.sum() == 0:
        return None
    labels, n = ndi.label(mask)
    if n == 0:
        return None
    sizes = ndi.sum(mask, labels, index=range(1, n + 1))
    keep = int(np.argmax(sizes)) + 1
    com = ndi.center_of_mass(mask, labels, keep)
    return tuple(float(c) for c in com)


def _build_localizer(cfg: dict) -> nn.Module:
    features = tuple(cfg.get("features", (16, 32, 64, 128, 256, 16)))
    return BasicUNet(
        spatial_dims=3,
        in_channels=cfg.get("in_channels", 1),
        out_channels=cfg.get("out_channels", 1),
        features=features,
        norm="instance",
        act=("LeakyReLU", {"negative_slope": 0.1, "inplace": True}),
        dropout=0.0,
    )


@lru_cache(maxsize=1)
def _load_model():
    model_path = Path(os.getenv("LOCALIZER_MODEL_PATH", DEFAULT_MODEL_PATH))
    if not model_path.exists():
        raise FileNotFoundError(f"Localizer model not found: {model_path}")

    checkpoint = torch.load(model_path, map_location="cpu")
    cfg = checkpoint.get("cfg", {})
    model = _build_localizer(cfg)
    model.load_state_dict(checkpoint["model"])
    model.eval()
    return model, cfg


@torch.no_grad()
def _predict_centroid_in_full_scan(
    model: nn.Module,
    scan_img: sitk.Image,
    target_grid: tuple[int, int, int],
) -> tuple[float, float, float]:
    scan_lr_img = _resample_to_target_size(scan_img, target_grid, is_label=False)
    scan_lr_np = _normalize_intensity(_sitk_to_np(scan_lr_img))
    x = torch.from_numpy(scan_lr_np)[None, None]

    model.eval()
    logits = model(x)
    pred = (torch.sigmoid(logits) > 0.5).cpu().numpy()[0, 0]

    com_lr = _largest_cc_centroid(pred)
    if com_lr is None:
        raise RuntimeError("Localizer produced an empty mask. Check checkpoint or input.")

    com_lr_xyz = (com_lr[2], com_lr[1], com_lr[0])
    phys_point = scan_lr_img.TransformContinuousIndexToPhysicalPoint(com_lr_xyz)
    com_fr_xyz = scan_img.TransformPhysicalPointToContinuousIndex(phys_point)
    return (com_fr_xyz[2], com_fr_xyz[1], com_fr_xyz[0])


def _crop_fixed_physical_size(
    scan_img: sitk.Image,
    centroid_full_zyx: tuple[float, float, float],
    edge_mm: float,
) -> sitk.Image:
    original_spacing_xyz = np.array(scan_img.GetSpacing())
    spacing_xyz = _effective_spacing(original_spacing_xyz)
    full_size_xyz = np.array(scan_img.GetSize())

    half_vox_xyz = np.round((edge_mm / 2.0) / spacing_xyz).astype(int)
    full_size_target_xyz = (2 * half_vox_xyz).astype(int)

    cz, cy, cx = centroid_full_zyx
    center_xyz = np.array([cx, cy, cz])
    start_xyz = np.round(center_xyz - half_vox_xyz).astype(int)

    for i in range(3):
        if start_xyz[i] < 0:
            start_xyz[i] = 0
        if start_xyz[i] + full_size_target_xyz[i] > full_size_xyz[i]:
            start_xyz[i] = full_size_xyz[i] - full_size_target_xyz[i]
        start_xyz[i] = max(start_xyz[i], 0)
        full_size_target_xyz[i] = min(full_size_target_xyz[i], full_size_xyz[i])

    crop = sitk.RegionOfInterest(
        scan_img,
        size=[int(s) for s in full_size_target_xyz],
        index=[int(s) for s in start_xyz],
    )
    if not np.allclose(spacing_xyz, original_spacing_xyz):
        crop.SetSpacing(tuple(float(s) for s in spacing_xyz))
    return crop


def _effective_spacing(spacing_xyz: np.ndarray) -> np.ndarray:
    spacing_xyz = np.asarray(spacing_xyz, dtype=np.float32)
    if (
        np.any(~np.isfinite(spacing_xyz))
        or np.any(spacing_xyz <= 0)
        or np.any(spacing_xyz > MAX_TRUSTED_SPACING_MM)
    ):
        return np.array([DEFAULT_MICRO_CT_SPACING_MM] * 3, dtype=np.float32)
    return spacing_xyz


def crop_scan_to_roi(input_path: Path, output_path: Path) -> dict:
    model, cfg = _load_model()
    target_grid = tuple(cfg.get("target_grid", (128, 128, 128)))
    configured_crop_mm = float(cfg.get("fixed_crop_mm", 28.0))
    default_crop_mm = configured_crop_mm if configured_crop_mm < 10 else DEFAULT_CROP_EDGE_MM
    fixed_crop_mm = float(os.getenv("LOCALIZER_CROP_MM", default_crop_mm))

    scan_img = _read_image(input_path)
    centroid_zyx = _predict_centroid_in_full_scan(model, scan_img, target_grid)
    cropped = _crop_fixed_physical_size(scan_img, centroid_zyx, fixed_crop_mm)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(cropped, str(output_path))

    sx, sy, sz = cropped.GetSpacing()
    nx, ny, nz = cropped.GetSize()
    vol_mm3 = sx * sy * sz * nx * ny * nz
    return {
        "centroid_z": float(centroid_zyx[0]),
        "centroid_y": float(centroid_zyx[1]),
        "centroid_x": float(centroid_zyx[2]),
        "crop_size_xyz": [int(nx), int(ny), int(nz)],
        "crop_spacing_xyz": [float(sx), float(sy), float(sz)],
        "crop_volume_mm3": float(vol_mm3),
        "fixed_crop_mm": fixed_crop_mm,
        "checkpoint_fixed_crop_mm": configured_crop_mm,
        "target_grid": [int(x) for x in target_grid],
    }
