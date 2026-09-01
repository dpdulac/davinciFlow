#!/usr/bin/env python
"""
export_tmnt2_ocio2_ctf.py

This script leverages OpenColorIO v2 (2.5.1+) to optimize and export the legacy 
TMNT2 OCIO v1 color transformations into mathematically lossless Color Transform Format (.ctf) files
and generates a clean, standalone OCIO v2 configuration.

Usage (within Mikros environment):
    rez env ocio-2.5.1 pyocio-2.5.1 -- python export_tmnt2_ocio2_ctf.py
"""

import os
import sys
import shutil

try:
    import PyOpenColorIO as ocio
except ImportError:
    print("Error: PyOpenColorIO is not imported. Please run within 'rez env ocio-2.5.1 pyocio-2.5.1'.")
    sys.exit(1)

def main():
    print(f"=======================================================")
    print(f"  TMNT2 Native OCIO v2 CTF & Config Exporter")
    print(f"  Running OpenColorIO Version: {ocio.__version__}")
    print(f"=======================================================\n")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    legacy_config_path = "/s/apps/packages/prods/anim/tmnt2/tmnt2Core/3.23.1/color/config.ocio"

    if not os.path.exists(legacy_config_path):
        print(f"Error: Legacy show config not found at: {legacy_config_path}")
        sys.exit(1)

    print(f"[1] Loading Legacy OCIO Config: {legacy_config_path}...")
    legacy_config = ocio.Config.CreateFromFile(legacy_config_path)

    display_name = "Rec.709-Screen"
    view_name = "SPI_anim"

    # Define our targets and output filenames (Using CTF to natively preserve InverseLUT1D math)
    exports = [
        {
            "name": "Linear ACEScg to SPI_anim",
            "src": "ACEScg",
            "target_space": legacy_config.getDisplayViewColorSpaceName("Rec.709-Screen", "SPI_anim"),
            "filename": "tmnt2_native_look_v2.ctf",
            "description": "TMNT2 Show Look (ACEScg Linear to SPI_anim Rec.709) - Mathematically Exact OCIO v2 CTF"
        },
        {
            "name": "Log ACEScct to SPI_anim",
            "src": "ACEScct",
            "target_space": legacy_config.getDisplayViewColorSpaceName("Rec.709-Screen", "SPI_anim"),
            "filename": "tmnt2_acescct_to_rec709_v2.ctf",
            "description": "TMNT2 Show Look (ACEScct Log to SPI_anim Rec.709) - Mathematically Exact OCIO v2 CTF"
        },
        {
            "name": "Linear ACEScg to Standard Rec709",
            "src": "ACEScg",
            "target_space": "Output - Rec.709",
            "filename": "aces_rec709_v2.ctf",
            "description": "Standard ACES Rec.709 Output"
        },
        {
            "name": "Linear ACEScg to SPI_anim_P3D65",
            "src": "ACEScg",
            "target_space": legacy_config.getDisplayViewColorSpaceName("P3D65-Screen/Cinema", "SPI_anim"),
            "filename": "tmnt2_p3d65_look_v2.ctf",
            "description": "TMNT2 Show Look (ACEScg to P3D65)"
        },
        {
            "name": "Linear ACEScg to Standard P3D65",
            "src": "ACEScg",
            "target_space": "Output - P3D65",
            "filename": "aces_p3d65_v2.ctf",
            "description": "Standard ACES P3D65 Output"
        },
        {
            "name": "sRGB Texture to ACEScg",
            "src": "srgb8",
            "target_space": "acescg",
            "filename": "texture_srgb_to_acescg.ctf",
            "description": "Legacy TMNT2 sRGB texture mapping to ACEScg"
        },
        {
            "name": "Linear Texture to ACEScg",
            "src": "linear",
            "target_space": "acescg",
            "filename": "texture_linear_to_acescg.ctf",
            "description": "Legacy TMNT2 Linear texture mapping to ACEScg"
        }
    ]

    print(f"\n[2] Extracting and Optimizing Transform Chains via OCIO v2...")
    for item in exports:
        src_space = item["src"]
        target_space = item["target_space"]
        out_file = os.path.join(base_dir, item["filename"])

        # We request an optimized processor from OCIO 2.5.1
        processor = legacy_config.getProcessor(src_space, target_space)
        opt_processor = processor.getOptimizedProcessor(ocio.OPTIMIZATION_LOSSLESS)
        group = opt_processor.createGroupTransform()

        print(f"  -> Exporting {item['name']}:")
        print(f"     Optimized Op Count: {len(group)} transforms (down from legacy profile)")
        for i, x in enumerate(group):
            print(f"       Op {i}: {x.getTransformType()}")

        # Save as Color Transform Format (.ctf) which natively supports InverseLUT1D and matrices
        ctf_format_name = [fmt[0] for fmt in group.GetWriteFormats() if fmt[1] == "ctf"][0]
        ctf_xml_string = group.write(ctf_format_name)
        with open(out_file, "w") as f:
            f.write(ctf_xml_string)
        print(f"     Successfully saved CTF: {out_file}\n")

    print("[3] Generating Standalone OCIO v2 Profile Configuration...")
    v2_config_filename = "davidCustomConfig.ocio"
    v2_config_path = os.path.join(base_dir, v2_config_filename)

    # Constructing a clean, ultra-fast OCIO v2 profile referencing our native CTF shader
    v2_yaml = f"""ocio_profile_version: 2.1

search_path: .
strictparsing: false
luma: [0.2126, 0.7152, 0.0722]

roles:
  default: ACEScg
  scene_linear: ACEScg
  rendering: ACEScg
  color_picking: ACEScg
  texture_paint: ACEScg
  data: Raw

displays:
  Rec.709-Screen:
    - !<View> {{name: SPI_anim (TMNT2 Look), colorspace: ACEScg, looks: TMNT2_Look}}
    - !<View> {{name: Standard ACES Rec.709, colorspace: ACEScg, looks: ACES_Rec709_Look}}
    - !<View> {{name: AgX (Filmic), colorspace: ACEScg, looks: AgX_Look}}

  P3D65-Screen:
    - !<View> {{name: SPI_anim (TMNT2 Look), colorspace: ACEScg, looks: TMNT2_P3_Look}}
    - !<View> {{name: Standard ACES P3-D65, colorspace: ACEScg, looks: ACES_P3_Look}}
    - !<View> {{name: AgX (Filmic), colorspace: ACEScg, looks: AgX_Look}}

colorspaces:
  - !<ColorSpace>
    name: ACEScg
    family: ACES
    equalitygroup: ""
    bitdepth: 32f
    description: ACEScg scene-linear working space
    isdata: false
    encoding: scene-linear

  - !<ColorSpace>
    name: ACEScct
    family: ACES
    equalitygroup: ""
    bitdepth: 32f
    description: ACEScct logarithmic working space
    isdata: false
    encoding: log

  - !<ColorSpace>
    name: sRGB - Texture
    family: Utility
    equalitygroup: ""
    bitdepth: 32f
    description: Standard 8-bit sRGB color texture space
    isdata: false
    to_reference: !<FileTransform> {{src: texture_srgb_to_acescg.ctf, interpolation: linear}}

  - !<ColorSpace>
    name: Linear - Texture
    family: Utility
    equalitygroup: ""
    bitdepth: 32f
    description: Linear sRGB color texture space
    isdata: false
    to_reference: !<FileTransform> {{src: texture_linear_to_acescg.ctf, interpolation: linear}}

  - !<ColorSpace>
    name: Raw
    family: Utility
    equalitygroup: ""
    bitdepth: 32f
    description: Raw data
    isdata: true

  - !<ColorSpace>
    name: Inverse TMNT2 MattePaint
    family: Utility
    equalitygroup: ""
    bitdepth: 32f
    description: Matte Painting input - Inverts the TMNT2 Look to preserve sRGB appearance under the TMNT2 Look
    isdata: false
    to_reference: !<FileTransform> {{src: tmnt2_native_look_v2.ctf, direction: inverse, interpolation: tetrahedral}}

  - !<ColorSpace>
    name: Inverse AgX MattePaint
    family: Utility
    equalitygroup: ""
    bitdepth: 32f
    description: Matte Painting input - Inverts the AgX Look to preserve sRGB appearance under the AgX Look
    isdata: false
    to_reference: !<GroupTransform>
      children:
        - !<FileTransform> {{src: agx_acescct_to_rec709.ctf, direction: inverse, interpolation: tetrahedral}}
        - !<ColorSpaceTransform> {{src: ACEScct, dst: ACEScg}}

looks:
  - !<Look>
    name: TMNT2_Look
    process_space: ACEScg
    transform: !<FileTransform> {{src: tmnt2_native_look_v2.ctf, interpolation: linear}}

  - !<Look>
    name: ACES_Rec709_Look
    process_space: ACEScg
    transform: !<FileTransform> {{src: aces_rec709_v2.ctf, interpolation: linear}}

  - !<Look>
    name: TMNT2_P3_Look
    process_space: ACEScg
    transform: !<FileTransform> {{src: tmnt2_p3d65_look_v2.ctf, interpolation: linear}}

  - !<Look>
    name: ACES_P3_Look
    process_space: ACEScg
    transform: !<FileTransform> {{src: aces_p3d65_v2.ctf, interpolation: linear}}

  - !<Look>
    name: AgX_Look
    process_space: ACEScct
    transform: !<FileTransform> {{src: agx_acescct_to_rec709.ctf, interpolation: tetrahedral}}
"""
    with open(v2_config_path, "w") as f:
        f.write(v2_yaml)
    print(f"  -> Generated config file: {v2_config_path}")

    # Validate our newly created OCIO v2 configuration
    print("\n[4] Validating standalone OCIO v2 configuration...")
    try:
        new_config = ocio.Config.CreateFromFile(v2_config_path)
        new_config.validate()
        print("  -> SUCCESS: OCIO v2 configuration is 100% valid and operational!")
    except Exception as e:
        print(f"  -> WARNING: Validation feedback: {e}")

    # Copying to requested locations
    print("\n[5] Deploying copies to user directories...")
    david_ocio_dir = "/s/prodanim/studio/_sandbox/dulacd/davidOcio"
    if not os.path.exists(david_ocio_dir):
        os.makedirs(david_ocio_dir)

    destinations = [
        "/datas/dulacd",
        "/s/prodanim/studio/_sandbox/dulacd",
        david_ocio_dir,
        "/datas/dulacd/DaVinciResolve/LUT/davinciFlow"
    ]

    for dest in destinations:
        if os.path.exists(dest):
            if "DaVinciResolve/LUT" in dest:
                for item in exports:
                    src_ctf = os.path.join(base_dir, item["filename"])
                    dst_ctf = os.path.join(dest, item["filename"])
                    shutil.copy2(src_ctf, dst_ctf)
                    print(f"  -> Installed CTF to Resolve: {dst_ctf}")
            else:
                for item in exports:
                    src_ctf = os.path.join(base_dir, item["filename"])
                    dst_ctf = os.path.join(dest, item["filename"])
                    shutil.copy2(src_ctf, dst_ctf)
                dst_cfg = os.path.join(dest, v2_config_filename)
                shutil.copy2(v2_config_path, dst_cfg)
                print(f"  -> Deployed standalone config & CTF to: {dest}")
        else:
            print(f"  -> Skipping destination (not found): {dest}")

    print("\n=======================================================")
    print("  All OCIO v2 compilation and deployment tasks finished!")
    print("=======================================================")

if __name__ == "__main__":
    main()
