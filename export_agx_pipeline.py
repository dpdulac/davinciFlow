#!/usr/bin/env python
"""
export_agx_pipeline.py

This script generates high-precision 65x65x65 3D LUTs (.cube) and native OCIO v2 (.ctf) profiles
for an industry-standard AgX Color Science Pipeline in DaVinci Flow.

Outputs Generated:
    1. agx_acescct_to_rec709.cube (for EXR image sequences via ACEScct log space)
    2. agx_rec709_proxy.cube      (for video proxies: .mov, .mp4, DNxHD)
    3. agx_srgb_img.cube          (for image stills: .png, .jpg, .tga)
    4. agx_config_v2.ocio         (Standalone OCIO v2.1 profile for DCCs like Nuke/Houdini/Katana)
    5. Native .ctf versions of the above transforms for OCIO v2 DCC workflows.

Usage (within Mikros environment):
    rez env ocio-2.5.1 pyocio-2.5.1 -- python export_agx_pipeline.py
"""

import os
import sys
import math
import shutil

try:
    import PyOpenColorIO as ocio
except ImportError:
    print("Error: PyOpenColorIO is not imported. Please run within 'rez env ocio-2.5.1 pyocio-2.5.1'.")
    sys.exit(1)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("Notice: NumPy not found. Using standard Python math loop (slightly slower).")

# ==============================================================================
# AgX MATHEMATICAL CORE (Standard AgX by Troy Sobotka / Jed Smith approximation)
# ==============================================================================

# Matrix: sRGB / Rec.709 primaries to ACEScg (AP1) linear RGB
REC709_TO_ACESCG = [
    [0.613097, 0.339523, 0.047379],
    [0.070194, 0.916354, 0.013452],
    [0.020616, 0.109570, 0.869815]
]

# Matrix: AgX Inset Primary Compression (Applied to ACEScg linear RGB)
AGX_INSET_MATRIX = [
    [0.856627153315983, 0.0951212405381588, 0.0482516061458583],
    [0.0137249751411824, 0.782959828699504, 0.203315196159314],
    [0.00968539613996213, 0.0980209678430588, 0.892293636016979]
]

def mat3_mul(mat, rgb):
    r, g, b = rgb[0], rgb[1], rgb[2]
    return [
        mat[0][0] * r + mat[0][1] * g + mat[0][2] * b,
        mat[1][0] * r + mat[1][1] * g + mat[1][2] * b,
        mat[2][0] * r + mat[2][1] * g + mat[2][2] * b
    ]

def acescct_to_linear(x):
    """Academy ACEScct log decode to ACEScg linear RGB."""
    if x > 0.0729055341958355:
        return 2.0 ** (x * 17.52 - 9.72)
    else:
        return (x - 0.0729055341958355) / 10.5402377416545 + 0.001

def rec709_eotf(x):
    """Standard BT.1886 / Rec.709 display EOTF (Gamma 2.4) to Linear."""
    return max(0.0, x) ** 2.4

def srgb_eotf(x):
    """Standard sRGB display EOTF to Linear."""
    if x <= 0.04045:
        return x / 12.92
    else:
        return ((x + 0.055) / 1.055) ** 2.4

def linear_to_agx_log2(x):
    """Encode linear scene light into AgX Log2 space (-10 EV to +6.5 EV -> [0, 1])."""
    val = max(x, 1e-10)
    log_val = (math.log(val, 2.0) + 10.0) / 16.5
    return max(0.0, min(1.0, log_val))

def agx_punchy_curve(x):
    """Standard AgX Punchy tone compression curve (Smooth Filmic Sigmoid)."""
    x = max(0.0, min(1.0, x))
    x2 = x * x
    x4 = x2 * x2
    y = 15.5 * (x4 * x2) - 40.14 * (x4 * x) + 31.96 * x4 - 6.868 * (x2 * x) + 0.4298 * x2 + 0.1191 * x - 0.00232
    return max(0.0, min(1.0, y))

