from pathlib import Path

import cv2
import matplotlib.patches as patches
import matplotlib.pyplot as plt


def visualize_search_window_preprocessing(
    original_search_window, sharpened_search_window, binarized_search_window, save_path
):
    message = "at function visualize_search_window_preprocessing"

    if not isinstance(save_path, Path):
        return (None, f"[ERROR] 'save_path' must be a pathlib.Path object {message}.")

    _, axes = plt.subplots(1, 3, figsize=(15, 5))

    try:
        axes[0].imshow(cv2.cvtColor(original_search_window, cv2.COLOR_BGR2RGB))
        axes[0].set_title("Original Search Window")
        axes[0].axis("off")

        axes[1].imshow(cv2.cvtColor(sharpened_search_window, cv2.COLOR_BGR2RGB))
        axes[1].set_title("Sharpened Search Window")
        axes[1].axis("off")

        axes[2].imshow(cv2.cvtColor(binarized_search_window, cv2.COLOR_BGR2RGB))
        axes[2].set_title("Binarized Search Window")
        axes[2].axis("off")

        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        return (None, None)
    except IOError as e:
        return (
            None,
            f"[ERROR] Error saving search window visualization to '{save_path}' {message}: {e}",
        )
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during visualization {message}: {e}")


def visualize_template_matching_result(
    search_window, result, max_loc, max_val, mean_val, quality_metric, save_path
):
    message = "at function visualize_template_matching_result"

    if not isinstance(save_path, Path):
        return (None, f"[ERROR] 'save_path' must be a pathlib.Path object {message}.")

    try:
        _, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))

        ax1.imshow(cv2.cvtColor(search_window, cv2.COLOR_BGR2RGB))
        ax1.set_title("Search Window")
        circle1 = patches.Circle(max_loc, 5, color="red", fill=False)
        ax1.add_patch(circle1)

        ax2.imshow(result, cmap="gray")
        ax2.set_title(
            f"Template Matching Result\n{max_val =:.2f}\n{mean_val =:.2f}\n{quality_metric =:.2f}"
        )
        circle2 = patches.Circle(max_loc, 5, color="red", fill=False)
        ax2.add_patch(circle2)

        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()
        return (None, None)
    except IOError as e:
        return (
            None,
            f"[ERROR] Error saving template matching visualization to '{save_path}' {message}: {e}",
        )
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during visualization {message}: {e}")


def visualize_features_with_matplotlib(
    rotated_image, chip_mapping, feature_shape, save_path, key="features"
):
    message = "at function visualize_features_with_matplotlib"

    if not isinstance(save_path, Path):
        return (None, f"[ERROR] 'save_path' must be a pathlib.Path object {message}.")

    try:
        rotated_image_rgb = cv2.cvtColor(rotated_image, cv2.COLOR_BGR2RGB)

        _, ax = plt.subplots(1, figsize=(12, 12))
        ax.imshow(rotated_image_rgb)

        if "features" in key:
            features = chip_mapping.get(key, None)
        if "gratings" in key:
            features = chip_mapping

        if features:
            for f in features:
                label = f.get("label")
                if "features" in key:
                    location = f.get("refined_location")
                if "gratings" in key:
                    location = f.get("grating_origin")

                if location:
                    x, y = location
                    if feature_shape:
                        height, width = feature_shape
                    else:
                        width = f.get("x-size")
                        height = f.get("y-size")

                    rect = patches.Rectangle(
                        (x, y), width, height, linewidth=1, edgecolor="white", facecolor="none"
                    )
                    ax.add_patch(rect)
                    ax.annotate(
                        label, location, color="white", fontsize=8, ha="center", va="bottom"
                    )

        plt.title("Rotated Image with features highlighted")
        plt.savefig(save_path)
        plt.close()
        return (None, None)
    except IOError as e:
        return (None, f"[ERROR] Error saving visualization to '{save_path}' {message}: {e}")
    except Exception as e:
        return (None, f"[ERROR] An unexpected error occurred during visualization {message}: {e}")
