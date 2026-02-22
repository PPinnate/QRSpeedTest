from setuptools import setup

APP = ["main.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "QRSpeedTest",
        "CFBundleDisplayName": "QRSpeedTest",
        "NSCameraUsageDescription": "QRSpeedTest needs camera access to benchmark QR decoder speed.",
    },
    "packages": ["qrspeedtest"],
}

setup(
    app=APP,
    name="QRSpeedTest",
    data_files=[],
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
