#!/usr/bin/env python3
"""Print the external webcam's current /dev/video path using read-only sysfs.

Identify this machine's webcam by USB ID 32e6:9221, regardless of its video
device number. No camera or motor device is opened.
"""

import sys
from pathlib import Path

USB_VENDOR_ID = "32e6"
USB_PRODUCT_ID = "9221"
VIDEO_CLASS = Path("/sys/class/video4linux")


def usb_ids(video_device: Path) -> tuple[str, str] | None:
    """Find the USB IDs above a video device's sysfs directory."""
    for parent in video_device.resolve().parents:
        vendor_file = parent / "idVendor"
        product_file = parent / "idProduct"
        if vendor_file.is_file() and product_file.is_file():
            return vendor_file.read_text().strip().lower(), product_file.read_text().strip().lower()
    return None


def main() -> int:
    """Print matching capture paths, or fail when the webcam is disconnected."""
    if not VIDEO_CLASS.is_dir():
        print("No video devices found in sysfs.", file=sys.stderr)
        return 1

    matches = []
    for device in VIDEO_CLASS.glob("video[0-9]*"):
        try:
            # UVC index 0 is the capture interface; index 1 commonly carries metadata.
            if (device / "index").read_text().strip() != "0":
                continue
            if usb_ids(device) == (USB_VENDOR_ID, USB_PRODUCT_ID):
                matches.append(Path("/dev") / device.name)
        except (OSError, ValueError):
            continue

    if not matches:
        print(f"External webcam {USB_VENDOR_ID}:{USB_PRODUCT_ID} not found.", file=sys.stderr)
        return 1

    for path in sorted(matches, key=lambda path: int(path.name.removeprefix("video"))):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
