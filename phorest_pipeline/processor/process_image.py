############################################################################
############################################################################
#                             Analyse Image                                #
#                      Author: Christopher Reardon                         #
#                            Date: 17/10/2024                              #
#       Description: Analyses image to extract resonance position          #
#                    returns results as a JSON file                        #
#                          Project: PhorestDX                              #
#                                                                          #
#                       Script designed for Python 3                       #
#         © Copyright Christopher Reardon, Joshua Male, PhorestDX          #
#                                                                          #
#                       Software release: UNRELEASED                       #
############################################################################
############################################################################
import json
from pathlib import Path

import cv2

from phorest_pipeline.processor.analysis_functions import (
    analyse_roi_data,
    extract_roi_data,
    get_image_brightness_contrast,
    postprocess_roi_results,
    preprocess_roi_data,
)
from phorest_pipeline.shared.config import (
    METHOD,
    NUMBER_SUB_ROIS,
    ROI_MANIFEST_PATH,
)

IMAGE_SIZE_THRESHOLD = 1_000_000  # Bits


def process_image(image_meta: dict | None) -> tuple[list | None, str | None]:
    print('[ANALYSER] [INFO] Processing image...')
    print(f'[ANALYSER] [INFO] Number of subROIs: {NUMBER_SUB_ROIS}')
    if not image_meta or not image_meta.get('filename') or not image_meta.get('filepath'):
        return None, 'Missing image metadata or filename.'

    if not ROI_MANIFEST_PATH.exists():
        return None, f'ROI manifest file not found: {ROI_MANIFEST_PATH}'
    
    with open(ROI_MANIFEST_PATH, 'r') as file:
        ROI_dictionary = json.load(file)

    image_filename = image_meta['filename']
    data_filepath = image_meta['filepath']
    image_filepath = Path(data_filepath, image_filename)
    processing_results = []

    try:
        if not image_filepath.exists():
            return None, f'Image file not found: {image_filepath}'

        image_size_good = image_filepath.stat().st_size > IMAGE_SIZE_THRESHOLD

        if not image_size_good:
            return None, 'Image does not match size criteria : {image_filepath}'

        # Load image
        image_data = cv2.imread(str(image_filepath), cv2.IMREAD_UNCHANGED)

        if image_data is None:
            return None, f'Failed to load image file (may be corrupt): {image_filepath}'

        brightness, contrast = get_image_brightness_contrast(image_data)

        processing_results.append({
            'brightness' : brightness,
            'contrast' : contrast,
        })

        # Normalise image data
        image_data = cv2.normalize(
            image_data,
            None,  # type:ignore[arg-type]
            0,
            255,
            cv2.NORM_MINMAX,
            dtype=cv2.CV_8U,
        )

        # Rotate image
        h, w = image_data.shape
        rot_centre = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(rot_centre, -ROI_dictionary['image_angle'], 1.0)
        image_data = cv2.warpAffine(image_data, rotation_matrix, (w, h))

        # Begin loop over ROIs
        for ROI_ID in ROI_dictionary:
            if 'ROI' not in ROI_ID:
                continue
            print(f'[ANALYSER] [INFO] Processing ROI "{ROI_ID}"')

            # Add ROI label to results dictionary
            results = { 'ROI-label' : ROI_dictionary[ROI_ID]['label'] }

            # Slice image to ROI
            ROI_data = extract_roi_data(image_data, ROI_ID, ROI_dictionary)

            # Prepare ROI for analysis
            ROI_data = preprocess_roi_data(ROI_data, NUMBER_SUB_ROIS)

            # Analyse ROI
            result = analyse_roi_data(ROI_data, METHOD)

            if not result:
                print(f'[ANALYSER] [WARNING] ROI {ROI_ID} - Resonance not visible')
                continue

            # Post-process results to add statistical analysis
            results.update(postprocess_roi_results(result))

            processing_results.append(results)

        return processing_results, None

    except Exception as e:
        error_msg = f'Error processing image {image_filepath}: {e}'
        print(f'[PROCESSOR] [ERROR] {error_msg}')
        return None, error_msg


if __name__ == '__main__':
    # Example usage
    image_meta = {'filename': 'example_image.png', 'filepath': '/path/to/image/directory'}
    results, error = process_image(image_meta)
    if error:
        print(f'Error: {error}')
    else:
        print(f'Processing results: {results}')
