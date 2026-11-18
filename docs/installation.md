# Installation and downloads

## Web application

Open the [website](https://kavehsame.github.io/Pelvic-X-ray-Measurements/) and
select **Start the web app**. Select **Start** in the app to prepare the measurement
workspace. The browser downloads the software and models, then performs image
processing locally. There is no separate software installation. Chrome or Edge is
recommended for choosing folders and saving directly into them.

Choose images using the input folder picker or **Open a file...**. Selecting a file
lets the browser read it locally; it does not upload it to the website. The
[web manual](web-manual.md) explains all controls and export choices.

**PelvicXrayMeasurements_1.7.0_web.zip** is for people who want to host their own
copy of the website. Normal users do not need it. Extract its files and serve them
over HTTPS, or through a local loopback web server for testing. Opening the HTML
directly from disk is not the supported launch method. The ZIP includes the full
runtime and models, but no generated test results or research images.

## Slicer extension

1. Install a current supported 3D Slicer release from [slicer.org](https://www.slicer.org/).
2. Download **PelvicXrayMeasurements_1.7.0_Slicer_extension.zip** from the GitHub release.
3. Extract the ZIP. Keep its folders and resources together.
4. In Slicer, open **Application Settings → Modules → Additional module paths**.
5. Add the inner **PelvicXrayMeasurements** folder containing **PelvicXrayMeasurements.py**.
6. Restart Slicer and select **Pelvic Xray Measurements** under **Orthopaedics**.

The bundle already includes the Smart Point Placement models. It is a scripted
module source bundle, not an Extensions Manager installer. Slicer catalogue review
is a separate process; this release does not claim an existing catalogue listing.
The tested Slicer version is recorded with the selected software checks.

## Source and checksums

GitHub's **Source code** archives contain the repository, documentation and tests.
They omit generated builds, runtime downloads and model weights. Developers should
follow [development](development.md) to restore the pinned build assets.

Use **SHA256SUMS.txt** from the release to verify each named download. The separate
**models-v1.6.0** release contains the two aggregate model files, licence and notices.
It is a build dependency; users of the complete extension bundle or web app do not
need to download those model files separately.

**Research use only. This software is not a medical device.** It is not intended
for diagnosis, treatment planning or other clinical decision-making.
