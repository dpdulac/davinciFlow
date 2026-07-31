import PyOpenColorIO as ocio

def main():
    try:
        config = ocio.GetCurrentConfig()
        print("Loaded OCIO Config.")
        
        baker = ocio.Baker()
        baker.setConfig(config)
        
        # Use IRIDAS .cube format (65x65x65)
        baker.setFormat("iridas_itx")
        baker.setCubeSize(65)
        
        # Set the color space and display/view
        baker.setInputSpace("acescg")
        baker.setShaperSpace("acescct")
        
        # Depending on OCIO version, we might need to set looks or target space
        # For a display transform in v1 baker, we set Looks to the view if needed, 
        # or we just get the view's colorspace and set it as target space.
        display = "Rec.709-Screen"
        view = "SPI_anim"
        
        # In OCIO, a view usually maps to a target colorspace
        display_colorspace = config.getDisplayViewColorSpaceName(display, view)
        print(f"Display Colorspace for {display}/{view} is: {display_colorspace}")
        
        baker.setTargetSpace(display_colorspace)
        
        print("Baking LUT... this may take a few seconds.")
        lut_data = baker.bake()
        
        out_path = "tmnt2_acescg_to_rec709.cube"
        with open(out_path, "w") as f:
            f.write(lut_data)
            
        print(f"Successfully baked LUT to {out_path}")
        
    except Exception as e:
        print(f"Error during baking: {e}")

if __name__ == "__main__":
    main()
