import logging
from typing import Dict
from numba import jit

import numpy as np
from scipy.optimize import curve_fit

from phorest_pipeline.shared.logger_config import configure_logger

logger = configure_logger(
    name=__name__, level=logging.WARNING, rotate_daily=True, log_filename="processor.log"
)

@jit(nopython=True) 
def max_intensity(data: np.ndarray) -> Dict:
    """
    Function Details
    ============================================================================
    Return the location of the maximum pixel value

    Parameters
    ----------
    data : ndarray
        1D array of pixel values

    Returns
    -------
    _ : Dict
        Dictionary containing result

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    return {"max_intensity": int(np.argmax(data))}


@jit(nopython=True) 
def centre(data: np.ndarray) -> Dict:
    """
    Function Details
    ============================================================================
    Return the location of the centre-of-mass of the distribution of pixel
    values.

    Parameters
    ----------
    data : ndarray
        1D array of pixel values

    Returns
    -------
    _ : Dict
        Dictionary containing result

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    # Filter data to only include peak area
    threshold = (np.std(data) * 3.0) + np.mean(data)
    data = np.where(data < threshold, 0, data)

    return {"centre": np.sum(data * np.arange(1, len(data) + 1)) / np.sum(data)}


@jit(nopython=True) 
def gaussian(data: np.ndarray) -> Dict:
    """
    Function Details
    ============================================================================
    Return the fitting parameters after fitting a guassian function to the
    distribution of pixel values

    Parameters
    ----------
    data : ndarray
        1D array of pixel values

    Returns
    -------
    _ : Dict
        Dictionary containing result

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """

    def gaussian_func(x, a, mu, sigma, offset):
        return (a * np.exp(-((x - mu) ** 2) / (2 * sigma**2))) + offset

    xdata = np.arange(0, len(data))
    p0 = [np.max(data) - np.min(data), np.argmax(data), 1, np.mean(data)]
    try:
        popt, _ = curve_fit(gaussian_func, xdata, data, p0=p0)
    except (RuntimeError, ValueError) as e:
        logger.warning(f"[FUNCTION FITTING] Curve fitting failed: {e}")
        return {}

    error = RMSE(data, gaussian_func(xdata, *popt))
    return {
        "amplitude": popt[0],
        "mu": popt[1],
        "sigma": popt[2],
        "offset": popt[3],
        "error": error,
    }


@jit(nopython=True) 
def fano(data: np.ndarray) -> Dict:
    """
    Function Details
    ============================================================================
    Return the fitting parameters after fitting a fano function to the
    distribution of pixel values

    Parameters
    ----------
    data : ndarray
        1D array of pixel values

    Returns
    -------
    _ : Dict
        Dictionary containing result

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """

    def fano_func(x, amp, assym, res, gamma, offset):
        num = ((assym * gamma) + (x - res)) * ((assym * gamma) + (x - res))
        den = (gamma * gamma) + ((x - res) * (x - res))
        return (amp * (num / den)) + offset

    xdata = np.arange(0, len(data))
    p0 = [np.max(data) - np.min(data), 0, np.argmax(data), len(data) / 4, np.mean(data)]
    try:
        popt, _ = curve_fit(fano_func, xdata, data, p0=p0)
    except (RuntimeError, ValueError) as e:
        logger.warning(f"[FUNCTION FITTING] Curve fitting failed: {e}")
        return {}

    error = RMSE(data, fano_func(xdata, *popt))
    return {
        "amplitude": popt[0],
        "assymetry": popt[1],
        "resonance": popt[2],
        "gamma": popt[3],
        "offset": popt[4],
        "error": error,
    }


@jit(nopython=True) 
def RMSE(data1: np.ndarray, data2: np.ndarray) -> float:
    """
    Function Details
    ============================================================================
    Return the root-mean-square-error between the fitted data and the raw data

    Parameters
    ----------
    data1 : ndarray
        1D array of pixel values
    data2: ndarray
        1D array derived from fitting parameters

    Returns
    -------
    _ : float
        Result of RMSE calculation

    ----------------------------------------------------------------------------
    Update History
    ==============

    16/10/2024
    ----------
    Created function CR.
    """
    squared_diff = (data1 - data2) ** 2
    mse = np.mean(squared_diff)
    return np.sqrt(mse)