def evaluate_pixel(rgb_in, mode):
    """Evaluates a single RGB triplet through the chosen AgX mode."""
    # Step 1: Decode Input to Linear ACEScg
    if mode == "acescct":
        lin_rgb = [acescct_to_linear(rgb_in[0]), acescct_to_linear(rgb_in[1]), acescct_to_linear(rgb_in[2])]
    elif mode == "rec709":
        lin_rec709 = [rec709_eotf(rgb_in[0]), rec709_eotf(rgb_in[1]), rec709_eotf(rgb_in[2])]
        lin_rgb = mat3_mul(REC709_TO_ACESCG, lin_rec709)
    elif mode == "srgb":
        lin_srgb = [srgb_eotf(rgb_in[0]), srgb_eotf(rgb_in[1]), srgb_eotf(rgb_in[2])]
        lin_rgb = mat3_mul(REC709_TO_ACESCG, lin_srgb)
    else:
        lin_rgb = rgb_in

    # Step 2: Apply AgX Inset Primary Compression
    inset_rgb = mat3_mul(AGX_INSET_MATRIX, lin_rgb)

    # Step 3: Encode into AgX Log2
    log_rgb = [linear_to_agx_log2(c) for c in inset_rgb]

    # Step 4: Apply AgX Filmic Tone Compression Curve
    out_rgb = [agx_punchy_curve(c) for c in log_rgb]

    return out_rgb

# ==============================================================================
# LUT BAKER & CTF / OCIO GENERATION
# ==============================================================================

def generate_cube_and_ctf(mode, name, title, size=65, base_dir="."):
    print(f"\n---> Generating [{title}] (Mode: {mode}) at {size}x{size}x{size}...")
    
    grid = []
    lines = []
    lines.append(f"# Created by DaVinci Flow AgX Pipeline Generator")
    lines.append(f"# Mode: {title}")
    lines.append(f"LUT_3D_SIZE {size}")

    step = 1.0 / (size - 1)
    
    # 3D LUT Standard Order: Blue (slowest), Green, Red (fastest)
    for b_idx in range(size):
        b = b_idx * step
        for g_idx in range(size):
            g = g_idx * step
            for r_idx in range(size):
                r = r_idx * step
                out = evaluate_pixel([r, g, b], mode)
                grid.extend(out)
                lines.append(f"{out[0]:.6f} {out[1]:.6f} {out[2]:.6f}")

    # Write .cube file
    cube_filename = f"{name}.cube"
    cube_path = os.path.join(base_dir, cube_filename)
    with open(cube_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"     Successfully saved 3D LUT: {cube_path}")

    # Generate equivalent OpenColorIO v2 CTF shader
    ctf_filename = f"{name}.ctf"
    ctf_path = os.path.join(base_dir, ctf_filename)
    
    lut3d_transform = ocio.Lut3DTransform(gridSize=size)
    if HAS_NUMPY:
        lut3d_transform.setData(np.array(grid, dtype=np.float32))
    else:
        import array
        lut3d_transform.setData(array.array('f', grid))
    group = ocio.GroupTransform([lut3d_transform])
    
    ctf_format_name = [fmt[0] for fmt in group.GetWriteFormats() if fmt[1] == "ctf"][0]
    ctf_xml = group.write(ctf_format_name)
    with open(ctf_path, "w") as f:
        f.write(ctf_xml)
    print(f"     Successfully saved OCIO v2 CTF: {ctf_path}")

    return cube_filename, ctf_filename

