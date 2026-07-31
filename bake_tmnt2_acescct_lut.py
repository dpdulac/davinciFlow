import PyOpenColorIO as ocio
import os

def main():
    # Load the studio TMNT2 OCIO config
    config = ocio.GetCurrentConfig()
    
    display = "Rec.709-Screen"
    view = "SPI_anim"
    output_space = config.getDisplayViewColorSpaceName(display, view)
    
    baker = ocio.Baker()
    baker.setConfig(config)
    baker.setFormat("iridas_itx")
    
    # CRITICAL: We set the input to ACEScct (log) instead of ACEScg (linear)
    baker.setInputSpace("acescct")
    baker.setTargetSpace(output_space)
    
    # 65x65x65 is high precision
    baker.setCubeSize(65)
    
    out_file = "tmnt2_acescct_to_rec709.cube"
    with open(out_file, "w") as f:
        f.write(baker.bake())
        
    print(f"Successfully baked {out_file}")

if __name__ == "__main__":
    main()
