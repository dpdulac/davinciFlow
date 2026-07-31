import PyOpenColorIO as ocio
import numpy as np
import os

def main():
    config = ocio.GetCurrentConfig()
    
    # We want to map:
    # 1D Pre-LUT: ACEScg -> acescct (Input domain [0, 50])
    # 3D LUT: acescct -> Rec.709-Screen (SPI_anim)
    
    input_space = "acescg"
    shaper_space = "acescct"
    
    display = "Rec.709-Screen"
    view = "SPI_anim"
    output_space = config.getDisplayViewColorSpaceName(display, view)
    
    processor_1d = config.getProcessor(input_space, shaper_space)
    cpu_1d = processor_1d.getDefaultCPUProcessor()
    
    processor_3d = config.getProcessor(shaper_space, output_space)
    cpu_3d = processor_3d.getDefaultCPUProcessor()
    
    # 1. Generate 1D LUT
    lut_1d_size = 4096
    domain_min = 0.0
    domain_max = 50.0  # ACEScg values up to 50
    
    x_1d = np.linspace(domain_min, domain_max, lut_1d_size, dtype=np.float32)
    rgb_1d = np.column_stack((x_1d, x_1d, x_1d))
    
    print("Processing 1D Shaper...")
    cpu_1d.applyRGB(rgb_1d)
    
    # 2. Generate 3D LUT
    lut_3d_size = 65
    x_3d = np.linspace(0.0, 1.0, lut_3d_size, dtype=np.float32)
    
    # Create 3D grid
    r, g, b = np.meshgrid(x_3d, x_3d, x_3d, indexing='ij')
    rgb_3d = np.column_stack((r.flatten(), g.flatten(), b.flatten()))
    
    print("Processing 3D LUT...")
    cpu_3d.applyRGB(rgb_3d)
    
    # 3. Write .cube file
    out_path = "tmnt2_acescg_to_rec709_shaper.cube"
    print(f"Writing {out_path}...")
    
    with open(out_path, "w") as f:
        f.write(f'TITLE "TMNT2 ACEScg to Rec709 with Shaper"\n')
        f.write(f'DOMAIN_MIN {domain_min} {domain_min} {domain_min}\n')
        f.write(f'DOMAIN_MAX {domain_max} {domain_max} {domain_max}\n\n')
        
        f.write(f'LUT_1D_SIZE {lut_1d_size}\n')
        # Write 1D data
        for rgb in rgb_1d:
            f.write(f"{rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")
            
        f.write(f'\nLUT_3D_SIZE {lut_3d_size}\n')
        # Write 3D data (in .cube, B varies fastest, then G, then R)
        # But meshgrid 'ij' gives shape (R, G, B), flatten gives R varying slowest.
        # .cube expects R to vary fastest!
        # Let's fix the grid generation for .cube format:
        pass
    
    # Correct 3D grid generation for .cube format (R varies fastest, then G, then B)
    # The order in the file must be:
    # R0 G0 B0
    # R1 G0 B0
    # ...
    # Rn G0 B0
    # R0 G1 B0
    # etc.
    
    r_fast, g_fast, b_fast = np.meshgrid(x_3d, x_3d, x_3d, indexing='ij')
    # np.meshgrid('ij') -> return shape is (len(x1), len(x2), len(x3)) -> (R, G, B)
    # Wait, if we want R to vary fastest, we should iterate B, then G, then R
    
    # Build list manually to be absolutely certain of order
    rgb_3d_list = []
    for b_val in x_3d:
        for g_val in x_3d:
            for r_val in x_3d:
                rgb_3d_list.append([r_val, g_val, b_val])
                
    rgb_3d_arr = np.array(rgb_3d_list, dtype=np.float32)
    cpu_3d.applyRGB(rgb_3d_arr)
    
    with open(out_path, "w") as f:
        f.write(f'TITLE "TMNT2 ACEScg to Rec709 with Shaper"\n')
        f.write(f'DOMAIN_MIN {domain_min} {domain_min} {domain_min}\n')
        f.write(f'DOMAIN_MAX {domain_max} {domain_max} {domain_max}\n\n')
        
        f.write(f'LUT_1D_SIZE {lut_1d_size}\n')
        for rgb in rgb_1d:
            f.write(f"{rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")
            
        f.write(f'\nLUT_3D_SIZE {lut_3d_size}\n')
        for rgb in rgb_3d_arr:
            f.write(f"{rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")
            
    print("Done!")

if __name__ == "__main__":
    main()
