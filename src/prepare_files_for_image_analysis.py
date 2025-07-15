from scripts.generate_roi_manifest import generate_roi_manifest

print("\nGenerating ROI metadata (this may take a few seconds)...")
generate_roi_manifest()

print("----------------------------------------------------------------------")
print("   ROI location file has been created.")
print("   Please check the saved ROI location images before continuing.")
print("   (see 'generated_files' directory)")
print("----------------------------------------------------------------------")
