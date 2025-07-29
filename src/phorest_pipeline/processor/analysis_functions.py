import logging
from typing import Dict, Tuple

import cv2
import numpy as np

from phorest_pipeline.processor.analysis_methods import (
    centre,
    fano,
    gaussian,
    max_intensity,
)
from phorest_pipeline.shared.config import DEBUG_MODE
from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(name=__name__, level=logging.WARNING, rotate_daily=True, log_filename='processor.log')


def get_image_brightness_contrast(data: np.ndarray) -> Tuple[float, float]:
    brightness = np.round(np.mean(data), 2)
    contrast = np.round(np.quantile(data, 0.95) - np.quantile(data, 0.05), 2)
    return (brightness.astype(float), contrast.astype(float))


def extract_roi_data(data: np.ndarray, ID: str, ROIs: Dict) -> np.ndarray:
    """
    Function Details
    ============================================================================
    Using the metadata supplied in the ROIs dictionary, along with the record
    ID (ID), returns a slice of the data that only includes the region-of-
    interest.

    Parameters
    ----------
    data : ndarry
        2D array representing an image
    ID : string
        String containing the key for retrieving the appropriate record from
        the ROIs dictionary
    ROIs : dictionary
        Dictionary containing all ROI metadata

    Returns
    -------
    data : ndarray
        2D Array containing pixel values of the region-of-interest

    Notes
    -----
    If the ROI label contains the letter 'A', the ndarray is flipped left-to-
    right.  This ensures that the middle of the bow-tie grating always starts
    at the 0 index of the ndarray.

    Examples
    --------
    ROI_data = extract_roi_data(image_data, ROI_ID, ROI_dictionary)

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    try:
        start_coord = ROIs[ID]['coords']
        end_coord = [x + y for x, y in zip(ROIs[ID]['coords'], ROIs[ID]['size'])]
        data = data[start_coord[0] : end_coord[0], start_coord[1] : end_coord[1]]
    except KeyError as e:
        logger.error(f'An error occured when reading ROI metadata - {e}')
        exit(1)

    # Flip array left-to-right according to ROI manifest flag
    if ROIs[ID]['flip']:
        data = np.fliplr(data)

    return data


def preprocess_roi_data(data: np.ndarray, sub_rois: int) -> np.ndarray:
    """
    Function Details
    ============================================================================
    Used to reduce the input ROI data so that it contains subROI data.

    Parameters
    ----------
    data : ndarry
        2D array representing an ROI of an image
    sub_rois : int
        Number of sub-rois the ROI is to be split into, 0 indicates no sub-rois
        and to process the whole ROI row-by-row

    Returns
    -------
    _ : ndarray
        Array containing pixel values of the reduced region-of-interest

    Notes
    -----
    This function uses cv2.resize() along with its cv2.INTER_LINEAR
    interpolation method to reduce the ROI to subROIs.  cv2.INTER_LINEAR uses
    the arithmetic mean to reduce an images dimensions, this is the method
    I previously used when making this adjustment manually.
    Also, if subROIs == 0 then the ROI data is returned without re-sizing, this
    is equivalent to doing a full row-by-row analysis

    Examples
    --------
    ROI_data = preprocess_roi_data(ROI_data)

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    if sub_rois == 0:
        return data
    else:
        _, width = data.shape
        return cv2.resize(data, (width, sub_rois), interpolation=cv2.INTER_LINEAR)


def analyse_roi_data(data: np.ndarray, analysis_method: str) -> Dict:
    """
    Function Details
    ============================================================================
    Analyses ROI data according the method passed to the function.

    Parameters
    ----------
    data : ndarry
        2D array representing an ROI of an image
    analysis_method : string
        Method required for analysis see Notes for more details

    Returns
    -------
    results : Dictionary
        Dictionary containing the 'analysis_method' and the resulting
        analysis 'values'

    Notes
    -----
    Currently there are three analysis methods: 'centre', 'gaussian', and 'fano'
    there are no longer 'median' versions as the statistical analysis is now
    performed on all results (see postprocess_roi_results())

    Examples
    --------
    result = analyse_roi_data(ROI_data, analysis_method)

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    analysis = {
        'max_intensity': max_intensity,
        'centre': centre,
        'gaussian': gaussian,
        'fano': fano,
    }

    results = {}
    error_count = 0
    for idx, d in enumerate(data):
        d_std = np.std(d)
        if d_std < 0.1:
            error_count += 1
            continue
        result_dict = analysis[analysis_method](d)
        if not bool(result_dict):
            logger.warning(f'Row {idx}, fitting function failed')
            error_count += 1
            continue
        for key, value in result_dict.items():
            if key not in results:
                results['Analysis-method'] = analysis_method
                results[key] = {'Values': []}
            if np.isnan(value):
                continue
            results[key]['Values'].append(value)

    if error_count / data.shape[0] > 0.5:
        logger.warning(f'{error_count} / {data.shape[0]} rows excluded from analysis')
    else:
        logger.info(f'{error_count} / {data.shape[0]} rows excluded from analysis')
    return results


def postprocess_roi_results(data: Dict) -> Dict:
    """
    Function Details
    ============================================================================
    Analyses ROI data according the method passed to the function.

    Parameters
    ----------
    data : Dictionary
        Dictionary containing raw results from analyse_roi_data()

    Returns
    -------
    results : Dictionary
        Dictionary with statistical measurements added

    Notes
    -----
    Currently there are six measurements added to the results dictionary: mean,
    standard deviation, lower quantile, median, upper quantile and maximum value

    Examples
    --------
    result = postprocess_roi_results(result)

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    dp = 3
    for key, value in data.items():
        if 'Analysis-method' in key:
            continue
        temp = np.array(value['Values'])
        data[key]['Mean'] = np.round(np.mean(temp), decimals=dp)
        data[key]['STD'] = np.round(np.std(temp), decimals=dp)
        data[key]['LQ'] = np.round(np.quantile(temp, 0.25), decimals=dp)
        data[key]['Median'] = np.round(np.quantile(temp, 0.50), decimals=dp)
        data[key]['UQ'] = np.round(np.quantile(temp, 0.75), decimals=dp)
        data[key]['Max'] = np.round(np.max(temp), decimals=dp)
        data[key]['Min'] = np.round(np.min(temp), decimals=dp)
        data_range = data[key]['Max'] - data[key]['Min']
        if data_range == 0:
            data[key]['Smoothness'] = 0.0
        else:
            data[key]['Smoothness'] = np.round(
                np.std(np.diff(temp)) / data_range, decimals=dp
            )  # Smoothness i.e. Variation
        if not DEBUG_MODE:
            del value["Values"]
    return data
