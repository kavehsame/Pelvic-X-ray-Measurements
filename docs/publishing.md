# Publishing

The source repository is **kavehsame/Pelvic-X-ray-Measurements**. GitHub Releases
hosts the complete extension and web bundles. GitHub Pages hosts the landing page,
browser app and documentation. The website is a static deployment: it does not
process or receive research images.

## First publication

1. Create the public repository. For the initial setup, keep Actions disabled
   while pushing the prepared source tree to **main** and publishing the model
   assets. This avoids starting builds before their dependencies exist.
2. Create the separate **models-v1.6.0** release and upload the two model files,
   Apache licence, model notice and checksums. Publish it before build workflows
   attempt to restore those assets. Do not mark this supporting asset release as
   the latest software release.
3. Enable GitHub Actions and set **Settings → Pages → Source** to **GitHub Actions**.
4. Run the checks workflow and inspect its results. Complete the native Slicer
   replay on a supported installation as described in [testing](testing.md).
5. Run the Pages workflow. Open the public landing page, then test Start, local
   image loading and export in Chrome. Confirm that the published files match the
   build checksums. Do not use patient data for publication checks or screenshots.
6. Create the **v1.6.0** software release from the reviewed commit. Attach the
   extension ZIP, web ZIP and **SHA256SUMS.txt**. Use the [release notes](releases/v1.6.0.md).

GitHub automatically adds source archives to a release. Explain that these are
developer source snapshots and do not contain the separately distributed models
or browser runtime. Do not put model weights or generated builds into source history.

## Updates

Version 1.8.0 restores its processed implant catalogue and PNG overlays from the [template asset release](https://github.com/kavehsame/Pelvic-X-ray-Measurements/releases/tag/templates-v1.8.0). The two filenames, byte counts and SHA-256 hashes are in `implant-assets.json`. Both the website build and the complete Slicer bundle use those same files. For a revised catalogue, create a new asset tag and update the manifest and Slicer build references together. Publish the asset release before the Pages build and keep the software release marked as latest.

Use a new software version and a new release for a changed distribution. Run both
editions through the common verifier, select the passing evidence, rebuild the
website and package the new downloads. Keep earlier releases. Reuse the same model
version only if its files are unchanged. Do not overwrite published model assets.

The Pages workflow deploys the generated **build/site/** directory. It uses the
repository's GitHub token with Pages permissions and an identity token; it does
not require a personal access token stored in source. The release workflow creates
a draft so its assets and notes can be reviewed before publication.

## Slicer Extensions Manager

Catalogue submission is a separate step after the public repository and model assets
are reachable. The repository provides a root CMake entry and keeps the extension
tree intact. Before submitting to the Slicer Extensions Index, verify installation
with the current supported Slicer release, confirm icon and screenshot URLs and
follow the current extension-submission requirements. An index entry is not
automatically created by publishing to GitHub.

References: [GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages),
[GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
and [Slicer extension distribution](https://slicer.readthedocs.io/en/latest/developer_guide/extensions.html).

**Research use only.** Keep the research-only, medical-device and clinical-use
notices in the landing page, manuals, application and download material.