def generate_standalone_ocio_config(base_dir="."):
    print("\n---> Generating Standalone AgX OCIO v2 Configuration...")
    v2_config_filename = "agx_config_v2.ocio"
    v2_config_path = os.path.join(base_dir, v2_config_filename)

    yaml = f"""ocio_profile_version: 2.1

search_path: .
strictparsing: false
luma: [0.2126, 0.7152, 0.0722]

roles:
  default: ACEScg
  scene_linear: ACEScg
  rendering: ACEScg
  color_picking: sRGB-Stills
  texture_paint: sRGB-Stills
  data: Raw

displays:
  Rec.709-Screen:
    - !<View> {{name: AgX-EXR, colorspace: ACEScg, looks: AgX_EXR_Look}}
    - !<View> {{name: AgX-Proxy, colorspace: Rec709-Proxy, looks: AgX_Proxy_Look}}
    - !<View> {{name: AgX-Stills, colorspace: sRGB-Stills, looks: AgX_Stills_Look}}

colorspaces:
  - !<ColorSpace>
    name: ACEScg
    family: ACES
    encoding: scene-linear
    description: ACEScg linear space (EXR)

  - !<ColorSpace>
    name: ACEScct
    family: ACES
    encoding: log

  - !<ColorSpace>
    name: Rec709-Proxy
    family: Video
    description: Rec.709 video space for MOV/MP4 proxies

  - !<ColorSpace>
    name: sRGB-Stills
    family: Stills
    description: sRGB space for PNG/TGA/JPG textures

  - !<ColorSpace>
    name: Raw
    family: Utility
    isdata: true

looks:
  - !<Look>
    name: AgX_EXR_Look
    process_space: ACEScct
    transform: !<FileTransform> {{src: agx_acescct_to_rec709.ctf, interpolation: tetrahedral}}

  - !<Look>
    name: AgX_Proxy_Look
    process_space: Rec709-Proxy
    transform: !<FileTransform> {{src: agx_rec709_proxy.ctf, interpolation: tetrahedral}}

  - !<Look>
    name: AgX_Stills_Look
    process_space: sRGB-Stills
    transform: !<FileTransform> {{src: agx_srgb_img.ctf, interpolation: tetrahedral}}
"""
    with open(v2_config_path, "w") as f:
        f.write(yaml)
    print(f"     Saved standalone AgX config: {v2_config_path}")
    return v2_config_filename

def main():
    print("=======================================================")
    print(f"  DaVinci Flow - AgX Color Science Pipeline Generator")
    print(f"  Running OpenColorIO Version: {ocio.__version__}")
    print("=======================================================")

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Generate the 3-Tier AgX LUT & CTF Profiles (65x65x65)
    exr_cube, exr_ctf = generate_cube_and_ctf("acescct", "agx_acescct_to_rec709", "AgX EXR (ACEScct Log to Rec709)", 65, base_dir)
    mov_cube, mov_ctf = generate_cube_and_ctf("rec709", "agx_rec709_proxy", "AgX Video Proxy (Rec709 to Rec709)", 65, base_dir)
    img_cube, img_ctf = generate_cube_and_ctf("srgb", "agx_srgb_img", "AgX Image Stills (sRGB to Rec709)", 65, base_dir)

    # 2. Generate Standalone OCIO v2 Config for DCCs
    cfg_name = generate_standalone_ocio_config(base_dir)

    # 3. Validate OCIO Config
    print("\n---> Validating generated OCIO v2 Configuration...")
    try:
        cfg = ocio.Config.CreateFromFile(os.path.join(base_dir, cfg_name))
        cfg.validate()
        print("     SUCCESS: OCIO v2 Configuration is 100% valid!")
    except Exception as e:
        print(f"     WARNING: OCIO Validation issue: {e}")

    # 4. Deploy across user systems
    print("\n---> Deploying AgX pipeline profiles to target locations...")
    destinations = [
        "/datas/dulacd",
        "/s/prodanim/studio/_sandbox/dulacd",
        "/datas/dulacd/DaVinciResolve/LUT/davinciFlow"
    ]

    artifacts = [exr_cube, exr_ctf, mov_cube, mov_ctf, img_cube, img_ctf, cfg_name]

    for dest in destinations:
        if os.path.exists(dest):
            for item in artifacts:
                # DaVinci Resolve LUT directory only needs the .cube and .ctf files, not .ocio
                if "DaVinciResolve/LUT" in dest and item.endswith(".ocio"):
                    continue
                src_path = os.path.join(base_dir, item)
                dst_path = os.path.join(dest, item)
                shutil.copy2(src_path, dst_path)
            print(f"     Deployed 3-Tier AgX suite to: {dest}")
        else:
            print(f"     Skipping destination (directory not found): {dest}")

    print("\n=======================================================")
    print("  AgX Color Science generation and deployment finished!")
    print("=======================================================")

if __name__ == "__main__":
    main()
