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

    # Define our targets and output filenames (Using CTF to natively preserve InverseLUT1D math)
    exports = [
        {
            "name": "Linear ACEScg to SPI_anim",
            "src": "ACEScg",
            "filename": "tmnt2_native_look_v2.ctf",
            "description": "TMNT2 Show Look (ACEScg Linear to SPI_anim Rec.709) - Mathematically Exact OCIO v2 CTF"
        },
        {
            "name": "Log ACEScct to SPI_anim",
            "src": "ACEScct",
            "filename": "tmnt2_acescct_to_rec709_v2.ctf",
            "description": "TMNT2 Show Look (ACEScct Log to SPI_anim Rec.709) - Mathematically Exact OCIO v2 CTF"
        }
    ]

    display_name = "Rec.709-Screen"
    view_name = "SPI_anim"

    print(f"\n[2] Extracting and Optimizing Transform Chains via OCIO v2...")
    for item in exports:
        src_space = item["src"]
        out_file = os.path.join(base_dir, item["filename"])

        # We request an optimized processor from OCIO 2.5.1
        processor = legacy_config.getProcessor(src_space, legacy_config.getDisplayViewColorSpaceName(display_name, view_name))
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
    v2_config_filename = "tmnt2_config_v2.ocio"
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
    - !<View> {{name: SPI_anim, colorspace: ACEScg, looks: TMNT2_Look}}

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
    name: Raw
    family: Utility
    equalitygroup: ""
    bitdepth: 32f
    description: Raw data
    isdata: true

looks:
  - !<Look>
    name: TMNT2_Look
    process_space: ACEScg
    transform: !<FileTransform> {{src: tmnt2_native_look_v2.ctf, interpolation: linear}}
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
    destinations = [
        "/datas/dulacd",
        "/s/prodanim/tmnt2/_sandbox/dulacd",
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
